# -*- coding: utf-8 -*-

"""
CONTRACT AI
============================================================

主程序 + 公共工具

流程：

STEP1：
    招标PDF
        ↓
    PDF → TEXT
        ↓
    提取合同条款
        ↓
    prompts/extract_bid.txt
        ↓
    AI一次性分析完整合同条款
        ↓
    output/bid_result.json


STEP2：
    正式合同PDF
        ↓
    PDF → TEXT
        ↓
    提取合同条款
        ↓
    prompts/extract_contract.txt
        ↓
    AI一次性分析完整合同条款
        ↓
    output/contract_result.json


STEP3：
    output/bid_result.json
    +
    output/contract_result.json
    +
    input/xxx.txt
    +
    prompts/compare.txt
        ↓
    AI一次性比较
        ↓
    output/compare_result.json


运行：

python contract_ai.py extract_bid 招标文件.pdf

python contract_ai.py extract_contract 正式合同.pdf

python contract_ai.py compare

或者：

python contract_ai.py compare --input input/compare.txt

指定Provider：

python contract_ai.py extract_bid 招标文件.pdf --provider zhipu

依赖：

pip install pymupdf requests
"""

import argparse
import json
import re
import sys
import time
import traceback
from pathlib import Path

import requests


# ============================================================
# 项目目录
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

CONFIG_DIR = BASE_DIR / "config"
PROMPT_DIR = BASE_DIR / "prompts"
OUTPUT_DIR = BASE_DIR / "output"
INPUT_DIR = BASE_DIR / "input"

CONFIG_DIR.mkdir(parents=True, exist_ok=True)
PROMPT_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
INPUT_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# 全局配置
# ============================================================

DEFAULT_TIMEOUT = 180

DEBUG = True


# ============================================================
# 文件工具
# ============================================================

def read_text_file(path):
    """
    读取TXT。
    自动尝试常见中文编码。
    """

    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(
            f"文件不存在：{path}"
        )

    data = path.read_bytes()

    encodings = [
        "utf-8-sig",
        "utf-8",
        "gb18030",
        "gbk",
        "cp936",
    ]

    last_error = None

    for encoding in encodings:
        try:
            return data.decode(encoding)
        except UnicodeDecodeError as e:
            last_error = e

    raise RuntimeError(
        f"无法识别文本文件编码：{path}\n"
        f"最后错误：{last_error}"
    )


def write_text_file(path, text):
    path = Path(path)

    path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    path.write_text(
        text,
        encoding="utf-8"
    )


def save_json(path, data):
    path = Path(path)

    path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with open(
        path,
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2
        )


def load_json(path):
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(
            f"JSON文件不存在：{path}"
        )

    with open(
        path,
        "r",
        encoding="utf-8"
    ) as f:
        return json.load(f)


# ============================================================
# Prompt
# ============================================================

def load_prompt(filename):
    """
    从 prompts 目录读取提示词。
    """

    path = PROMPT_DIR / filename

    if not path.exists():
        raise FileNotFoundError(
            f"Prompt不存在：{path}"
        )

    return read_text_file(path)


# ============================================================
# PDF → TEXT
# ============================================================

def extract_pdf_text(pdf_path):

    pdf_path = Path(pdf_path)

    if not pdf_path.exists():
        raise FileNotFoundError(
            f"PDF不存在：{pdf_path}"
        )

    if pdf_path.suffix.lower() != ".pdf":
        raise RuntimeError(
            f"输入文件不是PDF：{pdf_path}"
        )

    try:
        import fitz
    except ImportError:
        raise RuntimeError(
            "缺少PyMuPDF。\n"
            "请安装：pip install pymupdf"
        )

    print()
    print("=" * 70)
    print("PDF → TEXT")
    print("=" * 70)

    print(
        f"PDF：{pdf_path}"
    )

    pages = []

    try:
        document = fitz.open(
            str(pdf_path)
        )
    except Exception as e:
        raise RuntimeError(
            f"PDF打开失败：{e}"
        )

    try:

        total_pages = len(document)

        print(
            f"PDF页数：{total_pages}"
        )

        for page_index in range(
            total_pages
        ):

            page = document[
                page_index
            ]

            text = page.get_text(
                "text"
            )

            if text:
                pages.append(text)

    finally:
        document.close()

    full_text = "\n".join(pages)

    full_text = full_text.replace(
        "\x00",
        ""
    )

    full_text = full_text.replace(
        "\r\n",
        "\n"
    )

    full_text = full_text.replace(
        "\r",
        "\n"
    )

    full_text = re.sub(
        r"\n{4,}",
        "\n\n",
        full_text
    )

    full_text = full_text.strip()

    print(
        f"PDF文本提取完成："
        f"{len(full_text)} 字符"
    )

    if not full_text:
        raise RuntimeError(
            "PDF没有提取出任何文字。\n"
            "如果这是扫描件，需要OCR。"
        )

    return full_text


# ============================================================
# 章节识别
# ============================================================

