# -*- coding: utf-8 -*-
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import grounding as g

SOURCE = "第五条 价款\n5.1 合同价款为人民币 1200 万元，\n工期270日历天。\n第六条 保修\n保修期为二年。"
TEMPLATE = "规则……\n合同原文如下：\n{{CONTRACT_TEXT}}"


class FakeGateway:
    def __init__(self, replies):
        self.replies, self.prompts = list(replies), []

    def request_with_retry(self, provider, prompt):
        self.prompts.append(prompt)
        return json.dumps(self.replies[min(len(self.prompts) - 1, len(self.replies) - 1)], ensure_ascii=False)


def run(replies, source=SOURCE, **kw):
    gw = FakeGateway(replies)
    clean, grounded = g.extract_fields(gw, {}, TEMPLATE, source, parse=json.loads, log=lambda m: None, **kw)
    return gw, clean, grounded


class Locate(unittest.TestCase):
    def test_exact_match_ignores_whitespace_and_returns_original_offsets(self):
        status, span = g.SourceIndex(SOURCE).locate("合同价款为人民币1200万元")
        self.assertEqual(status, "exact")
        self.assertEqual(SOURCE[span[0]:span[1]], "合同价款为人民币 1200 万元")

    def test_fuzzy_and_not_found(self):
        index = g.SourceIndex(SOURCE)
        self.assertEqual(index.locate("合同价款为人民币1200万圆")[0], "fuzzy")
        self.assertEqual(index.locate("质量保证金扣留百分之三")[0], "not_found")

    def test_numbers_missing(self):
        index = g.SourceIndex(SOURCE)
        self.assertEqual(g.numbers_missing("1200万元，工期300天", index), ["300"])


class Chunks(unittest.TestCase):
    def test_short_text_is_one_chunk(self):
        self.assertEqual(g.split_chunks("abc", 100, 10), ["abc"])

    def test_long_text_is_split_with_overlap_and_nothing_lost(self):
        lines = [f"第{i}条 内容内容内容" for i in range(200)]
        chunks = g.split_chunks("\n".join(lines), 300, 60)
        self.assertGreater(len(chunks), 3)
        self.assertTrue(all(len(c) <= 300 for c in chunks))
        joined = "\n".join(chunks)
        self.assertTrue(all(line in joined for line in lines))
        self.assertTrue(set(chunks[0].split("\n")) & set(chunks[1].split("\n")))  # 块间有重叠


class Extract(unittest.TestCase):
    GOOD = {"合同金额": {"value": "5.1：人民币1200万元", "evidence": ["合同价款为人民币1200万元"]},
            "施工工期": {"value": "270日历天", "evidence": ["工期270日历天"]},
            "保修期": {"value": None, "evidence": []}}

    def test_verified_and_clean_output_keeps_old_format(self):
        gw, clean, grounded = run([self.GOOD])
        self.assertEqual(len(gw.prompts), 1)
        self.assertIn(SOURCE, gw.prompts[0])
        self.assertNotIn("{{CONTRACT_TEXT}}", gw.prompts[0])
        self.assertEqual(clean["合同金额"], {"value": "5.1：人民币1200万元"})
        self.assertEqual(clean["保修期"], {"value": None})
        self.assertEqual(grounded["fields"]["合同金额"]["grounding"], "verified")
        self.assertEqual(grounded["fields"]["保修期"]["grounding"], "empty")
        self.assertEqual(grounded["summary"], {"verified": 2, "empty": 1})

    def test_invented_value_is_flagged_retried_and_kept_marked(self):
        bad = {"合同金额": {"value": "人民币1500万元", "evidence": ["合同价款为人民币1500万元"]}}
        gw, clean, grounded = run([bad, bad])
        self.assertEqual(len(gw.prompts), 2)                     # 补抽了一轮
        self.assertIn("没能在原文中逐字找到：合同金额", gw.prompts[1])
        self.assertEqual(grounded["fields"]["合同金额"]["grounding"], "unverified")
        self.assertEqual(clean["合同金额"]["value"], "人民币1500万元")  # 不静默丢弃

    def test_retry_fixes_the_field(self):
        bad = {"合同金额": {"value": "人民币1500万元", "evidence": ["合同价款为人民币1500万元"]}}
        gw, clean, grounded = run([bad, self.GOOD])
        self.assertEqual(grounded["fields"]["合同金额"]["grounding"], "verified")
        self.assertEqual(clean["合同金额"]["value"], "5.1：人民币1200万元")

    def test_missing_evidence_and_legacy_format(self):
        gw, clean, grounded = run([{"施工工期": {"value": "270日历天"}}], extra_passes=0)
        self.assertEqual(grounded["fields"]["施工工期"]["grounding"], "no_evidence")
        self.assertEqual(len(gw.prompts), 1)

    def test_number_not_in_source_downgrades_to_partial(self):
        reply = {"施工工期": {"value": "300日历天", "evidence": ["工期270日历天"]}}
        _, _, grounded = run([reply], extra_passes=0)
        field = grounded["fields"]["施工工期"]
        self.assertEqual(field["grounding"], "partial")
        self.assertTrue(any("300" in w for w in field["warnings"]))

    def test_long_source_is_chunked_and_merged(self):
        lines = [f"第{i}条 一般约定" for i in range(60)] + ["保修期为二年。"]
        source = "\n".join(lines)
        replies = [{"保修期": {"value": None, "evidence": []}}] * 3 + [
            {"保修期": {"value": "二年", "evidence": ["保修期为二年"]}}]
        gw, clean, grounded = run(replies, source=source, max_chars=200, overlap=40, extra_passes=0)
        self.assertGreater(grounded["chunks"], 1)
        self.assertEqual(len(gw.prompts), grounded["chunks"])
        self.assertIn("第 1/", gw.prompts[0])
        self.assertEqual(clean["保修期"]["value"], "二年")
        self.assertEqual(grounded["fields"]["保修期"]["grounding"], "verified")


if __name__ == "__main__":
    unittest.main()
