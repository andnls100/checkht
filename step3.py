 
# -*- coding: utf-8 -*-

"""
STEP 3：合同一致性审核

输入文件：
    output/bid_result.json
    output/contract_result.json

提示词：
    prompts/compare.txt

说明：
    1. 调用 AI 执行审核。
    2. 不读取 infor.txt。
    3. 不合并补充信息。
    4. 不生成 compare_result.txt。
    5. AI 返回结果必须是合法 JSON。
"""

import json
from pathlib import Path

from contract_ai import OUTPUT_DIR, load_json


class Step3Processor:
    """合同一致性审核处理器。"""

    def __init__(self, gateway, provider):
        self.gateway = gateway
        self.provider = provider

        self.output_dir = Path(OUTPUT_DIR)
        self.project_dir = self.output_dir.parent

        self.prompt_path = (
            self.project_dir / "prompts" / "compare.txt"
        )
        self.bid_json_path = (
            self.output_dir / "bid_result.json"
        )
        self.contract_json_path = (
            self.output_dir / "contract_result.json"
        )

    def load_prompt(self):
        """读取审核提示词。"""

        if not self.prompt_path.is_file():
            raise FileNotFoundError(
                f"找不到提示词文件：{self.prompt_path}"
            )

        prompt = self.prompt_path.read_text(
            encoding="utf-8"
        ).strip()

        if not prompt:
            raise ValueError("compare.txt 内容为空。")

        return prompt

    @staticmethod
    def read_json_file(file_path):
        """读取 JSON 文件。"""

        file_path = Path(file_path)

        if not file_path.is_file():
            raise FileNotFoundError(
                f"找不到输入文件：{file_path}"
            )

        data = load_json(file_path)

        if data is None:
            raise ValueError(
                f"JSON 文件读取失败或内容为空：{file_path}"
            )

        return json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
            allow_nan=False
        )

    @staticmethod
    def build_request_prompt(
        prompt,
        bid_json,
        contract_json
    ):
        """构建 AI 请求内容。"""

        return f"""
{prompt}

====================
信息1：招标文件提取结果
====================

{bid_json}

====================
信息2：合同文件提取结果
====================

{contract_json}

====================
本次执行要求
====================

1. 只允许使用以上两份 JSON 进行审核。
2. 不读取或引用 infor.txt。
3. 不对信息1进行补充、合并或改写。
4. 信息1最终值必须依据招标文件原始字段。
5. 信息2合同值必须依据合同文件原始字段。
6. 遵守 compare.txt 中的全部审核规则。
7. 不得强行匹配无法明确对应的字段。
8. 返回完整、合法的 JSON。
9. 不得使用 Markdown 代码块。
10. 不得输出 JSON 以外的内容。
""".strip()

    @staticmethod
    def extract_response_text(response):
        """提取 AI 响应文本。"""

        if isinstance(response, str):
            return response.strip()

        if not isinstance(response, dict):
            raise TypeError(
                "AI 响应类型错误："
                f"{type(response).__name__}"
            )

        choices = response.get("choices")

        if isinstance(choices, list) and choices:
            message = choices[0].get("message", {})
            content = message.get("content")

            if isinstance(content, str):
                return content.strip()

            if isinstance(content, list):
                text_parts = []

                for item in content:
                    if (
                        isinstance(item, dict)
                        and item.get("type") == "text"
                    ):
                        text_parts.append(
                            item.get("text", "")
                        )

                if text_parts:
                    return "\n".join(text_parts).strip()

        content = response.get("content")

        if isinstance(content, str):
            return content.strip()

        raise ValueError(
            "无法从 AI 响应中提取文本，请检查 "
            "AIGateway.request_sync() 的返回格式。"
        )

    @staticmethod
    def validate_result(response_text):
        """校验 AI 返回的 JSON 结构。"""

        text = response_text.strip()

        if text.startswith("```"):
            lines = text.splitlines()

            if (
                lines
                and lines[0].strip().startswith("```")
            ):
                lines = lines[1:]

            if (
                lines
                and lines[-1].strip() == "```"
            ):
                lines = lines[:-1]

            text = "\n".join(lines).strip()

        try:
            result = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(
                "AI 返回的内容不是合法 JSON。\n"
                f"错误位置：第 {exc.lineno} 行，"
                f"第 {exc.colno} 列。\n"
                f"错误信息：{exc.msg}\n"
                f"AI 原始响应：\n{response_text}"
            ) from exc

        if not isinstance(result, dict):
            raise ValueError("AI 返回结果必须是 JSON 对象。")

        if "问题总数" not in result:
            raise ValueError("返回结果缺少“问题总数”字段。")

        if "问题列表" not in result:
            raise ValueError("返回结果缺少“问题列表”字段。")

        if not isinstance(result["问题总数"], int):
            raise ValueError("“问题总数”必须是整数。")

        if not isinstance(result["问题列表"], list):
            raise ValueError("“问题列表”必须是数组。")

        if result["问题总数"] != len(result["问题列表"]):
            raise ValueError(
                "“问题总数”与“问题列表”的实际长度不一致。"
            )

        required_fields = [
            "字段名称",
            "判断结果",
            "信息1最终值",
            "信息2合同值",
            "原因",
            "字段解释",
        ]

        allowed_judgments = {
            "不一致",
            "信息1缺少信息",
            "信息2缺少信息",
            "无法明确核验",
        }

        for index, item in enumerate(
            result["问题列表"],
            start=1
        ):
            if not isinstance(item, dict):
                raise ValueError(
                    f"问题列表第 {index} 项必须是 JSON 对象。"
                )

            for field in required_fields:
                if field not in item:
                    raise ValueError(
                        f"问题列表第 {index} 项缺少字段：{field}"
                    )

            if item["判断结果"] not in allowed_judgments:
                raise ValueError(
                    f"问题列表第 {index} 项的判断结果不合法："
                    f"{item['判断结果']}"
                )

            if not isinstance(item["原因"], list):
                raise ValueError(
                    f"问题列表第 {index} 项的“原因”必须是数组。"
                )

            if not all(
                isinstance(reason, str)
                for reason in item["原因"]
            ):
                raise ValueError(
                    f"问题列表第 {index} 项的“原因”"
                    "只能包含字符串。"
                )

        return result

    def run(self):
        """执行合同一致性审核。"""

        print("=" * 60)
        print("STEP 3：合同一致性审核")
        print("=" * 60)

        prompt = self.load_prompt()

        bid_json = self.read_json_file(
            self.bid_json_path
        )

        contract_json = self.read_json_file(
            self.contract_json_path
        )

        request_prompt = self.build_request_prompt(
            prompt,
            bid_json,
            contract_json
        )

        print("正在调用 AI 进行合同一致性审核...")

        response = self.gateway.request_sync(
            self.provider,
            request_prompt
            
        )

        response_text = self.extract_response_text(
            response
        )

        result = self.validate_result(response_text)

        print("\n" + "=" * 60)
        print("AI 审核结果")
        print("=" * 60)

        print(
            json.dumps(
                result,
                ensure_ascii=False,
                indent=2,
                allow_nan=False
            )
        )

        print("\n审核完成。")
        return result


if __name__ == "__main__":
    raise SystemExit(
        "请通过 contract_ai.py 启动，例如："
        "python contract_ai.py compare"
    )
 
