from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_ENDPOINT = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
DEFAULT_MODEL = "qwen3-vl-plus"


PROMPT = r"""
你是一名科研证据抽取智能体。请只抽取图像中的 Table 5（标题为
"Impact of fintech on industrial gas emissions."），忽略同页的其他表格与正文。

要求：
1. 逐模型读取系数、括号内标准误和显著性星号，不得推测模糊或缺失值。
2. 保留变量的模型下标含义；JSON 键名必须严格使用下面给定的键。
3. 数字输出为 JSON number；固定效应输出 boolean；表中空白项输出 null。
4. significance 只能是 "***"、"**"、"*" 或 ""。
5. 只输出一个合法 JSON 对象，不要 Markdown 代码围栏，不要附加解释。

严格输出结构：
{
  "table_number": "5",
  "title": "Impact of fintech on industrial gas emissions.",
  "dependent_variable": "SO2_it",
  "models": {
    "(1)": {
      "Fintech_it-1": {"coefficient": null, "std_error": null, "significance": ""},
      "DSD_it": null,
      "GDPpc_it-1": {"coefficient": null, "std_error": null, "significance": ""},
      "TOP_it-1": {"coefficient": null, "std_error": null, "significance": ""},
      "Ind_it-1": {"coefficient": null, "std_error": null, "significance": ""},
      "city_fe": null,
      "year_fe": null,
      "observations": null,
      "f_statistic": {"value": null, "significance": ""},
      "r_squared": null
    },
    "(2)": {
      "Fintech_it-1": {"coefficient": null, "std_error": null, "significance": ""},
      "DSD_it": {"coefficient": null, "std_error": null, "significance": ""},
      "GDPpc_it-1": {"coefficient": null, "std_error": null, "significance": ""},
      "TOP_it-1": {"coefficient": null, "std_error": null, "significance": ""},
      "Ind_it-1": {"coefficient": null, "std_error": null, "significance": ""},
      "city_fe": null,
      "year_fe": null,
      "observations": null,
      "f_statistic": {"value": null, "significance": ""},
      "r_squared": null
    }
  },
  "notes": {
    "clustered_standard_errors": null,
    "stars": {"*": 0.10, "**": 0.05, "***": 0.01}
  }
}
""".strip()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def parse_json_content(content: str) -> dict:
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("Model response does not contain a JSON object")
    parsed = json.loads(text[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("Model response JSON must be an object")
    return parsed


def call_qwen_vl(
    image_path: Path,
    *,
    endpoint: str,
    model: str,
    timeout: int,
) -> tuple[dict, dict]:
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        raise RuntimeError("DASHSCOPE_API_KEY is not configured")

    image_bytes = image_path.read_bytes()
    image_data_url = "data:image/png;base64," + base64.b64encode(image_bytes).decode("ascii")
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": image_data_url}},
                    {"type": "text", "text": PROMPT},
                ],
            }
        ],
        "temperature": 0.0,
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(
        endpoint,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    started = time.perf_counter()
    try:
        with urlopen(request, timeout=timeout) as response:
            response_bytes = response.read()
            status_code = response.status
            response_headers = dict(response.headers.items())
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"DashScope HTTP {exc.code}: {error_body}") from exc
    except URLError as exc:
        raise RuntimeError(f"DashScope connection failed: {exc}") from exc
    elapsed = time.perf_counter() - started

    raw = json.loads(response_bytes.decode("utf-8"))
    content = raw["choices"][0]["message"]["content"]
    extracted = parse_json_content(content)
    metadata = {
        "endpoint": endpoint,
        "model_requested": model,
        "model_returned": raw.get("model"),
        "request_id": raw.get("id") or response_headers.get("x-request-id"),
        "status_code": status_code,
        "elapsed_seconds": round(elapsed, 3),
        "image_path": str(image_path),
        "image_sha256": sha256_bytes(image_bytes),
        "prompt_sha256": sha256_bytes(PROMPT.encode("utf-8")),
        "usage": raw.get("usage"),
        "finish_reason": raw.get("choices", [{}])[0].get("finish_reason"),
    }
    return {"metadata": metadata, "raw_response": raw}, extracted


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Qwen-VL scientific table extraction")
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--model", default=os.getenv("QWEN_VL_MODEL", DEFAULT_MODEL))
    parser.add_argument("--endpoint", default=os.getenv("DASHSCOPE_ENDPOINT", DEFAULT_ENDPOINT))
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()

    image_path = args.image.resolve()
    if not image_path.is_file():
        raise FileNotFoundError(image_path)
    args.out_dir.mkdir(parents=True, exist_ok=True)

    response, extracted = call_qwen_vl(
        image_path,
        endpoint=args.endpoint,
        model=args.model,
        timeout=args.timeout,
    )
    response_path = args.out_dir / f"response_{args.case_id}.json"
    extraction_path = args.out_dir / f"extraction_{args.case_id}.json"
    response_path.write_text(
        json.dumps(response, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    extraction_path.write_text(
        json.dumps(extracted, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps({
        "case_id": args.case_id,
        "model": response["metadata"]["model_returned"] or args.model,
        "elapsed_seconds": response["metadata"]["elapsed_seconds"],
        "response_path": str(response_path),
        "extraction_path": str(extraction_path),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