def parse_chapter_number(line):

    line = line.strip()

    match = re.match(
        r"^第([一二三四五六七八九十百千万零〇两]+)章\b",
        line
    )

    if not match:
        return None

    value = match.group(1)

    numbers = {
        "零": 0,
        "〇": 0,
        "一": 1,
        "二": 2,
        "两": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
        "十": 10,
        "百": 100,
        "千": 1000,
        "万": 10000,
    }

    if len(value) == 1:
        return numbers.get(value)

    if value == "十":
        return 10

    if value.startswith("十"):
        tail = value[1:]

        return (
            10
            + numbers.get(
                tail,
                0
            )
        )

    if value.endswith("十"):
        head = value[:-1]

        if head in numbers:
            return numbers[head] * 10

    if "十" in value:

        parts = value.split("十")

        if len(parts) == 2:

            if parts[0]:
                tens = numbers.get(
                    parts[0],
                    0
                )
            else:
                tens = 1

            if parts[1]:
                ones = numbers.get(
                    parts[1],
                    0
                )
            else:
                ones = 0

            return tens * 10 + ones

    return None


def is_top_level_chapter(line):

    line = line.strip()

    return bool(
        re.match(
            r"^第[一二三四五六七八九十百千万零〇两]+章\b",
            line
        )
    )


def is_contract_chapter(line):

    if not is_top_level_chapter(line):
        return False

    return "合同条款" in line


def looks_like_toc_line(line):

    line = line.strip()

    if not line:
        return False

    if re.search(
        r"\.{3,}",
        line
    ):
        return True

    if "……" in line:
        return True

    if re.search(
        r"合同条款\s*\d{1,4}$",
        line
    ):
        return True

    return False


import re


CHAPTER_PATTERN = re.compile(
    r"^\s*第\s*([一二三四五六七八九十百零\d]+)\s*章\s*(.*)$"
)


def find_all_chapters(text):

    chapters = []

    lines = text.splitlines()

    pos = 0

    for line in lines:

        match = CHAPTER_PATTERN.match(line)

        if match:

            number = match.group(1)
            title = match.group(2).strip()

            chapters.append(
                {
                    "number": number,
                    "title": f"第{number}章 {title}",
                    "start": pos,
                    "toc": False
                }
            )

        pos += len(line) + 1


    return chapters

    chapters = []

    offset = 0

    for line in text.splitlines(
        keepends=True
    ):

        stripped = line.strip()

        if is_top_level_chapter(
            stripped
        ):

            number = parse_chapter_number(
                stripped
            )

            chapters.append({

                "number": number,

                "title": stripped,

                "start": offset,

                "toc": looks_like_toc_line(
                    stripped
                )
            })

        offset += len(line)

    return chapters


# ============================================================
# 查找合同条款开始
# ============================================================

def find_contract_start(text):

    chapters = find_all_chapters(
        text
    )

    candidates = []

    for i, chapter in enumerate(
        chapters
    ):

        if not is_contract_chapter(
            chapter["title"]
        ):
            continue

        start = chapter["start"]

        if i + 1 < len(chapters):
            end = chapters[
                i + 1
            ]["start"]
        else:
            end = len(text)

        length = end - start

        item = dict(chapter)

        item["end"] = end
        item["length"] = length

        candidates.append(
            item
        )

    if not candidates:

        raise RuntimeError(
            "没有找到“第X章 合同条款”。\n\n"
            "程序识别到的一级章节：\n"
            + "\n".join(
                [
                    x["title"]
                    for x in chapters
                ]
            )
        )

    print()
    print(
        f"发现合同条款章节："
        f"{len(candidates)} 个"
    )

    for item in candidates:

        print(
            f"  第{item['number']}章"
            f" | {item['length']}字符"
            f" | {item['title']}"
        )

    good = [
        x
        for x in candidates
        if (
            not x["toc"]
            and
            x["length"] >= 5000
        )
    ]

    if good:

        selected = max(
            good,
            key=lambda x: x["length"]
        )

    else:

        non_toc = [
            x
            for x in candidates
            if not x["toc"]
        ]

        if non_toc:

            selected = max(
                non_toc,
                key=lambda x: x["length"]
            )

        else:

            selected = max(
                candidates,
                key=lambda x: x["length"]
            )

    print(
        f"选择：{selected['title']}"
    )

    return selected


# ============================================================
# 查找合同条款结束
# ============================================================

def find_contract_end(
    text,
    start_info
):

    chapters = find_all_chapters(
        text
    )

    start = start_info["start"]

    for chapter in chapters:

        if chapter["start"] <= start:
            continue

        return chapter["start"]

    return len(text)


# ============================================================
# 截取合同条款
# ============================================================

def extract_contract_section(text):

    start_info = find_contract_start(
        text
    )

    start = start_info["start"]

    end = find_contract_end(
        text,
        start_info
    )

    section = text[
        start:end
    ].strip()

    print(
        f"合同条款截取完成："
        f"{len(section)} 字符"
    )

    if len(section) < 5000:

        print(
            "警告：合同条款长度小于5000字符。"
        )

    return section


