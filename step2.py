# -*- coding: utf-8 -*-

"""
STEP 2
============================================================

正式合同 PDF / DOCX / TXT
    ↓
转换 TEXT
    ↓
保存 contract_contract_section.txt
    ↓
读取 prompts/extract_contract.txt
    ↓
Prompt + 完整合同文本
    ↓
一次性发送 AI
    ↓
AI 返回 JSON
    ↓
JSON 校验
    ↓
output/contract_result.json
"""

from pathlib import Path

from contract_ai import (
    BASE_DIR,
    OUTPUT_DIR,
    extract_pdf_text,
    write_text_file,
    load_prompt,
    save_json,
    parse_ai_json,
)


class Step2Processor:

    def __init__(self, gateway, provider):
        self.gateway = gateway
        self.provider = provider

    # ========================================================
    # 文件 → TEXT
    # ========================================================

    def file_to_text(self, input_path):

        input_path = Path(input_path)

        if not input_path.exists():
            raise FileNotFoundError(
                f"输入文件不存在：{input_path}"
            )

        suffix = input_path.suffix.lower()

        # ====================================================
        # PDF
        # ====================================================

        if suffix == ".pdf":

            print()
            print("文件类型：PDF")
            print("正在提取 PDF 文本...")

            text = extract_pdf_text(
                input_path
            )

            return text

        # ====================================================
        # DOCX
        # ====================================================

        elif suffix == ".docx":

            print()
            print("文件类型：DOCX")
            print("正在读取 DOCX 文本...")

            try:
                from docx import Document

            except ImportError:

                raise ImportError(
                    "缺少 python-docx，请执行：pip install python-docx"
                )

            document = Document(
                str(input_path)
            )

            paragraphs = []

            # ------------------------------------------------
            # 普通段落
            # ------------------------------------------------

            for paragraph in document.paragraphs:

                text = paragraph.text.strip()

                if text:
                    paragraphs.append(text)

            # ------------------------------------------------
            # 表格
            # ------------------------------------------------

            for table in document.tables:

                for row in table.rows:

                    cells = []

                    for cell in row.cells:

                        cell_text = (
                            cell.text
                            .replace("\n", " ")
                            .strip()
                        )

                        cells.append(
                            cell_text
                        )

                    row_text = " | ".join(
                        cells
                    )

                    if row_text.strip():

                        paragraphs.append(
                            row_text
                        )

            text = "\n".join(
                paragraphs
            )

            return text

        # ====================================================
        # TXT
        # ====================================================

        elif suffix == ".txt":

            print()
            print("文件类型：TXT")
            print("正在读取 TXT...")

            return input_path.read_text(
                encoding="utf-8"
            )

        # ====================================================
        # 不支持
        # ====================================================

        else:

            raise ValueError(
                f"不支持的文件类型：{suffix}\n"
                f"支持：PDF / DOCX / TXT"
            )

    # ========================================================
    # 主流程
    # ========================================================

    def run(self, input_path):

        print()
        print("=" * 70)
        print("STEP 2：正式合同分析")
        print("=" * 70)

        input_path = Path(
            input_path
        )

        print()
        print(
            f"输入文件：{input_path}"
        )

        # ====================================================
        # 1. 文件 → TEXT
        # ====================================================

        contract_text = self.file_to_text(
            input_path
        )

        if not contract_text.strip():

            raise ValueError(
                "合同文本为空，无法进行 AI 分析"
            )

        print()
        print(
            f"合同文本长度："
            f"{len(contract_text)} 字符"
        )

        # ====================================================
        # 2. 保存合同 TXT
        # ====================================================

        output_txt = (
            OUTPUT_DIR
            / "contract_contract_section.txt"
        )

        write_text_file(
            output_txt,
            contract_text
        )

        print()
        print(
            f"合同 TXT：{output_txt}"
        )

        # ====================================================
        # 3. 读取 Prompt
        # ====================================================

        prompt_template = load_prompt(
            "extract_contract.txt"
        )

        prompt_path = (
            BASE_DIR
            / "prompts"
            / "extract_contract.txt"
        )

        print(
            f"Prompt：{prompt_path}"
        )

        # ====================================================
        # 4. Prompt + 完整合同文本
        # ====================================================

        prompt = (
            prompt_template
            + "\n\n"
            + "以下是正式合同原文："
            + "\n\n"
            + contract_text
        )

        print()
        print(
            "完整合同一次性发送 AI"
        )

        print(
            f"Prompt 总长度："
            f"{len(prompt)} 字符"
        )

        # ====================================================
        # 5. AI
        # ====================================================

        print()
        print(
            "正在调用 AI..."
        )

        ai_text = self.gateway.request_with_retry(
            self.provider,
            prompt
        )

        if not ai_text:

            raise ValueError(
                "AI 没有返回内容"
            )

        print()
        print(
            f"AI 返回长度："
            f"{len(ai_text)} 字符"
        )

        # ====================================================
        # 6. AI结果 → JSON
        # ====================================================

        print()
        print(
            "正在解析 AI JSON..."
        )

        try:

            result = parse_ai_json(
                ai_text
            )

        except Exception as e:

            print()
            print("=" * 70)
            print("AI 返回内容无法解析为 JSON")
            print("=" * 70)

            print()
            print(
                f"错误：{e}"
            )

            print()
            print("AI 原始返回：")
            print("-" * 70)

            print(
                ai_text
            )

            print("-" * 70)

            # ------------------------------------------------
            # 保存原始 AI 返回
            # ------------------------------------------------

            raw_output = (
                OUTPUT_DIR
                / "contract_ai_raw.txt"
            )

            write_text_file(
                raw_output,
                ai_text
            )

            print()
            print(
                f"AI 原始结果已保存："
                f"{raw_output}"
            )

            raise

        # ====================================================
        # 7. 保存 JSON
        # ====================================================

        output_json = (
            OUTPUT_DIR
            / "contract_result.json"
        )

        save_json(
            output_json,
            result
        )

        # ====================================================
        # 8. 完成
        # ====================================================

        print()
        print("=" * 70)
        print("STEP 2 完成")
        print("=" * 70)

        print(
            f"合同 TXT：{output_txt}"
        )

        print(
            f"JSON 结果：{output_json}"
        )

        print("=" * 70)

        return result