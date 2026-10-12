from typing import Literal
from pydantic import BaseModel, Field
from sqlalchemy import JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from ..db import Base

STRENGTHS = ['insufficient','preliminary','mixed','associational','causal_cautious']
Strength = Literal['insufficient','preliminary','mixed','associational','causal_cautious']


class ClaimAssessment(Base):
    __tablename__ = 'claim_assessments'
    run_id: Mapped[str] = mapped_column(ForeignKey('analysis_runs.id',ondelete='CASCADE'),primary_key=True)
    claim_id: Mapped[str] = mapped_column(primary_key=True)
    verdict: Mapped[str]
    max_strength: Mapped[str]
    allowed_wording: Mapped[str]
    blockers: Mapped[list] = mapped_column(JSON)
    user_decision: Mapped[str] = mapped_column(default='pending')
    chosen_strength: Mapped[str]
    final_text: Mapped[str]


class Decision(BaseModel):
    user_decision: Literal['accepted','downgraded','deferred','rejected']
    chosen_strength: Strength
    final_text: str = Field(min_length=1,max_length=5000)
