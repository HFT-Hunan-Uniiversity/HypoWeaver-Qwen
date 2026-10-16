from pydantic import BaseModel, Field
from sqlalchemy import JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from ..db import Base, uid, now


class Proposal(Base):
    __tablename__ = "proposals"
    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: uid("proposal"))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    llm_model: Mapped[str | None]
    interpretation: Mapped[dict | None] = mapped_column(JSON)
    narrative_status: Mapped[str | None]
    narrative_errors: Mapped[list | None] = mapped_column(JSON)
    version: Mapped[int]
    kind: Mapped[str]
    sections: Mapped[list] = mapped_column(JSON)
    snapshot: Mapped[dict] = mapped_column(JSON)
    removed_references: Mapped[int] = mapped_column(default=0)
    stale: Mapped[bool] = mapped_column(default=False)
    confirmed_at: Mapped[str | None] = mapped_column(default=None)
    created_at: Mapped[str] = mapped_column(default=now)


class Paragraph(BaseModel):
    claim_id: str
    text: str = Field(min_length=1, max_length=6000)


class Interpretation(BaseModel):
    paragraphs: list[Paragraph]


class SectionDraft(BaseModel):
    key: str
    markdown: str = Field(min_length=1, max_length=12000)
    evidence_ids: list[str] = Field(default_factory=list)


class SectionsDraft(BaseModel):
    sections: list[SectionDraft] = Field(min_length=1, max_length=10)


class SectionEdit(BaseModel):
    markdown: str = Field(min_length=1, max_length=12000)
