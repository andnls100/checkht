# -*- coding: utf-8 -*-
"""Compatibility layer for reasoning-first OpenAI-compatible models."""

import json
import requests


def install(gateway):
    """Patch one AIGateway instance in-place."""
    if getattr(gateway, "_reasoning_compat_installed", False):
        return gateway

    original = gateway.request_sync

    def request_sync(provider, prompt, system_prompt=None, retry_index=0):
        model = str(provider.get("model", "")).strip().lower()
        if not model.startswith("glm-5.3"):
            return original(provider, prompt, system_prompt, retry_index)

        api_key = gateway.get_api_key(provider)
        url = gateway.build_chat_url(provider)
        timeout = int(provider.get("timeout", 180))
        max_tokens = max(20000, int(provider.get("max_tokens", 20000)))
        reasoning_effort = provider.get("reasoning_effort", "low")

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": provider.get("model"),
            "messages": messages,
            "temperature": float(provider.get("temperature", 0.1)),
            "max_tokens": max_tokens,
            "thinking": {"type": "enabled"},
            "reasoning_effort": reasoning_effort,
        }
        if provider.get("use_max_completion_tokens", False):
            payload.pop("max_tokens", None)
            payload["max_completion_tokens"] = max_tokens

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "contract-ai/1.0",
        }

        print()
        print("=" * 80)
        print("AI REQUEST (reasoning compatibility)")
        print("=" * 80)
        print(f"Provider      : {provider.get('name', 'unknown')}")
        print(f"Model         : {provider.get('model')}")
        print(f"Prompt长度    : {len(prompt)} 字符")
        print(f"Max tokens    : {max_tokens}")
        print(f"Reasoning     : {reasoning_effort}")
        print(f"Retry         : {retry_index + 1}")
        print("=" * 80)

        try:
            response = requests.post(url, headers=headers, json=payload, timeout=(30, timeout))
        except requests.exceptions.RequestException as exc:
            raise RuntimeError(f"AI请求失败：{exc}") from exc

        try:
            data = response.json()
        except Exception as exc:
            raise RuntimeError(f"AI服务器返回的不是JSON：{response.text[:12000]}") from exc

        if not response.ok:
            raise RuntimeError(
                f"AI HTTP {response.status_code}\n"
                f"{json.dumps(data, ensure_ascii=False, indent=2)[:20000]}"
            )

        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError("AI响应中的choices为空")

        choice = choices[0]
        finish_reason = choice.get("finish_reason")
        message = choice.get("message") or {}
        content = message.get("content")
        reasoning = message.get("reasoning_content")

        print(f"Finish reason : {finish_reason}")
        print(f"Content chars : {len(str(content or ''))}")
        print(f"Reasoning chars: {len(str(reasoning or ''))}")

        # reasoning_content 仅用于排查日志，绝不作为业务提取结果。
        if finish_reason == "length":
            raise RuntimeError(
                "AI输出被max_tokens截断：finish_reason=length。"
                f"content字符数={len(str(content or ''))}；"
                "请缩小字段批次后重试。"
            )

        if content is not None and str(content).strip():
            return str(content)

        raise RuntimeError(
            "AI返回成功，但最终 content 为空；reasoning_content 仅用于日志排查。"
        )

    gateway.request_sync = request_sync
    gateway._reasoning_compat_installed = True
    return gateway
