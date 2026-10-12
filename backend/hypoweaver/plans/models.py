from typing import Literal
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column
from ..db import Base, uid, now

MethodFamily = Literal['policy_causal', 'panel_association', 'mechanism_boundary']


class Variable(BaseModel):
    role: Literal['outcome', 'treatment', 'control', 'mechanism', 'moderator', 'unit', 'time']
    name: str = Field(min_length=1, pattern=r'^[A-Za-z_][A-Za-z0-9_]*$')
    definition: str = Field(min_length=1)
    uncertain: bool = True


class ModelSpec(BaseModel):
    fixed_effects: list[Literal['unit', 'time']] = Field(default_factory=lambda: ['unit', 'time'])
    cluster: str = 'unit'
    event_window: list[int] = Field(default_factory=lambda: [-5, 5], min_length=2, max_length=2)
    bins: list[int] = Field(default_factory=lambda: [-5, -4, -3, -2, 0, 1, 2, 3, 4, 5])
    identification_assumptions: list[str] = Field(default_factory=list)

    @model_validator(mode='after')
    def valid_event(self):
        if self.event_window[0] >= -1 or self.event_window[1] < 0:
            raise ValueError('事件窗口必须同时覆盖处理前和处理后')
        if self.bins != sorted(set(self.bins)) or -1 in self.bins or not self.bins or self.bins[0] != self.event_window[0] or self.bins[-1] != self.event_window[1]:
            raise ValueError('事件分箱须升序、无重复，省略基期 -1，首尾与窗口一致')
        return self


class Robustness(BaseModel):
    id: str = Field(min_length=1)
    change: str = Field(min_length=1)
    kind: Literal['drop_controls', 'exclude_years', 'monotone_only', 'alt_outcome', 'add_controls']
    args: dict = Field(default_factory=dict)


class Permutation(BaseModel):
    n: int = Field(default=499, ge=19, le=1999)
    seed: int = Field(default=42, ge=0, le=2**32-1)


class DecisionRules(BaseModel):
    expected_sign: Literal[-1, 1] = 1
    alpha: float = Field(default=.05, gt=0, lt=1)
    pretrend_alpha: float = Field(default=.10, gt=0, lt=1)
    robustness_share: float = Field(default=.75, gt=0, le=1)
    permutation_alpha: float = Field(default=.05, gt=0, lt=1)


class PlannedClaim(BaseModel):
    id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    type: Literal['main', 'mechanism', 'boundary'] = 'main'


class PlanDraft(BaseModel):
    method_family: MethodFamily
    variables: list[Variable] = Field(min_length=4)
    model: ModelSpec = Field(default_factory=ModelSpec)
    robustness: list[Robustness] = Field(default_factory=list)
    permutation: Permutation = Field(default_factory=Permutation)
    decision_rules: DecisionRules = Field(default_factory=DecisionRules)
    claims_planned: list[PlannedClaim] = Field(min_length=1)
    boundary_notes: str = Field(min_length=1)
    treatment_is_real_assignment: bool = False

    @model_validator(mode='after')
    def unique_roles(self):
        if len({v.name for v in self.variables}) != len(self.variables):
            raise ValueError('变量名必须唯一')
        for role in ['outcome', 'treatment', 'unit', 'time']:
            if sum(v.role == role for v in self.variables) != 1:
                raise ValueError(f'{role} 角色必须恰好有一个变量')
        for values in [self.robustness, self.claims_planned]:
            if len({v.id for v in values}) != len(values):
                raise ValueError('稳健性及结论标识不得重复')
        return self


class CarbonPlanDraft(PlanDraft):
    robustness: list[Robustness] = Field(min_length=4)


class StudyPlan(Base):
    __tablename__ = 'study_plans'
    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: uid('plan'))
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id', ondelete='CASCADE'))
    candidate_id: Mapped[str] = mapped_column(ForeignKey('candidates.id', ondelete='CASCADE'))
    version: Mapped[int]
    status: Mapped[str] = mapped_column(default='draft')
    method_family: Mapped[str]
    variables: Mapped[list] = mapped_column(JSON)
    model: Mapped[dict] = mapped_column(JSON)
    robustness: Mapped[list] = mapped_column(JSON)
    permutation: Mapped[dict] = mapped_column(JSON)
    decision_rules: Mapped[dict] = mapped_column(JSON)
    claims_planned: Mapped[list] = mapped_column(JSON)
    boundary_notes: Mapped[str]
    treatment_is_real_assignment: Mapped[bool] = mapped_column(default=False)
    stale: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[str] = mapped_column(default=now)
