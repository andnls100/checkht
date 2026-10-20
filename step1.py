# -*- coding: utf-8 -*-

"""
STEP 1
============================================================

招标PDF
    ↓
PDF → TEXT
    ↓
提取合同条款
    ↓
保存 bid_contract_section.txt
    ↓
读取 prompts/extract_bid.txt
    ↓
将合同文本注入 {{CONTRACT_TEXT}}
    ↓
完整合同条款一次性发送AI
    ↓
AI返回JSON
    ↓
解析JSON
    ↓
保存 output/bid_result.json
"""

from pathlib import Path

from grounding import extract_fields, print_summary

from contract_ai import (
    BASE_DIR,
    OUTPUT_DIR,
    extract_pdf_text,
    extract_contract_section,
    write_text_file,
    load_prompt,
    save_json,
    parse_ai_json,
)


class Step1Processor:

    def __init__(
        self,
        gateway,
        provider
    ):
        self.gateway = gateway
        self.provider = provider

    def run(
        self,
        pdf_path
    ):

        print()
        print("=" * 70)
        print("STEP 1：招标文件分析")
        print("=" * 70)

        # ====================================================
        # 1. PDF → TEXT
        # ====================================================

        print()
        print("[1/8] 正在读取PDF...")

        full_text = extract_pdf_text(
            pdf_path
        )

        if not full_text:
            raise RuntimeError(
                "PDF提取结果为空，无法继续处理。"
            )

        print(
            f"PDF文本长度：{len(full_text)} 字符"
        )

        # ====================================================
        # 2. 提取合同条款
        # ====================================================

        print()
        print("[2/8] 正在提取合同条款...")

        contract_text = extract_contract_section(
            full_text
        )

        if not contract_text:
            raise RuntimeError(
                "未提取到合同条款，无法继续处理。"
            )

        print(
            f"合同条款长度：{len(contract_text)} 字符"
        )

        # ====================================================
        # 3. 保存合同条款TXT
        # ====================================================

        print()
        print("[3/8] 正在保存合同条款TXT...")

        output_txt = (
            OUTPUT_DIR
            / "bid_contract_section.txt"
        )

        write_text_file(
            output_txt,
            contract_text
        )

        print(
            f"合同条款TXT：{output_txt}"
        )

        # ====================================================
        # 4. 读取Prompt
        # ====================================================

        print()
        print("[4/8] 正在读取Prompt...")

        prompt_template = load_prompt(
            "extract_bid.txt"
        )

        if not prompt_template:
            raise RuntimeError(
                "extract_bid.txt 内容为空。"
            )

        prompt_path = (
            BASE_DIR
            / "prompts"
            / "extract_bid.txt"
        )

        print(
            f"Prompt：{prompt_path}"
        )

        # ====================================================
        # 5-7. 分块（长文）→ AI 抽取 → 原文定位 → 补抽
        #
        # 每个字段带 evidence（逐字摘自原文），程序在原文里
        # 找到它的位置；找不到的字段标记 unverified 并补抽一轮。
        # extract_bid.txt 里的 {{CONTRACT_TEXT}} 由 grounding 注入。
        # ====================================================

        print()
        print("[5-7/8] AI抽取 + 原文定位...")

        print(
            f"AI：{self.provider}"
        )

        result, grounded = extract_fields(
            self.gateway,
            self.provider,
            prompt_template,
            contract_text,
            parse=parse_ai_json
        )

        print_summary(
            grounded
        )

        # ====================================================
        # 8. 保存JSON
        # ====================================================

        print()
        print("[8/8] 正在保存结果...")

        output_json = (
            OUTPUT_DIR
            / "bid_result.json"
        )

        save_json(
            output_json,
            result
        )

        grounded_json = (
            OUTPUT_DIR
            / "bid_result.grounded.json"
        )

        save_json(
            grounded_json,
            grounded
        )

        print(
            f"原文定位结果：{grounded_json}"
        )

        # ====================================================
        # 完成
        # ====================================================

        print()
        print("=" * 70)
        print("STEP 1完成")
        print("=" * 70)

        print(
            f"合同条款：{output_txt}"
        )

        print(
            f"AI结果：{output_json}"
        )

        print(
            "=" * 70
        )

        return result