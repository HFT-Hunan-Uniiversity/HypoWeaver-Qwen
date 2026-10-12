import json
import time
from fastapi import Request
from openai import AsyncOpenAI, APIConnectionError, APIStatusError, APITimeoutError
from pydantic import ValidationError
from ..errors import AppError
from .models import LLMCall
from .prompts import PROMPTS, RULES


class LLM:
    def __init__(self, settings, sessions, client=None):
        self.settings, self.sessions = settings, sessions
        self.client = client

    async def generate(self, prompt_name, payload, OutputModel, project_id=None):
        settings = self.settings
        if not settings.dashscope_api_key:
            raise AppError("llm_not_configured", "尚未配置 DASHSCOPE_API_KEY，请在本地环境中配置后重试")
        if not settings.qwen_model:
            raise AppError("model_not_configured", "尚未配置 QWEN_MODEL")
        prompt = PROMPTS[prompt_name]
        messages = [
            {"role": "system", "content": RULES + "\n" + prompt.instruction + "\nJSON Schema:\n" + json.dumps(OutputModel.model_json_schema(), ensure_ascii=False)},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ]
        client = self.client or AsyncOpenAI(api_key=settings.dashscope_api_key, base_url=settings.qwen_base_url, timeout=90, max_retries=0)
        try:
            for attempt in range(2):
                start = time.perf_counter()
                record = dict(project_id=project_id, prompt_name=prompt.name, prompt_version=prompt.version,
                              model=settings.qwen_model, input_tokens=0, output_tokens=0, status="failed", error=None)
                content = ""
                try:
                    response = await client.chat.completions.create(
                        model=settings.qwen_model, messages=messages, temperature=0.2,
                        response_format={"type": "json_object"},
                    )
                    if response.usage:
                        record.update(input_tokens=response.usage.prompt_tokens, output_tokens=response.usage.completion_tokens)
                    content = response.choices[0].message.content or ""
                    result = OutputModel.model_validate_json(content)
                    record["status"] = "succeeded"
                    return result
                except ValidationError as exc:
                    errors = [{"loc": list(e["loc"]), "type": e["type"]} for e in exc.errors(include_input=False)]
                    record.update(status="invalid_output", error="结构化输出校验失败")
                    if attempt:
                        raise AppError("llm_invalid_output", "模型输出经一次修复后仍不符合要求，请重试") from exc
                    messages.extend([
                        {"role": "assistant", "content": content},
                        {"role": "user", "content": "请修复 JSON，遵守原始 Schema。校验错误：" + json.dumps(errors)},
                    ])
                except (APIConnectionError, APITimeoutError) as exc:
                    record["error"] = "无法连接模型服务或请求超时"
                    raise AppError("llm_connection", record["error"], 502) from exc
                except APIStatusError as exc:
                    record["error"] = f"模型服务返回 HTTP {exc.status_code}，请检查密钥、模型和服务额度"
                    raise AppError("llm_service", record["error"], 502) from exc
                except AppError:
                    raise
                except Exception as exc:
                    record["error"] = f"模型响应处理失败（{type(exc).__name__}）"
                    raise AppError("llm_error", record["error"], 502) from exc
                finally:
                    record["latency_ms"] = round((time.perf_counter() - start) * 1000)
                    with self.sessions() as db:
                        db.add(LLMCall(**record))
                        db.commit()
        finally:
            if self.client is None:
                await client.close()


def get_llm(request: Request):
    """FastAPI dependency: tests may override with a deterministic FakeLLM."""
    return request.app.state.llm