class AIGateway:

    def __init__(
        self,
        config_path
    ):

        self.config_path = Path(
            config_path
        )

        if not self.config_path.exists():

            raise FileNotFoundError(
                f"AI配置不存在：{self.config_path}"
            )

        self.config = load_json(
            self.config_path
        )

    # ========================================================
    # Provider
    # ========================================================

    def get_provider(
        self,
        name=None
    ):

        if isinstance(
            self.config,
            dict
        ):

            providers = self.config.get(
                "providers",
                []
            )

        elif isinstance(
            self.config,
            list
        ):

            providers = self.config

        else:

            raise RuntimeError(
                "AI配置格式错误"
            )

        if not isinstance(
            providers,
            list
        ):

            raise RuntimeError(
                "providers必须是数组"
            )

        if not providers:

            raise RuntimeError(
                "没有配置Provider"
            )

        # ----------------------------------------------------
        # 指定Provider
        # ----------------------------------------------------

        if name:

            name = str(
                name
            ).strip()

            for provider in providers:

                if not isinstance(
                    provider,
                    dict
                ):
                    continue

                provider_name = str(
                    provider.get(
                        "name",
                        ""
                    )
                ).strip()

                if (
                    provider_name.lower()
                    ==
                    name.lower()
                ):

                    return provider

            available = [
                str(
                    x.get(
                        "name",
                        ""
                    )
                )
                for x in providers
                if isinstance(
                    x,
                    dict
                )
            ]

            raise RuntimeError(
                f"找不到Provider：{name}\n"
                f"当前可用Provider：{available}"
            )

        # ----------------------------------------------------
        # 默认第一个
        # ----------------------------------------------------

        provider = providers[0]

        if not isinstance(
            provider,
            dict
        ):

            raise RuntimeError(
                "第一个Provider配置格式错误"
            )

        return provider

    # ========================================================
    # API Key
    # ========================================================

    def get_api_key(
        self,
        provider
    ):

        provider_name = provider.get(
            "name",
            "unknown"
        )

        api_keys = provider.get(
            "api_keys"
        )

        if not isinstance(
            api_keys,
            list
        ):

            raise RuntimeError(
                f"Provider {provider_name} "
                f"的api_keys不是list"
            )

        if not api_keys:

            raise RuntimeError(
                f"Provider {provider_name} "
                f"的api_keys为空"
            )

        for item in api_keys:

            if not isinstance(
                item,
                dict
            ):
                continue

            api_key = item.get(
                "api_key"
            )

            if not isinstance(
                api_key,
                str
            ):
                continue

            api_key = api_key.strip()

            if api_key:

                return api_key

        raise RuntimeError(
            f"Provider {provider_name} "
            f"没有有效API Key"
        )

    # ========================================================
    # Base URL处理
    # ========================================================

    @staticmethod
    def normalize_base_url(
        base_url
    ):

        if not isinstance(
            base_url,
            str
        ):

            raise RuntimeError(
                "base_url必须是字符串"
            )

        base_url = base_url.strip()

        if not base_url:

            raise RuntimeError(
                "Provider缺少base_url"
            )

        # ----------------------------------------------------
        # 删除尾部 /
        # ----------------------------------------------------

        base_url = base_url.rstrip("/")

        # ----------------------------------------------------
        # 用户可能已经写了：
        #
        # /chat/completions
        # ----------------------------------------------------

        suffixes = [
            "/chat/completions",
            "/completions"
        ]

        for suffix in suffixes:

            if base_url.endswith(
                suffix
            ):

                base_url = base_url[
                    :-len(suffix)
                ]

                base_url = base_url.rstrip("/")

        return base_url

    # ========================================================
    # 构造Chat Completions URL
    # ========================================================

    def build_chat_url(
        self,
        provider
    ):

        base_url = self.normalize_base_url(
            provider.get(
                "base_url"
            )
        )

        # ----------------------------------------------------
        # 已经是完整 API v4
        #
        # https://open.bigmodel.cn/api/paas/v4
        # ----------------------------------------------------

        if base_url.endswith(
            "/v4"
        ):

            return (
                base_url
                + "/chat/completions"
            )

        # ----------------------------------------------------
        # 已经是 /v1
        #
        # OpenAI兼容平台
        # ----------------------------------------------------

        if base_url.endswith(
            "/v1"
        ):

            return (
                base_url
                + "/chat/completions"
            )

        # ----------------------------------------------------
        # 阿里百炼 / 其他兼容接口
        #
        # 如果用户已经配置完整API路径，
        # 这里不擅自添加路径。
        # ----------------------------------------------------

        return (
            base_url
            + "/chat/completions"
        )

    # ========================================================
    # 安全显示响应
    # ========================================================

    @staticmethod
    def get_response_text(
        response
    ):

        try:

            text = response.text

        except Exception:

            return "<无法读取服务器响应>"

        if not text:

            return "<服务器没有返回内容>"

        # 防止服务器返回几十MB导致终端爆炸
        max_length = 12000

        if len(text) > max_length:

            return (
                text[:max_length]
                + "\n\n"
                + "......服务器返回内容过长，"
                + "这里只显示前12000字符......"
            )

        return text

    # ========================================================
    # 提取Request ID
    # ========================================================

    @staticmethod
    def get_request_id(
        response,
        data=None
    ):

        request_id = None

        try:

            request_id = response.headers.get(
                "X-Request-ID"
            )

        except Exception:
            pass

        if not request_id:

            try:

                request_id = response.headers.get(
                    "request-id"
                )

            except Exception:
                pass

        if not request_id and isinstance(
            data,
            dict
        ):

            request_id = (
                data.get("request_id")
                or
                data.get("id")
            )

        return request_id

    # ========================================================
    # 请求
    # ========================================================

    def request_sync(
        self,
        provider,
        prompt,
        system_prompt=None,
        retry_index=0
    ):

        provider_name = str(
            provider.get(
                "name",
                "unknown"
            )
        ).strip()

        model = provider.get(
            "model"
        )

        if not model:
            raise RuntimeError(
                "Provider缺少model"
            )

        model = str(model).strip()

        api_key = self.get_api_key(
            provider
        )

        url = self.build_chat_url(
            provider
        )

        # ========================================================
        # 参数
        # ========================================================

        timeout = provider.get(
            "timeout",
            300
        )

        try:
            timeout = int(timeout)
        except Exception:
            timeout = 300

        max_tokens = provider.get(
            "max_tokens",
            8192
        )

        try:
            max_tokens = int(max_tokens)
        except Exception:
            max_tokens = 8192

        temperature = provider.get(
            "temperature",
            0.1
        )

        try:
            temperature = float(
                temperature
            )
        except Exception:
            temperature = 0.1

        # ========================================================
        # messages
        # ========================================================

        messages = []

        if system_prompt:

            messages.append({
                "role": "system",
                "content": system_prompt
            })

        messages.append({
            "role": "user",
            "content": prompt
        })

        # ========================================================
        # payload
        # ========================================================

        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }

        # 某些接口要求 max_completion_tokens
        if provider.get(
            "use_max_completion_tokens",
            False
        ):

            payload.pop(
                "max_tokens",
                None
            )

            payload[
                "max_completion_tokens"
            ] = max_tokens

        headers = {
            "Authorization":
                f"Bearer {api_key}",

            "Content-Type":
                "application/json",

            "Accept":
                "application/json",

            "User-Agent":
                "contract-ai/1.0"
        }

        # ========================================================
        # 请求前日志
        # ========================================================

        print()
        print("=" * 80)
        print("AI REQUEST")
        print("=" * 80)

        print(
            f"Provider      : {provider_name}"
        )

        print(
            f"Model         : {model}"
        )

        print(
            f"URL           : {url}"
        )

        print(
            f"Prompt长度    : {len(prompt)} 字符"
        )

        print(
            f"Max tokens    : {max_tokens}"
        )

        print(
            f"Timeout       : {timeout}s"
        )

        print(
            f"Retry         : {retry_index + 1}"
        )

        print("=" * 80)

        # ========================================================
        # HTTP请求
        # ========================================================

        try:

            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=(
                    30,
                    timeout
                )
            )

        except requests.exceptions.Timeout as e:

            print()
            print("=" * 80)
            print("AI REQUEST TIMEOUT")
            print("=" * 80)

            print(
                repr(e)
            )

            print("=" * 80)

            raise RuntimeError(
                f"AI请求超时：{e}"
            )

        except requests.exceptions.ConnectionError as e:

            print()
            print("=" * 80)
            print("AI CONNECTION ERROR")
            print("=" * 80)

            print(
                repr(e)
            )

            print("=" * 80)

            raise RuntimeError(
                f"AI连接失败：{e}"
            )

        except requests.exceptions.RequestException as e:

            print()
            print("=" * 80)
            print("AI REQUEST ERROR")
            print("=" * 80)

            print(
                f"类型：{type(e).__name__}"
            )

            print(
                repr(e)
            )

            print("=" * 80)

            raise RuntimeError(
                f"AI请求异常：{e}"
            )

        # ========================================================
        # HTTP响应
        # ========================================================

        print()
        print("=" * 80)
        print("AI RESPONSE")
        print("=" * 80)

        print(
            f"HTTP Status：{response.status_code}"
        )

        print(
            f"URL：{url}"
        )

        # ========================================================
        # Headers
        # ========================================================

        print()
        print("Response Headers:")

        for key, value in response.headers.items():

            # 不打印敏感内容
            print(
                f"  {key}: {value}"
            )

        # ========================================================
        # 原始Response
        # ========================================================

        raw_text = response.text

        print()
        print(
            f"Raw Response Length："
            f"{len(raw_text)}"
        )

        print()
        print("Raw Response repr:")

        print(
            repr(raw_text)
        )

        # ========================================================
        # 如果不是HTTP 2xx
        # ========================================================

        if not response.ok:

            print()
            print("=" * 80)
            print("AI HTTP ERROR")
            print("=" * 80)

            print(
                raw_text
            )

            print("=" * 80)

            raise RuntimeError(
                f"AI HTTP {response.status_code}\n"
                f"{raw_text}"
            )

        # ========================================================
        # JSON解析
        # ========================================================

        try:

            data = response.json()

        except Exception as e:

            print()
            print("=" * 80)
            print("AI RESPONSE JSON PARSE ERROR")
            print("=" * 80)

            print(
                f"错误类型：{type(e).__name__}"
            )

            print(
                f"错误：{e}"
            )

            print()
            print("服务器原始返回：")

            print(
                repr(raw_text)
            )

            print("=" * 80)

            raise RuntimeError(
                "AI服务器返回的不是JSON：\n"
                + raw_text
            )

        # ========================================================
        # 打印完整JSON响应
        # ========================================================

        print()
        print("=" * 80)
        print("AI RESPONSE JSON")
        print("=" * 80)

        try:

            print(
                json.dumps(
                    data,
                    ensure_ascii=False,
                    indent=2
                )
            )

        except Exception:

            print(
                repr(data)
            )

        print("=" * 80)

        # ========================================================
        # usage
        # ========================================================

        usage = data.get(
            "usage"
        )

        if usage:

            print()
            print("Token Usage:")

            print(
                json.dumps(
                    usage,
                    ensure_ascii=False,
                    indent=2
                )
            )

        # ========================================================
        # choices
        # ========================================================

        if "choices" not in data:

            raise RuntimeError(
                "AI响应中没有choices。\n\n"
                "完整响应：\n"
                + json.dumps(
                    data,
                    ensure_ascii=False,
                    indent=2
                )
            )

        choices = data.get(
            "choices"
        )

        if not isinstance(
            choices,
            list
        ):

            raise RuntimeError(
                "AI响应中的choices不是数组。\n\n"
                + json.dumps(
                    data,
                    ensure_ascii=False,
                    indent=2
                )
            )

        if len(choices) == 0:

            raise RuntimeError(
                "AI响应中的choices为空。\n\n"
                + json.dumps(
                    data,
                    ensure_ascii=False,
                    indent=2
                )
            )

        # ========================================================
        # 第一条结果
        # ========================================================

        choice = choices[0]

        print()
        print("=" * 80)
        print("AI CHOICE")
        print("=" * 80)

        print(
            json.dumps(
                choice,
                ensure_ascii=False,
                indent=2
            )
        )

        print("=" * 80)

        # ========================================================
        # message
        # ========================================================

        message = choice.get(
            "message"
        )

        if message is None:

            raise RuntimeError(
                "AI响应中没有message。\n\n"
                + json.dumps(
                    choice,
                    ensure_ascii=False,
                    indent=2
                )
            )

        print()
        print("AI MESSAGE:")

        print(
            json.dumps(
                message,
                ensure_ascii=False,
                indent=2
            )
        )

        # ========================================================
        # content
        # ========================================================

        content = message.get(
            "content"
        )

        print()
        print("=" * 80)
        print("AI CONTENT")
        print("=" * 80)

        print(
            f"content类型："
            f"{type(content).__name__}"
        )

        if content is None:

            print(
                "content = None"
            )

        else:

            print(
                f"content长度："
                f"{len(str(content))}"
            )

            print()
            print("content repr：")

            print(
                repr(content)
            )

            print()
            print("content实际内容：")

            print(
                content
            )

        print("=" * 80)

        # ========================================================
        # content为空
        # ========================================================

        if content is None:

            raise RuntimeError(
                "AI返回content=None。\n\n"
                "完整响应：\n"
                + json.dumps(
                    data,
                    ensure_ascii=False,
                    indent=2
                )
            )

        content = str(
            content
        )

        if not content.strip():

            raise RuntimeError(
                "AI返回content为空字符串。\n\n"
                "完整响应：\n"
                + json.dumps(
                    data,
                    ensure_ascii=False,
                    indent=2
                )
            )

        return content

        provider_name = str(
            provider.get(
                "name",
                "unknown"
            )
        ).strip()

        model = provider.get(
            "model"
        )

        if not model:

            raise RuntimeError(
                "Provider缺少model"
            )

        model = str(
            model
        ).strip()

        api_key = self.get_api_key(
            provider
        )

        url = self.build_chat_url(
            provider
        )

        # ====================================================
        # timeout
        # ====================================================

        timeout = provider.get(
            "timeout",
            DEFAULT_TIMEOUT
        )

        try:

            timeout = int(
                timeout
            )

        except Exception:

            timeout = DEFAULT_TIMEOUT

        # ====================================================
        # max_tokens
        #
        # 不给太大的默认输出。
        #
        # 合同分析通常几千token已经足够。
        # ====================================================

        max_tokens = provider.get(
            "max_tokens",
            8192
        )

        try:

            max_tokens = int(
                max_tokens
            )

        except Exception:

            max_tokens = 8192

        # ====================================================
        # temperature
        # ====================================================

        temperature = provider.get(
            "temperature",
            0.1
        )

        try:

            temperature = float(
                temperature
            )

        except Exception:

            temperature = 0.1

        # ====================================================
        # messages
        # ====================================================

        messages = []

        if system_prompt:

            messages.append({
                "role": "system",
                "content": system_prompt
            })

        messages.append({
            "role": "user",
            "content": prompt
        })

        # ====================================================
        # 请求JSON
        # ====================================================

        payload = {

            "model": model,

            "messages": messages,

            "temperature": temperature,

            "max_tokens": max_tokens
        }

        # ----------------------------------------------------
        # 某些Provider支持max_completion_tokens
        # ----------------------------------------------------

        if provider.get(
            "use_max_completion_tokens",
            False
        ):

            payload.pop(
                "max_tokens",
                None
            )

            payload[
                "max_completion_tokens"
            ] = max_tokens

        headers = {

            "Authorization":
                f"Bearer {api_key}",

            "Content-Type":
                "application/json",

            "Accept":
                "application/json",

            "User-Agent":
                "contract-ai/1.0"
        }

        # ====================================================
        # 调试信息
        # ====================================================

        print()
        print(
            "-" * 70
        )

        print(
            f"Provider     : {provider_name}"
        )

        print(
            f"Model        : {model}"
        )

        print(
            f"URL          : {url}"
        )

        print(
            f"Prompt chars  : {len(prompt)}"
        )

        print(
            f"Max tokens   : {max_tokens}"
        )

        print(
            f"Timeout      : {timeout}s"
        )

        print(
            f"Retry        : {retry_index + 1}"
        )

        print(
            "-" * 70
        )

        # ====================================================
        # HTTP请求
        # ====================================================

        start_time = time.time()

        try:

            response = requests.post(

                url,

                headers=headers,

                json=payload,

                timeout=(
                    30,
                    timeout
                )
            )

        except requests.exceptions.Timeout as e:

            elapsed = time.time() - start_time

            raise RuntimeError(
                "AI请求超时。\n\n"
                f"URL：{url}\n"
                f"连接/读取超时：{timeout}秒\n"
                f"耗时：{elapsed:.1f}秒\n"
                f"错误：{e}"
            )

        except requests.exceptions.ConnectionError as e:

            elapsed = time.time() - start_time

            raise RuntimeError(
                "AI服务器连接失败。\n\n"
                f"URL：{url}\n"
                f"耗时：{elapsed:.1f}秒\n\n"
                f"错误：{e}"
            )

        except requests.exceptions.SSLError as e:

            raise RuntimeError(
                "HTTPS/SSL连接失败。\n\n"
                f"URL：{url}\n\n"
                f"错误：{e}"
            )

        except requests.exceptions.RequestException as e:

            raise RuntimeError(
                "HTTP请求异常。\n\n"
                f"URL：{url}\n\n"
                f"错误类型：{type(e).__name__}\n"
                f"错误：{e}"
            )

        elapsed = (
            time.time()
            - start_time
        )

        # ====================================================
        # HTTP状态
        # ====================================================

        print(
            f"HTTP Status : {response.status_code}"
        )

        print(
            f"Elapsed     : {elapsed:.1f}s"
        )

        # ====================================================
        # 尝试解析JSON
        # ====================================================

        data = None

        try:

            data = response.json()

        except Exception:

            data = None

        request_id = self.get_request_id(
            response,
            data
        )

        if request_id:

            print(
                f"Request ID  : {request_id}"
            )

        # ====================================================
        # HTTP失败
        # ====================================================

        if not response.ok:

            response_text = (
                self.get_response_text(
                    response
                )
            )

            print()
            print(
                "========== AI服务器错误 =========="
            )

            print(
                response_text
            )

            print(
                "===================================="
            )

            # ------------------------------------------------
            # 400
            # ------------------------------------------------

            if response.status_code == 400:

                raise RuntimeError(
                    "HTTP 400 Bad Request。\n\n"
                    "这通常表示：\n"
                    "1. model名称错误\n"
                    "2. 请求参数不兼容\n"
                    "3. 当前模型不支持某个参数\n"
                    "4. 请求格式错误\n"
                    "5. Provider的API地址错误\n\n"
                    f"URL：{url}\n"
                    f"Model：{model}\n"
                    f"服务器返回：\n"
                    f"{response_text}"
                )

            # ------------------------------------------------
            # 401
            # ------------------------------------------------

            if response.status_code == 401:

                raise RuntimeError(
                    "HTTP 401 Unauthorized。\n\n"
                    "API Key认证失败。\n\n"
                    f"Provider：{provider_name}\n"
                    f"Model：{model}\n"
                    f"URL：{url}\n\n"
                    f"服务器返回：\n"
                    f"{response_text}"
                )

            # ------------------------------------------------
            # 403
            # ------------------------------------------------

            if response.status_code == 403:

                raise RuntimeError(
                    "HTTP 403 Forbidden。\n\n"
                    "API Key没有该模型/接口权限。\n\n"
                    f"Provider：{provider_name}\n"
                    f"Model：{model}\n\n"
                    f"服务器返回：\n"
                    f"{response_text}"
                )

            # ------------------------------------------------
            # 404
            # ------------------------------------------------

            if response.status_code == 404:

                raise RuntimeError(
                    "HTTP 404 Not Found。\n\n"
                    "API地址不存在。\n\n"
                    f"URL：{url}\n"
                    f"Model：{model}\n\n"
                    f"服务器返回：\n"
                    f"{response_text}"
                )

            # ------------------------------------------------
            # 429
            # ------------------------------------------------

            if response.status_code == 429:

                raise RuntimeError(
                    "HTTP 429 Too Many Requests。\n\n"
                    "可能是：\n"
                    "1. RPM超限\n"
                    "2. TPM超限\n"
                    "3. 余额/额度不足\n"
                    "4. 并发限制\n\n"
                    f"服务器返回：\n"
                    f"{response_text}"
                )

            # ------------------------------------------------
            # 5xx
            # ------------------------------------------------

            if response.status_code >= 500:

                raise RuntimeError(
                    f"AI服务器错误：HTTP "
                    f"{response.status_code}\n\n"
                    f"服务器返回：\n"
                    f"{response_text}"
                )

            raise RuntimeError(
                f"HTTP {response.status_code}\n\n"
                f"服务器返回：\n"
                f"{response_text}"
            )

        # ====================================================
        # 成功JSON
        # ====================================================

        if data is None:

            raise RuntimeError(
                "HTTP 200，但是服务器返回的不是JSON。\n\n"
                + self.get_response_text(
                    response
                )
            )

        # ====================================================
        # 打印usage
        # ====================================================

        usage = data.get(
            "usage"
        )

        if isinstance(
            usage,
            dict
        ):

            prompt_tokens = usage.get(
                "prompt_tokens"
            )

            completion_tokens = usage.get(
                "completion_tokens"
            )

            total_tokens = usage.get(
                "total_tokens"
            )

            print()
            print(
                "Token Usage"
            )

            print(
                f"  prompt     : "
                f"{prompt_tokens}"
            )

            print(
                f"  completion : "
                f"{completion_tokens}"
            )

            print(
                f"  total      : "
                f"{total_tokens}"
            )

        # ====================================================
        # choices
        # ====================================================

        try:

            choices = data[
                "choices"
            ]

            if not choices:

                raise RuntimeError(
                    "choices为空"
                )

            message = choices[0][
                "message"
            ]

            content = message.get(
                "content"
            )

        except Exception as e:

            raise RuntimeError(
                "AI返回格式异常。\n\n"
                f"解析错误：{e}\n\n"
                + json.dumps(
                    data,
                    ensure_ascii=False,
                    indent=2
                )[:20000]
            )

        if content is None:

            raise RuntimeError(
                "AI返回成功，但是content为空。\n\n"
                + json.dumps(
                    data,
                    ensure_ascii=False,
                    indent=2
                )[:20000]
            )

        if not isinstance(
            content,
            str
        ):

            content = str(
                content
            )

        print()
        print(
            f"AI返回：{len(content)} 字符"
        )

        return content

    # ========================================================
    # 重试
    # ========================================================

    def request_with_retry(
        self,
        provider,
        prompt,
        system_prompt=None
    ):

        try:

            max_retry = int(
                provider.get(
                    "max_retry",
                    3
                )
            )

        except Exception:

            max_retry = 3

        max_retry = max(
            1,
            max_retry
        )

        last_error = None

        for retry_index in range(
            max_retry
        ):

            try:

                return self.request_sync(

                    provider,

                    prompt,

                    system_prompt,

                    retry_index
                )

            except RuntimeError as e:

                last_error = e

                error_text = str(e)

                # =================================================
                # 这些错误重试没有意义
                # =================================================

                fatal_keywords = [

                    "HTTP 400",

                    "HTTP 401",

                    "HTTP 403",

                    "HTTP 404",

                    "额度已耗尽",

                    "model不存在",

                    "模型不存在"
                ]

                is_fatal = any(
                    keyword in error_text
                    for keyword in fatal_keywords
                )

                if is_fatal:

                    print()
                    print(
                        "该错误属于不可重试错误，"
                        "停止重试。"
                    )

                    raise

                # =================================================
                # 最后一次
                # =================================================

                if retry_index >= max_retry - 1:

                    break

                wait_time = min(
                    2 ** retry_index,
                    10
                )

                print()
                print(
                    f"请求失败：{error_text}"
                )

                print(
                    f"{wait_time}秒后重试..."
                )

                time.sleep(
                    wait_time
                )

        raise RuntimeError(
            "AI请求最终失败：\n\n"
            + str(last_error)
        ) 

