# -*- coding: utf-8 -*-
"""
抽取结果的「原文定位」与长文分块（借鉴 google/langextract 的做法）

借鉴的三点：
  1. Source grounding：每个字段除 value 外必须带 evidence（逐字摘自原文的片段）。
     程序把 evidence 在原文里找出来，记录字符位置；找不到的字段标记为 unverified。
  2. 长文分块 + 合并：原文超过 CHUNK_CHARS 时按行切块（块间有重叠），逐块抽取后合并，避免一次塞太长漏条款。
  3. 补抽（multi-pass）：对第一轮没能在原文里验证的字段，再抽一轮；仍不过的保留并标记，不静默丢弃。

对下游的兼容：
  bid_result.json / contract_result.json 仍是 {"字段": {"value": ...}}，step3 不用改；
  带 evidence、字符位置、验证状态的完整结果另存为 *.grounded.json。
"""

import difflib
import os
import re
import unicodedata

CHUNK_CHARS = int(os.environ.get("CHECKHT_CHUNK_CHARS", "80000"))
CHUNK_OVERLAP = int(os.environ.get("CHECKHT_CHUNK_OVERLAP", "2000"))
EXTRA_PASSES = int(os.environ.get("CHECKHT_EXTRA_PASSES", "1"))  # 对未验证字段最多补抽几轮；0 = 不补抽
FUZZY_RATIO = 0.8
PLACEHOLDER = "{{CONTRACT_TEXT}}"

_SPACE = re.compile(r"\s+")
_NUMBER = re.compile(r"\d+(?:\.\d+)?")


# ------------------------------------------------------------
# 规范化与定位
# ------------------------------------------------------------

def normalize(text):
    """NFKC + 去掉所有空白 + 小写。PDF 抽取的文本常带多余换行和空格，不能逐字节比较。"""
    return _SPACE.sub("", unicodedata.normalize("NFKC", str(text))).lower()


class SourceIndex:
    """原文的规范化副本，以及规范化位置 → 原文位置的映射。"""

    def __init__(self, text):
        self.text = text
        chars, index = [], []
        for pos, ch in enumerate(text):
            piece = normalize(ch)
            for c in piece:
                chars.append(c)
                index.append(pos)
        self.norm = "".join(chars)
        self.index = index

    def _span(self, start, end):
        return [self.index[start], self.index[end - 1] + 1]

    def locate(self, quote):
        """返回 (status, [start, end] 或 None)。status: exact / fuzzy / not_found / too_short"""
        nq = normalize(quote)
        if len(nq) < 2:
            return "too_short", None
        pos = self.norm.find(nq)
        if pos >= 0:
            return "exact", self._span(pos, pos + len(nq))
        match = difflib.SequenceMatcher(None, self.norm, nq, autojunk=False).find_longest_match(
            0, len(self.norm), 0, len(nq))
        if match.size >= 6 and match.size >= FUZZY_RATIO * len(nq):
            return "fuzzy", self._span(match.a, match.a + match.size)
        return "not_found", None


def numbers_missing(value, source_index):
    """value 里出现、但原文规范化文本里找不到的阿拉伯数字（金额、期限、比例、条款号）。"""
    if not value:
        return []
    missing = []
    for number in _NUMBER.findall(normalize(value)):
        if number not in source_index.norm and number not in missing:
            missing.append(number)
    return missing


# ------------------------------------------------------------
# 分块
# ------------------------------------------------------------

def split_chunks(text, max_chars=CHUNK_CHARS, overlap=CHUNK_OVERLAP):
    if len(text) <= max_chars:
        return [text]
    lines = []
    for line in text.split("\n"):
        while len(line) > max_chars:  # 极端长行：硬切
            lines.append(line[:max_chars])
            line = line[max_chars:]
        lines.append(line)
    chunks, current, size = [], [], 0
    for line in lines:
        if size + len(line) + 1 > max_chars and current:
            chunks.append("\n".join(current))
            tail, kept = [], 0
            for prev in reversed(current):  # 下一块从上一块末尾的几行重叠开始
                if kept + len(prev) + 1 > overlap:
                    break
                tail.insert(0, prev)
                kept += len(prev) + 1
            current, size = tail, kept
        current.append(line)
        size += len(line) + 1
    if current:
        chunks.append("\n".join(current))
    return chunks


# ------------------------------------------------------------
# 结果整理
# ------------------------------------------------------------

def _entry(raw):
    """把一个字段的原始输出整理成 (value, [evidence...])；兼容没带 evidence 的旧格式。"""
    if isinstance(raw, dict):
        value = raw.get("value")
        evidence = raw.get("evidence")
    else:
        value, evidence = raw, None
    if value is not None and not isinstance(value, str):
        value = str(value)
    if isinstance(value, str) and not value.strip():
        value = None
    if isinstance(evidence, str):
        evidence = [evidence]
    evidence = [e.strip() for e in (evidence or []) if isinstance(e, str) and e.strip()]
    return value, evidence


def _fields(data):
    """AI 返回的 JSON → {字段名: (value, evidence)}。"""
    if not isinstance(data, dict):
        raise ValueError("AI 返回的 JSON 顶层必须是对象")
    return {name: _entry(raw) for name, raw in data.items()}


