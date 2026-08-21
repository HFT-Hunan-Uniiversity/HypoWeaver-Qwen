# 千问 LLM 元数据抽取 fallback
# 只在正则提取失败时调用，节约 token
# 模型: qwen-turbo (DashScope compatible-mode)

import json
import os
import re
from typing import Optional, Dict, Any

import requests

DASHSCOPE_API_KEY = os.environ.get("DASHSCOPE_API_KEY", "")
DASHSCOPE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
MODEL = "qwen-turbo"

HEADERS = {
    "Authorization": f"Bearer {DASHSCOPE_API_KEY}",
    "Content-Type": "application/json",
}


def _build_prompt(first_page_text: str, doc_type: str = "paper") -> str:
    """构建抽取 prompt，根据文档类型定制"""
    text = first_page_text[:3000]

    if doc_type == "paper":
        return f"""你是一个学术论文元数据抽取专家。从以下 PDF 第一页文本中提取论文元数据，以 JSON 格式返回。

返回格式（严格 JSON，不要多余文字）：
{{
    "title": "论文标题（中英文均可）",
    "authors": ["作者1", "作者2"],
    "abstract": "摘要内容（完整）",
    "keywords": ["关键词1", "关键词2"]
}}

规则：
1. title: 如果找不到返回 null
2. authors: 如果找不到返回空数组 []
3. abstract: 如果找不到返回 null
4. keywords: 如果找不到返回空数组 []
5. 不要编造任何信息，找不到就返回 null/空数组

以下是文本内容：
---
{text}
---"""

    elif doc_type == "policy":
        return f"""你是一个政策文件元数据抽取专家。从以下文本提取政策文件元数据，以 JSON 格式返回。

返回格式（严格 JSON，不要多余文字）：
{{
    "title": "文件标题",
    "issuer": "发文机关（如国务院、央行）",
    "doc_number": "文号（如 银发〔2024〕1号）",
    "date": "发布日期",
    "summary": "主要内容摘要（100字以内）"
}}

规则：
1. 找不到的字段返回 null
2. 不要编造信息

以下是文本内容：
---
{text}
---"""

    else:
        # esg_report / news / 兜底
        type_label = {
            "esg_report": "ESG 报告",
            "news": "新闻",
        }.get(doc_type, "文档")
        return f"""你是一个{type_label}元数据抽取专家。从以下文本提取元数据，以 JSON 格式返回。

返回格式（严格 JSON，不要多余文字）：
{{
    "title": "标题",
    "authors": ["作者或责任方"],
    "date": "发布日期",
    "summary": "核心内容摘要（100字以内）"
}}

规则：
1. 找不到的字段返回 null / 空数组
2. 不要编造信息

以下是文本内容：
---
{text}
---"""


def extract_with_llm(first_page_text: str, doc_type: str = "paper") -> Optional[Dict[str, Any]]:
    """
    调用 qwen-turbo 抽取元数据。
    返回 {title, authors, abstract, keywords} 或 None（失败）。
    """
    prompt = _build_prompt(first_page_text)

    data = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 1024,
        "temperature": 0.1,
    }

    try:
        resp = requests.post(DASHSCOPE_URL, headers=HEADERS, json=data, timeout=30)
        if resp.status_code != 200:
            print(f"    ⚠️  LLM 调用失败: HTTP {resp.status_code}")
            return None

        result = resp.json()
        content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
        if not content:
            return None

        # 提取 JSON（兼容模型可能输出 markdown 代码块）
        json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
        if json_match:
            content = json_match.group(1)

        parsed = json.loads(content)
        return {
            "title": parsed.get("title") or None,
            "authors": parsed.get("authors") or [],
            "abstract": parsed.get("abstract") or None,
            "keywords": parsed.get("keywords") or [],
        }

    except json.JSONDecodeError as e:
        print(f"    ⚠️  LLM 返回 JSON 解析失败: {e}")
        return None
    except requests.exceptions.RequestException as e:
        print(f"    ⚠️  LLM 请求异常: {e}")
        return None
    except Exception as e:
        print(f"    ⚠️  LLM 未知错误: {e}")
        return None


if __name__ == "__main__":
    # 命令行测试
    import sys
    test_text = "摘要：本文研究绿色金融对技术创新的影响。关键词：绿色金融；技术创新"
    if len(sys.argv) > 1:
        test_text = open(sys.argv[1], encoding="utf-8").read()
    result = extract_with_llm(test_text)
    print(json.dumps(result, ensure_ascii=False, indent=2))