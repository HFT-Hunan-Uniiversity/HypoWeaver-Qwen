from pydantic import BaseModel
from sqlalchemy.orm import Mapped, mapped_column
from ..db import Base, now, uid


class LLMCall(Base):
    __tablename__ = "llm_calls"
    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: uid("llm"))
    project_id: Mapped[str | None]
    prompt_name: Mapped[str]
    prompt_version: Mapped[str]
    model: Mapped[str]
    input_tokens: Mapped[int] = mapped_column(default=0)
    output_tokens: Mapped[int] = mapped_column(default=0)
    latency_ms: Mapped[int]
    status: Mapped[str]
    error: Mapped[str | None]
    created_at: Mapped[str] = mapped_column(default=now)


class ConnectionCheck(BaseModel):
    message: str
