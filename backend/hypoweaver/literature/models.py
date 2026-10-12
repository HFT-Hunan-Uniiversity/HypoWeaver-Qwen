from pydantic import BaseModel, Field
from sqlalchemy import ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column
from ..db import Base, now, uid


class LiteratureSearch(Base):
    __tablename__ = "literature_searches"
    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: uid("search"))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    queries: Mapped[list] = mapped_column(JSON)
    per_source_status: Mapped[dict] = mapped_column(JSON, default=dict)
    hit_count: Mapped[int] = mapped_column(default=0)
    status: Mapped[str] = mapped_column(default="running")
    job_id: Mapped[str | None]
    created_at: Mapped[str] = mapped_column(default=now)


class EvidenceCard(Base):
    __tablename__ = "evidence_cards"
    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: uid("ev"))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    search_id: Mapped[str | None] = mapped_column(ForeignKey("literature_searches.id", ondelete="SET NULL"))
    source: Mapped[str]
    sources: Mapped[list] = mapped_column(JSON, default=list)
    doi: Mapped[str | None]
    title: Mapped[str]
    authors: Mapped[list] = mapped_column(JSON, default=list)
    year: Mapped[int | None]
    venue: Mapped[str] = mapped_column(default="")
    cited_by: Mapped[int | None]
    abstract: Mapped[str | None]
    fulltext_excerpt: Mapped[str | None]
    concepts: Mapped[list] = mapped_column(JSON, default=list)
    included: Mapped[bool] = mapped_column(default=True)


class Query(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    lang: str = ""
    rationale: str = ""


class QuerySuggestion(BaseModel):
    queries: list[Query] = Field(min_length=3, max_length=6)


class SearchInput(BaseModel):
    queries: list[Query] = Field(min_length=1, max_length=6)


class EvidencePatch(BaseModel):
    included: bool | None = None
    title: str | None = Field(default=None, min_length=1, max_length=2000)
    year: int | None = Field(default=None, ge=1000, le=2200)
