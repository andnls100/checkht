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
        # 5. 将合同文本注入Prompt
        #
        # extract_bid.txt 中必须存在：
        #
        # {{CONTRACT_TEXT}}
        #
        # ====================================================

        print()
        print("[5/8] 正在构造AI Prompt...")

        if "{{CONTRACT_TEXT}}" not in prompt_template:

            raise RuntimeError(
                "extract_bid.txt 中没有找到 "
                "{{CONTRACT_TEXT}} 占位符。"
            )

        prompt = prompt_template.replace(
            "{{CONTRACT_TEXT}}",
            contract_text
        )

        print(
            f"Prompt模板长度："
            f"{len(prompt_template)} 字符"
        )

        print(
            f"合同文本长度："
            f"{len(contract_text)} 字符"
        )

        print(
            f"总Prompt长度："
            f"{len(prompt)} 字符"
        )

        # ====================================================
        # 6. AI
        # ====================================================

        print()
        print("[6/8] 完整合同条款一次性发送AI")

        print(
            f"AI：{self.provider}"
        )

        print(
            f"Prompt长度：{len(prompt)} 字符"
        )

        print(
            "正在请求AI，请稍候..."
        )

        ai_text = self.gateway.request_with_retry(
            self.provider,
            prompt
        )

        # ====================================================
        # 6.1 AI返回结果检查
        # ====================================================

        print()
        print("=" * 70)
        print("AI原始返回检查")
        print("=" * 70)

        if ai_text is None:

            print(
                "AI返回：None"
            )

            raise RuntimeError(
                "AI返回内容为 None。"
                "请检查AI Gateway响应解析。"
            )

        print(
            f"AI返回类型：{type(ai_text).__name__}"
        )

        print(
            f"AI返回长度：{len(ai_text)} 字符"
        )

        print()
        print("AI返回内容：")

        # repr可以看出空字符串、换行等隐藏字符
        print(
            repr(ai_text)
        )

        print("=" * 70)

        # ====================================================
        # 6.2 空返回直接报错
        # ====================================================

        if not str(ai_text).strip():

            raise RuntimeError(
                "AI返回内容为空。"
                "\n"
                "当前问题不是JSON解析问题，"
                "而是AI Gateway没有取得有效的模型输出。"
                "\n"
                "请检查 request_with_retry() 的响应解析。"
            )

        # ====================================================
        # 7. AI结果 → JSON
        # ====================================================

        print()
        print("[7/8] 正在解析AI JSON...")

        try:

            result = parse_ai_json(
                ai_text
            )

        except Exception as e:

            print()
            print("=" * 70)
            print("JSON解析失败")
            print("=" * 70)

            print(
                f"错误：{e}"
            )

            print()
            print("AI原始返回：")
            print(
                repr(ai_text)
            )

            print("=" * 70)

            raise

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