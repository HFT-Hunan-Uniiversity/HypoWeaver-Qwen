# ============================================================================
# KG 三元组抽取专用 LLM 客户端 — src/kg/llm_extract_client.py
# ============================================================================
# 独立于 src/parse/adapters/llm_metadata.py 的第二个 DashScope 客户端。
#
#   - llm_metadata.py : 固定 qwen-turbo，低成本解析 标题/作者/关键词  —— 不动。
#   - 本模块           : 固定 qwen-max，做三元组抽取，互不干扰。
#
# 仅提供 chat(qwen-max) 原语 + 容错重试；prompt 与 JSON 解析放在 extractor.py，
# 职责单一：发一次请求、拿回原始文本，超时/5xx 自动指数退避重试。
# 所有配置从 src/kg/config.py 读取（含 DASHSCOPE_API_KEY 环境变量复用）。
# ============================================================================

from __future__ import annotations

import json
import time
from typing import Optional

import requests

from src.kg.config import (
    LLM_API_KEY,
    LLM_BASE_URL,
    LLM_MODEL,
    LLM_MAX_RETRIES,
    LLM_RETRY_BACKOFF,
    LLM_TIMEOUT,
    LLM_TEMPERATURE,
)


def chat_raw(
    messages: list,
    max_tokens: int = 4096,
    response_format: Optional[dict] = None,
    timeout: Optional[int] = None,
) -> Optional[str]:
    """
    对 qwen-max 发一次 OpenAI-compatible 请求，返回响应 content 字符串。
    失败（网络/HTTP 5xx/空正文）自动重试，全部失败返回 None。

    参数:
      messages: [{"role","content"}, ...]
      max_tokens: 最大输出 token
      response_format: {"type":"json_object"}，DashScope 兼容模式支持
    """
    headers = {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "Content-Type": "application/json",
    }
    data = {
        "model": LLM_MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": LLM_TEMPERATURE,
    }
    if response_format:
        data["response_format"] = response_format

    last_err = None
    for attempt in range(LLM_MAX_RETRIES + 1):
        try:
            resp = requests.post(
                LLM_BASE_URL, headers=headers, json=data, timeout=timeout or LLM_TIMEOUT
            )
            if resp.status_code == 200:
                content = _extract_content(resp.json())
                if content is not None:
                    return content
                last_err = "LLM 返回空内容"
            else:
                last_err = f"HTTP {resp.status_code}: {resp.text[:200]}"
                # 4xx（如鉴权/限流）不重试，直接抛给上层
                if 400 <= resp.status_code < 500:
                    return None
        except requests.exceptions.Timeout:
            last_err = "请求超时"
        except requests.exceptions.RequestException as e:
            last_err = f"网络异常: {e}"
        except Exception as e:  # noqa: BLE001
            last_err = f"未知错误: {e}"

        if attempt < LLM_MAX_RETRIES:
            time.sleep(LLM_RETRY_BACKOFF * (2 ** attempt))

    # 静默返回 None（记录在日志/失败清单即可，不抛异常打断流水线）
    return None


def _extract_content(payload: dict) -> Optional[str]:
    """从 DashScope 兼容响应里取 content 文本。"""
    try:
        content = (
            payload
            .get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
        )
        return content if content else None
    except Exception:  # noqa: BLE001
        return None


def chat_json(
    messages: list,
    max_tokens: int = 4096,
) -> Optional[str]:
    """
    以 json_object 模式请求（强制 LLM 输出合法 JSON 对象）。
    返回原始 JSON 字符串；失败返回 None。
    """
    return chat_raw(
        messages,
        max_tokens=max_tokens,
        response_format={"type": "json_object"},
    )
