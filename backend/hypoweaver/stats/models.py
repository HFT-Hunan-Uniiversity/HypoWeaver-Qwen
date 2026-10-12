from typing import Literal, Any
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column
from ..db import Base, uid, now
from ..plans.models import MethodFamily, Robustness, Permutation


class EventSpec(BaseModel):
    bins: list[int] = Field(default_factory=lambda: [-5, -4, -3, -2, 0, 1, 2, 3, 4, 5])
    reference: Literal[-1] = -1
    monotone_only: Literal[True] = True

    @model_validator(mode="after")
    def consecutive(self):
        if not self.bins or self.bins[0] < -20 or self.bins[-1] > 20 or self.bins[0] >= -1 or self.bins[-1] < 0:
            raise ValueError("事件窗口须覆盖处理前后，且限定在 -20 至 20")
        if self.bins != [k for k in range(self.bins[0], self.bins[-1] + 1) if k != -1]:
            raise ValueError("事件分箱须连续且仅省略基期 -1")
        return self


class SampleFilter(BaseModel):
    field: str
    op: Literal["eq", "ne", "ge", "le", "in"]
    value: Any


class AnalysisSpec(BaseModel):
    method_family: MethodFamily
    unit: str
    time: str
    outcome: str
    treatment: str
    controls: list[str] = Field(default_factory=list)
    fe: list[Literal["unit", "time"]] = Field(default_factory=lambda: ["unit", "time"])
    cluster: str = "unit"
    event: EventSpec = Field(default_factory=EventSpec)
    robustness: list[Robustness] = Field(default_factory=list)
    permutation: Permutation = Field(default_factory=Permutation)
    sample_filters: list[SampleFilter] = Field(default_factory=list)
    mechanism: str | None = None
    moderator: str | None = None


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"
    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: uid("run"))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    plan_id: Mapped[str] = mapped_column(ForeignKey("study_plans.id", ondelete="CASCADE"))
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"))
    status: Mapped[str] = mapped_column(default="queued")
    steps: Mapped[dict] = mapped_column(JSON, default=dict)
    spec: Mapped[dict] = mapped_column(JSON)
    plan_snapshot: Mapped[dict] = mapped_column(JSON)
    binding_snapshot: Mapped[dict] = mapped_column(JSON)
    result: Mapped[dict | None] = mapped_column(JSON)
    reproduction: Mapped[dict | None] = mapped_column(JSON)
    stale: Mapped[bool] = mapped_column(default=False)
    error: Mapped[str | None]
    job_id: Mapped[str | None]
    created_at: Mapped[str] = mapped_column(default=now)
    finished_at: Mapped[str | None]
