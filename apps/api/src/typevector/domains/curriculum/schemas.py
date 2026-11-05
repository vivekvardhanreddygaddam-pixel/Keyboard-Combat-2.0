"""TypeVector Arena — Curriculum Schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SkillTrackLevelRead(BaseModel):
    """Specification and criteria for a single track level."""

    level_number: int
    title: str
    min_wpm: float
    min_accuracy_pct: float
    pass_attempts_required: int
    prompt_content: str
    criteria_version: str = "2026.1-draft"


class SkillTrackRead(BaseModel):
    """Skill track summary schema."""

    id: uuid.UUID | str
    slug: str
    title: str
    description: str | None
    is_active: bool = True

    model_config = ConfigDict(from_attributes=True)


class SkillTrackDetailRead(BaseModel):
    """Skill track detailed schema with all level definitions."""

    slug: str
    title: str
    description: str | None
    is_active: bool = True
    levels: list[SkillTrackLevelRead]


class UserTrackProgressRead(BaseModel):
    """Participant qualification state across a single educational skill track."""

    track_slug: str
    track_title: str
    current_level_number: int
    current_level_title: str
    qualifying_attempts_count: int
    pass_attempts_required: int
    is_track_completed: bool
    criteria_version: str
    criteria_status: str
    last_evaluated_at: datetime | None


class CurriculumAssessmentSubmit(BaseModel):
    """Submission payload for a curriculum level assessment attempt."""

    track_slug: str = Field(..., max_length=100)
    level_number: int = Field(..., ge=1, le=6)
    input_text: str = Field(default="", max_length=15000)
    started_at: datetime
    completed_at: datetime


class CriterionStatus(BaseModel):
    """Individual pass/fail status for a criteria dimension."""

    name: str
    required: float
    actual: float
    unit: str
    passed: bool


class CurriculumEvaluationResult(BaseModel):
    """Authoritative server evaluation result for a curriculum level assessment."""

    track_slug: str
    level_number: int
    level_title: str
    net_wpm: float
    accuracy_pct: float
    completion_pct: float
    is_qualifying: bool
    qualifying_attempts_completed: int
    pass_attempts_required: int
    did_advance_level: bool
    new_level_number: int
    criteria_version: str
    criteria_status: str
    criteria_checklist: list[CriterionStatus]
    explanation: str


class AdaptiveRecommendationRead(BaseModel):
    """Explainable, evidence-backed curriculum recommendation based on real observed weaknesses."""

    recommended_track_slug: str
    recommended_track_title: str
    recommended_level: int
    reason: str
    evidence: str
    confidence: str
    sample_size: int
    alternative_track_slugs: list[str]
    disclaimer: str = (
        "Recommendations are pedagogical guides based on error frequency patterns. "
        "Participants may select any exercise or track freely."
    )
