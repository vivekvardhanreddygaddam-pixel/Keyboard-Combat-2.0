"""TypeVector Arena — Scoring Schemas."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ParticipantScoreRead(BaseModel):
    """Authoritative score response schema."""

    id: uuid.UUID
    attempt_id: uuid.UUID
    event_id: uuid.UUID
    round_id: uuid.UUID
    user_id: uuid.UUID
    gross_wpm: float
    net_wpm: float
    accuracy_pct: float
    arena_score: int
    is_complete: bool
    completion_ratio: float
    canonical_hash: str
    score_status: str
    created_at: datetime
    replay_manifest_json: dict[str, Any]

    model_config = ConfigDict(from_attributes=True)


class ReconciliationReport(BaseModel):
    """Audit report comparing persisted score against deterministic evidence re-computation."""

    attempt_id: uuid.UUID
    is_consistent: bool
    stored_score: int
    recomputed_score: int
    stored_hash: str
    recomputed_hash: str
    discrepancy_details: str | None = None
    reconciled_at: datetime = Field(default_factory=datetime.now)


class MetricGlossaryItem(BaseModel):
    """Specification of a user-facing typing metric label."""

    label: str
    definition: str
    source: str
    denominator: str
    rounding: str
    limitations: str


class MetricGlossaryResponse(BaseModel):
    """Collection of authoritative metric definitions."""

    metrics: dict[str, MetricGlossaryItem]
