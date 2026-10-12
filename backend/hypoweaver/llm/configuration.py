import os
from urllib.parse import urlsplit
from dotenv import dotenv_values, set_key
from pydantic import BaseModel, Field, field_validator
from .service import LLM, configured


class LLMConfigInput(BaseModel):
    base_url: str | None = Field(default=None, max_length=2000)
    api_key: str | None = Field(default=None, max_length=4096, repr=False)
    llm_model: str | None = Field(default=None, min_length=1, max_length=200)

    @field_validator("base_url")
    @classmethod
    def valid_url(cls, value):
        if value is None:
            return value
        parsed = urlsplit(value)
        if parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("模型地址须为不含账号密码的 HTTP(S) 地址")
        if parsed.query or parsed.fragment:
            raise ValueError("模型地址不应包含查询参数或片段")
        return value.rstrip("/")

    @field_validator("llm_model")
    @classmethod
    def nonempty_model(cls, value):
        if value is not None and not value.strip():
            raise ValueError("模型名不能为空")
        return value.strip() if value is not None else value


def config_path(settings):
    return settings.storage_dir() / ".env.llm"


def load(settings):
    path = config_path(settings)
    if path.exists():
        stored = dotenv_values(path)
        values = {key.lower(): stored[key] for key in ["LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL"] if key in stored}
        return settings.model_copy(update=values)
    return settings


def public(settings):
    return {
        "base_url": settings.llm_base_url,
        "llm_model": settings.llm_model,
        "configured": configured(settings),
    }


def save(app, payload):
    settings = app.state.settings
    names = {"base_url": "llm_base_url", "api_key": "llm_api_key", "llm_model": "llm_model"}
    changes = {names[key]: value for key, value in payload.model_dump(exclude_none=True).items()}
    updated = settings.model_copy(update=changes)
    path = config_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    # The local file is ignored and owner-readable; never echo key material.
    descriptor = os.open(path, os.O_CREAT | os.O_WRONLY, 0o600)
    os.close(descriptor)
    path.chmod(0o600)
    for key in ["llm_base_url", "llm_api_key", "llm_model"]:
        set_key(path, key.upper(), getattr(updated, key))
    path.chmod(0o600)
    app.state.settings = updated
    app.state.llm = LLM(updated, app.state.sessions)
    return public(updated)