# ============================================================
# AI JSON解析
# ============================================================

def clean_json_text(text):

    if not isinstance(
        text,
        str
    ):

        text = str(text)

    text = text.strip()

    text = re.sub(
        r"^```json\s*",
        "",
        text,
        flags=re.I
    )

    text = re.sub(
        r"^```\s*",
        "",
        text
    )

    text = re.sub(
        r"\s*```$",
        "",
        text
    )

    return text.strip()


def parse_ai_json(text):

    print()
    print("=" * 80)
    print("PARSE AI JSON")
    print("=" * 80)

    print(
        f"输入类型：{type(text).__name__}"
    )

    if text is None:

        print(
            "AI返回：None"
        )

        raise RuntimeError(
            "AI返回内容为None"
        )

    text = str(text)

    print(
        f"输入长度：{len(text)} 字符"
    )

    print()
    print("原始AI返回 repr：")

    print(
        repr(text)
    )

    # ========================================================
    # 空字符串
    # ========================================================

    if not text.strip():

        print()
        print(
            "AI返回的是空字符串！"
        )

        raise RuntimeError(
            "AI返回内容为空字符串"
        )

    # ========================================================
    # 清理Markdown代码块
    # ========================================================

    cleaned = text.strip()

    cleaned = re.sub(
        r"^```json\s*",
        "",
        cleaned,
        flags=re.I
    )

    cleaned = re.sub(
        r"^```\s*",
        "",
        cleaned
    )

    cleaned = re.sub(
        r"\s*```$",
        "",
        cleaned
    )

    cleaned = cleaned.strip()

    print()
    print("清理后的内容：")

    print(
        repr(cleaned)
    )

    # ========================================================
    # 直接JSON
    # ========================================================

    try:

        result = json.loads(
            cleaned
        )

        print()
        print(
            "JSON直接解析成功"
        )

        print(
            f"结果类型："
            f"{type(result).__name__}"
        )

        print("=" * 80)

        return result

    except json.JSONDecodeError as e:

        print()
        print(
            "直接JSON解析失败："
        )

        print(
            f"错误：{e}"
        )

        print(
            f"位置：{e.pos}"
        )

        print(
            f"附近内容："
            f"{repr(cleaned[max(0, e.pos - 100):e.pos + 100])}"
        )

    # ========================================================
    # 提取JSON对象
    # ========================================================

    start = cleaned.find(
        "{"
    )

    end = cleaned.rfind(
        "}"
    )

    if (
        start != -1
        and
        end != -1
        and
        end > start
    ):

        candidate = cleaned[
            start:end + 1
        ]

        print()
        print(
            "发现可能的JSON对象"
        )

        print(
            f"JSON对象长度："
            f"{len(candidate)}"
        )

        try:

            result = json.loads(
                candidate
            )

            print(
                "JSON对象解析成功"
            )

            print("=" * 80)

            return result

        except json.JSONDecodeError as e:

            print(
                f"JSON对象解析失败：{e}"
            )

    # ========================================================
    # 提取JSON数组
    # ========================================================

    start = cleaned.find(
        "["
    )

    end = cleaned.rfind(
        "]"
    )

    if (
        start != -1
        and
        end != -1
        and
        end > start
    ):

        candidate = cleaned[
            start:end + 1
        ]

        print()
        print(
            "发现可能的JSON数组"
        )

        print(
            f"JSON数组长度："
            f"{len(candidate)}"
        )

        try:

            result = json.loads(
                candidate
            )

            print(
                "JSON数组解析成功"
            )

            print("=" * 80)

            return result

        except json.JSONDecodeError as e:

            print(
                f"JSON数组解析失败：{e}"
            )

    # ========================================================
    # 最终失败
    # ========================================================

    print()
    print("=" * 80)
    print("AI JSON解析最终失败")
    print("=" * 80)

    print()
    print("AI完整原始返回：")

    print(
        text
    )

    print()
    print("AI原始返回 repr：")

    print(
        repr(text)
    )

    print("=" * 80)

    raise RuntimeError(
        "AI返回内容不是合法JSON：\n\n"
        + text
    )

    try:

        return json.loads(
            text
        )

    except Exception:
        pass

    # 尝试从回答中提取JSON对象
    start = text.find("{")
    end = text.rfind("}")

    if (
        start != -1
        and
        end != -1
        and
        end > start
    ):

        candidate = text[
            start:end + 1
        ]

        try:

            return json.loads(
                candidate
            )

        except Exception:
            pass

    # 尝试JSON数组
    start = text.find("[")
    end = text.rfind("]")

    if (
        start != -1
        and
        end != -1
        and
        end > start
    ):

        candidate = text[
            start:end + 1
        ]

        try:

            return json.loads(
                candidate
            )

        except Exception:
            pass

    raise RuntimeError(
        "AI返回内容不是合法JSON：\n\n"
        + text
    )


