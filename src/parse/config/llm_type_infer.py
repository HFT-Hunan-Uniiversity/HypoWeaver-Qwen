# LLM 文档类型推断兜底
# 当文件名关键词匹配无法确定类型时，用千问看第一页文本分类

import json
import re
from typing import Optional

import requests

from src.parse.config.doc_types import get_supported_types
from src.parse.adapters.llm_metadata import DASHSCOPE_URL, MODEL, HEADERS


def _build_prompt(first_page_text: str, supported_types: list) -> str:
    """构建分类 prompt"""
    text = first_page_text[:2000]

    types_desc = "\n".join(
        f"  - {t['key']}: {t['desc']}" for t in supported_types
    )

    return f"""你是一个文档分类专家。从以下文本判断这份文档的类型。

支持的文档类型：
{types_desc}

规则：
1. 只从以上类型中选择一个
2. 如果都不确定，返回 "unknown"
3. 只输出 JSON，不要多余文字

返回格式：
{{"doc_type": "paper", "doc_type_cn": "论文", "confidence": "high"}}

confidence 字段: high（确定）/ medium（可能）/ low（不太确定）

以下是文本内容：
---
{text}---"""


def infer_type_with_llm(first_page_text: str) -> Optional[dict]:
    """
    用千问 turbol 推断文档类型。
    返回 {"doc_type": str, "doc_type_cn": str, "confidence": str} 或 None。
    """
    from src.parse.config.doc_types import DOC_TYPE_CONFIGS

    supported = [
        {"key": k, "desc": v["description"]}
        for k, v in DOC_TYPE_CONFIGS.items()
    ]
    # 加一个兜底选项说明
    supported.append({"key": "unknown", "desc": "以上都不属于（未知类型）"})

    prompt = _build_prompt(first_page_text, supported)

    data = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 128,
        "temperature": 0.1,
    }

    try:
        resp = requests.post(DASHSCOPE_URL, headers=HEADERS, json=data, timeout=30)
        if resp.status_code != 200:
            return None

        result = resp.json()
        content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
        if not content:
            return None

        # 提取 JSON
        json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
        if json_match:
            content = json_match.group(1)

        parsed = json.loads(content)
        doc_type = parsed.get("doc_type", "unknown")
        doc_type_cn = parsed.get("doc_type_cn", "未知")

        # 校验：如果返回的类型不在支持列表中，转为 unknown
        if doc_type != "unknown" and doc_type not in get_supported_types():
            doc_type = "unknown"
            doc_type_cn = "未知"

        return {
            "doc_type": doc_type,
            "doc_type_cn": doc_type_cn,
            "confidence": parsed.get("confidence", "low"),
        }

    except Exception:
        return None