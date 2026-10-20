# -*- coding: utf-8 -*-

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
from ai_gateway_fix import install as install_gateway_fix


class Step1Processor:
    def __init__(self, gateway, provider):
        self.gateway = install_gateway_fix(gateway)
        self.provider = provider

    def run(self, pdf_path):
        print()
        print("=" * 70)
        print("STEP 1：招标文件分析")
        print("=" * 70)

        print()
        print("[1/8] 正在读取PDF...")
        full_text = extract_pdf_text(pdf_path)
        if not full_text:
            raise RuntimeError("PDF提取结果为空，无法继续处理。")
        print(f"PDF文本长度：{len(full_text)} 字符")

        print()
        print("[2/8] 正在提取合同条款...")
        contract_text = extract_contract_section(full_text)
        if not contract_text:
            raise RuntimeError("未提取到合同条款，无法继续处理。")
        print(f"合同条款长度：{len(contract_text)} 字符")

        output_txt = OUTPUT_DIR / "bid_contract_section.txt"
        write_text_file(output_txt, contract_text)
        print(f"合同条款TXT：{output_txt}")

        print()
        print("[4/8] 正在读取Prompt...")
        prompt_template = load_prompt("extract_bid.txt")
        if not prompt_template:
            raise RuntimeError("extract_bid.txt 内容为空。")
        print(f"Prompt：{BASE_DIR / 'prompts' / 'extract_bid.txt'}")

        print()
        print("[5-7/8] AI抽取 + 原文定位...")
        result, grounded = extract_fields(
            self.gateway,
            self.provider,
            prompt_template,
            contract_text,
            parse=parse_ai_json,
        )
        print_summary(grounded)

        output_json = OUTPUT_DIR / "bid_result.json"
        save_json(output_json, result)
        grounded_json = OUTPUT_DIR / "bid_result.grounded.json"
        save_json(grounded_json, grounded)

        print()
        print("=" * 70)
        print("STEP 1完成")
        print("=" * 70)
        print(f"合同条款：{output_txt}")
        print(f"AI结果：{output_json}")
        print(f"原文定位结果：{grounded_json}")
        print("=" * 70)
        return result
