from pydantic import BaseModel, Field, model_validator
from sqlalchemy import ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column
from ..db import Base, now


class BindingValue(BaseModel):
    field: str | None = None
    formula: str | None = Field(default=None, max_length=500)

    @model_validator(mode='after')
    def exactly_one(self):
        if bool(self.field) == bool(self.formula):
            raise ValueError('请提供一个字段或一个派生公式')
        return self


class BindingInput(BaseModel):
    dataset_id: str
    bindings: dict[str, BindingValue]
    confirmed: bool = False


class BindingSuggestion(BindingValue):
    role_name: str
    confidence: float = Field(ge=0, le=1)
    note: str


class BindingOutput(BaseModel):
    bindings: list[BindingSuggestion]


class VariableBinding(Base):
    __tablename__ = 'variable_bindings'
    plan_id: Mapped[str] = mapped_column(ForeignKey('study_plans.id', ondelete='CASCADE'), primary_key=True)
    dataset_id: Mapped[str] = mapped_column(ForeignKey('datasets.id'))
    bindings: Mapped[dict] = mapped_column(JSON)
    confirmed: Mapped[bool] = mapped_column(default=False)
    updated_at: Mapped[str] = mapped_column(default=now)