# ============================================================
# Main
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description="合同AI分析工具"
    )

    parser.add_argument(
        "mode",
        choices=[
            "extract_bid",
            "extract_contract",
            "compare"
        ],
        help="处理模式"
    )

    parser.add_argument(
        "input",
        nargs="?",
        help="PDF文件路径"
    )

    parser.add_argument(
        "--provider",
        default=None,
        help="Provider名称"
    )

    parser.add_argument(
        "--config",
        default=str(
            CONFIG_DIR
            / "ai-model.json"
        ),
        help="AI配置文件"
    )

    parser.add_argument(
        "--input",
        dest="compare_input",
        default=None,
        help="STEP3额外TXT文件"
    )

    args = parser.parse_args()

    config_path = Path(
        args.config
    )

    # --------------------------------------------------------
    # 防止 contract_ai.py 作为脚本运行时，
    # step1.py import contract_ai 导致模块重复加载
    # --------------------------------------------------------

    sys.modules["contract_ai"] = sys.modules[
        __name__
    ]

    # --------------------------------------------------------
    # 导入三个Processor
    # --------------------------------------------------------

    from step1 import Step1Processor
    from step2 import Step2Processor
    from step3 import Step3Processor

    # --------------------------------------------------------
    # Gateway
    # --------------------------------------------------------

    gateway = AIGateway(
        config_path
    )

    provider = gateway.get_provider(
        args.provider
    )

    print()
    print(
        f"Provider："
        f"{provider.get('name')}"
    )

    print(
        f"Model："
        f"{provider.get('model')}"
    )

    # ========================================================
    # STEP1
    # ========================================================

    if args.mode == "extract_bid":

        if not args.input:

            raise RuntimeError(
                "extract_bid必须指定PDF"
            )

        processor = Step1Processor(
            gateway,
            provider
        )

        processor.run(
            args.input
        )

        return

    # ========================================================
    # STEP2
    # ========================================================

    if args.mode == "extract_contract":

        if not args.input:

            raise RuntimeError(
                "extract_contract必须指定PDF"
            )

        processor = Step2Processor(
            gateway,
            provider
        )

        processor.run(
            args.input
        )

        return

    # ========================================================
    # STEP3
    # ========================================================

    if args.mode == "compare":
        processor = Step3Processor(gateway, provider)
        processor.run()
        return


# ============================================================
# Entry
# ============================================================

if __name__ == "__main__":

    try:

        main()

    except KeyboardInterrupt:

        print(
            "\n程序被用户中断。"
        )

        sys.exit(1)

    except Exception as e:

        print(
            "\n程序执行失败："
            + type(e).__name__
            + ": "
            + str(e)
        )

        if DEBUG:
            traceback.print_exc()

        sys.exit(1)