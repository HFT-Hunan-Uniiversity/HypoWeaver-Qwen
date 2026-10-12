from typing import Literal
from pydantic import BaseModel, Field
from sqlalchemy import ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column
from ..db import Base, uid, now


class DatasetUpload(Base):
    __tablename__ = "dataset_uploads"
    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: uid("upload"))
    name: Mapped[str]
    format: Mapped[str]
    file_path: Mapped[str]
    metadata_: Mapped[dict] = mapped_column("metadata", JSON)
    created_at: Mapped[str] = mapped_column(default=now)


class Dataset(Base):
    __tablename__ = "datasets"
    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: uid("ds"))
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"))
    name: Mapped[str]
    source: Mapped[dict] = mapped_column(JSON, default=dict)
    format: Mapped[str]
    sheet: Mapped[str | None]
    selected_columns: Mapped[list] = mapped_column(JSON)
    file_path: Mapped[str]
    size_bytes: Mapped[int]
    sha256: Mapped[str]
    n_rows: Mapped[int]
    n_cols: Mapped[int]
    panel: Mapped[dict] = mapped_column(JSON)
    profile: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(default=now)


class Source(BaseModel):
    url: str = ""
    doi: str = ""
    license: str = ""
    citation: str = ""


class ImportInput(BaseModel):
    upload_id: str
    project_id: str
    name: str = Field(min_length=1, max_length=200)
    columns: list[str] = Field(min_length=1, max_length=300)
    sheet: str | None = None
    source: Source = Field(default_factory=Source)
    unit: str | None = None
    time: str | None = None


class DatasetPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    source: Source | None = None


class FieldPatch(BaseModel):
    semantics: Literal["real_assignment", "peer_exposure", "unknown"] | None = None
    level: Literal["firm", "industry", "region", "other"] | None = None
