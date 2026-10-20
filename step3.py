 
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
from ai_gateway_fix import install as install_gateway_fix


class Step3Processor:
    """合同一致性审核处理器。"""

    def __init__(self, gateway, provider):
        # compare 阶段也使用兼容层：统一 max_tokens，并识别空内容/截断。
        self.gateway = install_gateway_fix(gateway)
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
        """分批执行合同一致性审核；单批截断或空响应时递归缩小批次。"""
        print("=" * 60)
        print("STEP 3：合同一致性审核")
        print("=" * 60)

        prompt = self.load_prompt()
        # 通用规则始终发送；金额专项规则仅在当前批次涉及金额字段时发送。
        prompt_parts = prompt.split("\n[金额专项规则]\n", 1)
        general_prompt = prompt_parts[0]
        amount_rules = prompt_parts[1].split("\n## JSON输出", 1)[0].strip() if len(prompt_parts) > 1 else ""
        bid_data = load_json(self.bid_json_path)
        contract_data = load_json(self.contract_json_path)
        if not isinstance(bid_data, dict) or not isinstance(contract_data, dict):
            raise ValueError("招标文件和合同文件提取结果必须是 JSON 对象。")

        field_names = list(dict.fromkeys([*bid_data.keys(), *contract_data.keys()]))

        # 按字段实际文本长度动态分批：短字段可多批处理，长字段自动缩小批次。
        # 同时限制字段数，避免单批过多导致输出截断。
        target_data_chars = 6000
        max_fields_per_batch = 8
        batches = []
        current_batch = []
        current_chars = 0
        for field in field_names:
            field_payload = json.dumps(
                {"信息1": bid_data.get(field), "信息2": contract_data.get(field)},
                ensure_ascii=False, separators=(",", ":"), allow_nan=False
            )
            field_chars = len(field_payload)
            if current_batch and (
                current_chars + field_chars > target_data_chars
                or len(current_batch) >= max_fields_per_batch
            ):
                batches.append(current_batch)
                current_batch = []
                current_chars = 0
            current_batch.append(field)
            current_chars += field_chars
        if current_batch:
            batches.append(current_batch)
        if not batches:
            batches = [[]]

        print(f"招标字段数：{len(bid_data)}；合同字段数：{len(contract_data)}")
        print(
            f"比较批次数：{len(batches)}；动态分批目标：每批数据约 {target_data_chars} 字符，"
            f"最多 {max_fields_per_batch} 个字段"
        )
        all_issues = []
        compare_provider = dict(self.provider)
        # 比较阶段关闭深度推理，避免 reasoning 占满输出 token 配额。
        compare_provider["thinking_enabled"] = False

        def compare_batch(fields, batch_no, depth=0):
            if fields:
                bid_subset = {k: bid_data[k] for k in fields if k in bid_data}
                contract_subset = {k: contract_data[k] for k in fields if k in contract_data}
            else:
                bid_subset, contract_subset = bid_data, contract_data

            batch_prompt = general_prompt
            amount_keywords = ("金额", "价款", "报价", "限价", "费率", "下浮率", "保证金", "设计费", "建安工程费", "暂列")
            if amount_rules and any(any(word in str(name) for word in amount_keywords) for name in fields):
                batch_prompt += "\n\n金额专项规则：\n" + amount_rules
            request_prompt = self.build_request_prompt(
                batch_prompt,
                json.dumps(bid_subset, ensure_ascii=False, indent=2, allow_nan=False),
                json.dumps(contract_subset, ensure_ascii=False, indent=2, allow_nan=False)
            )
            print(f"正在审核第 {batch_no} 批，字段数：{len(fields) if fields else len(field_names)}")
            try:
                response = self.gateway.request_sync(compare_provider, request_prompt)
                response_text = self.extract_response_text(response)
                if not response_text:
                    raise RuntimeError("AI 返回 content 为空")
                result = self.validate_result(response_text)
                return result["问题列表"]
            except Exception as exc:
                retryable = any(token in str(exc).lower() for token in (
                    "finish_reason=length", "被maxtokens截断", "content 为空",
                    "不是合法 json", "不是合法json", "jsondecodeerror"
                ))
                if retryable and len(fields) > 1 and depth < 8:
                    middle = len(fields) // 2
                    print(f"第 {batch_no} 批响应不完整，拆分为 {middle} + {len(fields) - middle} 个字段重试。")
                    return (
                        compare_batch(fields[:middle], batch_no, depth + 1)
                        + compare_batch(fields[middle:], batch_no, depth + 1)
                    )
                raise RuntimeError(f"第 {batch_no} 批审核失败：{exc}") from exc

        for index, fields in enumerate(batches, start=1):
            all_issues.extend(compare_batch(fields, index))

        deduplicated = []
        seen = set()
        for item in all_issues:
            key = (item.get("字段名称"), item.get("判断结果"),
                   item.get("信息1最终值"), item.get("信息2合同值"))
            if key not in seen:
                seen.add(key)
                deduplicated.append(item)

        # 任一方缺少有效值时，原因和字段解释统一简写，避免冗长描述。
        for item in deduplicated:
            if item.get("判断结果") in {"信息1缺少信息", "信息2缺少信息"}:
                item["原因"] = ["无法比较。"]
                item["字段解释"] = "无法比较。"

        result = {"问题总数": len(deduplicated), "问题列表": deduplicated}
        result = self.validate_result(json.dumps(result, ensure_ascii=False))

        print("\\n" + "=" * 60)
        print("AI 审核结果")
        print("=" * 60)
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        print("\\n审核完成。")
        return result


if __name__ == "__main__":
    raise SystemExit(
        "请通过 contract_ai.py 启动，例如："
        "python contract_ai.py compare"
    )
 
