from typing import Literal
from pydantic import BaseModel, Field
from sqlalchemy import ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column
from ..db import Base, now, uid


class CandidateSet(Base):
    __tablename__ = "candidate_sets"
    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: uid("cs"))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    model: Mapped[str | None]
    version: Mapped[int]
    status: Mapped[str] = mapped_column(default="generating")
    review: Mapped[dict] = mapped_column(JSON, default=dict)
    recommendation_text: Mapped[str] = mapped_column(default="")
    removed_references: Mapped[int] = mapped_column(default=0)
    evidence_ids: Mapped[list] = mapped_column(JSON, default=list)
    stale: Mapped[bool] = mapped_column(default=False)
    error: Mapped[str | None]
    job_id: Mapped[str | None]
    created_at: Mapped[str] = mapped_column(default=now)


class Candidate(Base):
    __tablename__ = "candidates"
    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: uid("cand"))
    set_id: Mapped[str] = mapped_column(ForeignKey("candidate_sets.id", ondelete="CASCADE"))
    title: Mapped[str]
    gap: Mapped[str]
    hypothesis: Mapped[str]
    mechanism: Mapped[list] = mapped_column(JSON)
    required_data: Mapped[list] = mapped_column(JSON)
    identification: Mapped[str]
    risks: Mapped[list] = mapped_column(JSON)
    positioning: Mapped[str]
    evidence_ids: Mapped[list] = mapped_column(JSON)
    user_edited: Mapped[bool] = mapped_column(default=False)


class CandidateDraft(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    gap: str = Field(min_length=1)
    hypothesis: str = Field(min_length=1)
    mechanism: list[str] = Field(min_length=1)
    required_data: list[str] = Field(min_length=1)
    identification: str = Field(min_length=1)
    risks: list[str] = Field(min_length=1)
    positioning: Literal["high_increment_data_gap", "feasible_limited_increment", "balanced"]
    evidence_ids: list[str] = Field(min_length=2)


class CandidateOutput(BaseModel):
    candidates: list[CandidateDraft] = Field(min_length=2, max_length=4)
    recommendation_text: str = Field(min_length=1)


class ReviewIssue(BaseModel):
    candidate_id: str
    problem: str
    suggestion: str


class ReviewOutput(BaseModel):
    decision: Literal["pass", "revise"]
    issues: list[ReviewIssue] = Field(default_factory=list)
