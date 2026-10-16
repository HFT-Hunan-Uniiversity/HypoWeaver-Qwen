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
        self.settings, self.sessions = settings.model_copy(deep=True), sessions
        self.model = settings.llm_model
        self.client = client

    # Long structured proposals need up to 600s; short prompts stay at 90s.
    LONG_TIMEOUT_PROMPTS = frozenset({"write_proposal_sections", "interpret_results"})

    async def generate(self, prompt_name, payload, OutputModel, project_id=None, timeout=None):
        settings = self.settings
        require_configured(settings)
        prompt = PROMPTS[prompt_name]
        messages = [
            {
                "role": "system",
                "content": RULES
                + "\n"
                + prompt.instruction
                + "\nJSON Schema:\n"
                + json.dumps(OutputModel.model_json_schema(), ensure_ascii=False),
            },
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ]
        if timeout is None:
            timeout = 600 if prompt_name in self.LONG_TIMEOUT_PROMPTS else 90
        client = self.client or AsyncOpenAI(
            api_key=settings.llm_api_key, base_url=settings.llm_base_url, timeout=timeout, max_retries=0
        )
        try:
            for attempt in range(2):
                start = time.perf_counter()
                record = dict(
                    project_id=project_id,
                    prompt_name=prompt.name,
                    prompt_version=prompt.version,
                    model=settings.llm_model,
                    input_tokens=0,
                    output_tokens=0,
                    status="failed",
                    error=None,
                )
                content = ""
                try:
                    response = await client.chat.completions.create(
                        model=settings.llm_model,
                        messages=messages,
                        temperature=0.2,
                        response_format={"type": "json_object"},
                    )
                    if response.usage:
                        record.update(
                            input_tokens=response.usage.prompt_tokens, output_tokens=response.usage.completion_tokens
                        )
                    content = response.choices[0].message.content or ""
                    result = OutputModel.model_validate_json(content)
                    record["status"] = "succeeded"
                    return result
                except ValidationError as exc:
                    errors = [
                        {"loc": list(error["loc"]), "type": error["type"], "msg": error["msg"]}
                        for error in exc.errors(include_input=False, include_context=False, include_url=False)
                    ]
                    summary = json.dumps(errors, ensure_ascii=False)
                    record.update(status="invalid_output", error=summary[:500])
                    if attempt:
                        raise AppError("llm_invalid_output", "模型输出经一次修复后仍不符合要求，请重试") from exc
                    messages.extend(
                        [
                            {"role": "assistant", "content": content},
                            {
                                "role": "user",
                                "content": "请修复 JSON，遵守原始 Schema。校验错误：" + summary,
                            },
                        ]
                    )
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
    require_configured(request.app.state.settings)
    return request.app.state.llm


def configured(settings):
    return all(s.strip() for s in [settings.llm_api_key, settings.llm_model, settings.llm_base_url])


def require_configured(settings):
    if not configured(settings):
        raise AppError("llm_not_configured", "尚未配置模型：请通过设置接口或 LLM_API_KEY / LLM_MODEL 配置后重试", 409)


def model_name(llm):
    # Dependency substitutes in offline tests carry no real model provenance.
    return getattr(llm, "model", None)
