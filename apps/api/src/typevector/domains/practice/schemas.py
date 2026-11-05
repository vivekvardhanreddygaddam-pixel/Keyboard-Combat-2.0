"""TypeVector Arena — Practice Schemas."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PracticePromptRead(BaseModel):
    """Curated practice prompt metadata and content."""

    id: str
    mode: str
    title: str
    difficulty: str
    language: str
    source: str
    content: str


class PracticeModeInfo(BaseModel):
    """Specification of an available practice mode."""

    mode: str
    title: str
    description: str
    is_timed: bool = False
    duration_seconds: int | None = None
    target_accuracy_min: float | None = None


class PracticeSessionSubmit(BaseModel):
    """Payload submitted upon completing a practice typing exercise."""

    prompt_id: str | None = None
    mode: str = Field(..., max_length=50)
    language: str = Field(default="en", max_length=50)
    target_text: str = Field(..., min_length=1, max_length=10000)
    input_text: str = Field(default="", max_length=15000)
    started_at: datetime
    completed_at: datetime
    client_metrics: dict[str, Any] | None = None


class DiffSegment(BaseModel):
    """Single character or token alignment unit."""

    expected: str | None
    actual: str | None
    type: str  # match | error | tail
    category: str  # match | substitution | omission | insertion | case_error | etc.


class PracticeSessionRead(BaseModel):
    """Practice session result schema."""

    id: uuid.UUID
    user_id: uuid.UUID | None
    mode: str
    language: str
    started_at: datetime
    completed_at: datetime | None
    gross_wpm: float | None
    net_wpm: float | None
    accuracy_pct: float | None
    error_diff_json: dict[str, Any] | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PracticeEvaluationResponse(BaseModel):
    """Authoritative server evaluation result returned after submitting a practice attempt."""

    session_id: uuid.UUID
    user_id: uuid.UUID | None
    mode: str
    language: str
    is_saved: bool
    started_at: datetime
    completed_at: datetime
    metrics: dict[str, Any]
    segments: list[DiffSegment]
    error_breakdown: dict[str, int]
    suggestions: list[str]
