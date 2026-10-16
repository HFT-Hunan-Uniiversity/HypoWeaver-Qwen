from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column
from ..db import Base, now, uid


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: uid("pr"))
    title: Mapped[str] = mapped_column(String(200))
    case: Mapped[str | None]
    direction: Mapped[dict] = mapped_column(JSON)
    selected_candidate_id: Mapped[str | None]
    created_at: Mapped[str] = mapped_column(default=now)
    updated_at: Mapped[str] = mapped_column(default=now)

    @property
    def completed(self) -> bool:
        """最新一版提案已在后端确认且未过期。"""
        from sqlalchemy import select
        from sqlalchemy.orm import object_session
        from ..proposal.models import Proposal

        db = object_session(self)
        if db is None:
            return False
        latest = db.scalar(
            select(Proposal).where(Proposal.project_id == self.id).order_by(Proposal.version.desc()).limit(1)
        )
        return bool(latest and latest.confirmed_at and not latest.stale)


class Direction(BaseModel):
    text: str = Field(default="", max_length=10000)
    question: str = ""
    constraints: list[str] = Field(default_factory=list)
    domain: str = ""


class ProjectCreate(BaseModel):
    case: Literal["carbon"] | None = None
    title: str = Field(min_length=1, max_length=200, pattern=r"\S")
    direction: Direction = Field(default_factory=Direction)


class ProjectPatch(BaseModel):
    case: Literal["carbon"] | None = None
    title: str | None = Field(default=None, min_length=1, max_length=200, pattern=r"\S")
    direction: Direction | None = None


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    case: str | None
    title: str
    direction: Direction
    selected_candidate_id: str | None
    created_at: str
    completed: bool = False
    updated_at: str