def _merge(results):
    """多块结果合并：每个字段保留所有块里的不同取值与证据（原规则：多个约定全部保留）。"""
    merged = {}
    for fields in results:
        for name, (value, evidence) in fields.items():
            old_value, old_evidence = merged.get(name, (None, []))
            if value and value not in (old_value or ""):
                old_value = value if not old_value else old_value + "\n" + value
            merged[name] = (old_value, old_evidence + [e for e in evidence if e not in old_evidence])
    return merged


def verify_field(value, evidence, source_index):
    """返回该字段的定位结果字典。"""
    report = {"value": value, "evidence": [], "warnings": []}
    if value is None:
        report["grounding"] = "empty"
        if evidence:
            report["warnings"].append("value 为空但给了 evidence")
        return report
    if not evidence:
        report["grounding"] = "no_evidence"
        report["warnings"].append("AI 没有给出 evidence，无法核对")
    else:
        statuses = []
        for quote in evidence:
            status, span = source_index.locate(quote)
            report["evidence"].append({"text": quote, "status": status, "char_interval": span})
            statuses.append(status)
        if all(s == "exact" for s in statuses):
            report["grounding"] = "verified"
        elif any(s in ("exact", "fuzzy") for s in statuses):
            report["grounding"] = "partial"
        else:
            report["grounding"] = "unverified"
    missing = numbers_missing(value, source_index)
    if missing:
        report["warnings"].append(
            "value 中的数字在原文里找不到：" + "、".join(missing)
            + "（可能是大小写数字换算，也可能是 AI 编造，请人工核对）")
        if report["grounding"] == "verified":
            report["grounding"] = "partial"
    return report


NEEDS_RETRY = ("unverified", "no_evidence")


# ------------------------------------------------------------
# 主流程
# ------------------------------------------------------------

def build_prompt(template, chunk, number=1, total=1, only_fields=None):
    notes = []
    if total > 1:
        notes.append(f"【说明】合同原文较长，已分段处理。这是第 {number}/{total} 段，只依据本段原文提取；本段没有的字段 value 填 null、evidence 填 []。")
    if only_fields:
        notes.append("【补抽】上一轮下列字段的 evidence 没能在原文中逐字找到：" + "、".join(only_fields)
                     + "。本轮只需重新核对这些字段：evidence 必须逐字复制原文，无法逐字摘出的字段 value 填 null；其余字段 value 填 null、evidence 填 []。")
    head = ("\n".join(notes) + "\n\n") if notes else ""
    if PLACEHOLDER in template:
        return head + template.replace(PLACEHOLDER, chunk)
    return head + template + "\n\n以下是正式合同原文：\n\n" + chunk


def _run_pass(gateway, provider, template, chunks, parse, log, only_fields=None):
    results = []
    for i, chunk in enumerate(chunks, 1):
        prompt = build_prompt(template, chunk, i, len(chunks), only_fields)
        log(f"请求 AI：第 {i}/{len(chunks)} 段，Prompt {len(prompt)} 字符")
        ai_text = gateway.request_with_retry(provider, prompt)
        if not ai_text or not str(ai_text).strip():
            raise RuntimeError("AI 没有返回内容")
        results.append(_fields(parse(ai_text)))
    return _merge(results)


def extract_fields(gateway, provider, template, source_text, parse=None, log=print,
                   max_chars=None, overlap=None, extra_passes=None):
    """抽取 + 原文定位。返回 (clean, grounded)。

    clean    {"字段": {"value": ...}}，与原来的 *_result.json 同格式
    grounded {"fields": {字段: {value, evidence[{text,status,char_interval}], grounding, warnings}}, "summary": {...}}
    """
    if parse is None:
        from contract_ai import parse_ai_json as parse
    chunks = split_chunks(source_text, max_chars or CHUNK_CHARS, CHUNK_OVERLAP if overlap is None else overlap)
    index = SourceIndex(source_text)
    fields = _run_pass(gateway, provider, template, chunks, parse, log)
    reports = {name: verify_field(value, ev, index) for name, (value, ev) in fields.items()}

    passes = EXTRA_PASSES if extra_passes is None else extra_passes
    for round_no in range(1, passes + 1):
        retry = [n for n, r in reports.items() if r["grounding"] in NEEDS_RETRY]
        if not retry:
            break
        log(f"第 {round_no} 轮补抽：{len(retry)} 个字段没能在原文中验证：{'、'.join(retry)}")
        again = _run_pass(gateway, provider, template, chunks, parse, log, only_fields=retry)
        for name in retry:
            if name not in again:
                continue
            value, evidence = again[name]
            new = verify_field(value, evidence, index)
            if new["grounding"] in ("verified", "partial"):
                new["warnings"].append(f"第 {round_no} 轮补抽后通过")
                reports[name] = new

    clean = {}
    for name, r in reports.items():
        clean[name] = {"value": r["value"]}
    summary = {}
    for r in reports.values():
        summary[r["grounding"]] = summary.get(r["grounding"], 0) + 1
    grounded = {"source_chars": len(source_text), "chunks": len(chunks), "summary": summary, "fields": reports}
    return clean, grounded


def print_summary(grounded, log=print):
    log("原文定位结果：" + "，".join(f"{k} {v}" for k, v in sorted(grounded["summary"].items())))
    for name, r in grounded["fields"].items():
        if r["grounding"] in NEEDS_RETRY + ("partial",) or r["warnings"]:
            log(f"  ⚠ {name}：{r['grounding']}" + ("；" + "；".join(r["warnings"]) if r["warnings"] else ""))
