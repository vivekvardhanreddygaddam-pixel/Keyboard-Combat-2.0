"""TypeVector Arena — Events Schemas."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EventRead(BaseModel):
    """Event summary schema."""

    id: uuid.UUID
    organization_id: uuid.UUID
    slug: str
    title: str
    description: str | None
    status: str
    capacity: int
    version: int
    is_prize_event: bool = False
    ruleset_approval_status: str = "draft_awaiting_approval"
    pause_started_at: datetime | None = None
    total_pause_duration_seconds: int = 0
    incident_reason: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EventRulesetRead(BaseModel):
    """Immutable versioned rule specification read schema."""

    id: uuid.UUID
    event_id: uuid.UUID
    version_number: int
    min_accuracy_pct: float
    duration_seconds: int
    scoring_formula: str
    ruleset_json: dict[str, Any]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EventDetailRead(EventRead):
    """Event detailed schema including rulesets."""

    rulesets: list[EventRulesetRead] = []


class EventCreate(BaseModel):
    """Event creation payload."""

    organization_id: uuid.UUID
    slug: str = Field(min_length=2, max_length=100, pattern=r"^[a-z0-9-]+$")
    title: str = Field(min_length=3, max_length=255)
    description: str | None = None
    capacity: int = Field(default=100, ge=2, le=10000)
    is_prize_event: bool = False
    min_accuracy_pct: float = Field(default=90.0, ge=50.0, le=100.0)
    duration_seconds: int = Field(default=60, ge=10, le=3600)
    scoring_formula: str = "arena-score-v1"


class EventUpdate(BaseModel):
    """Event update payload (only allowed while in DRAFT status)."""

    title: str | None = Field(default=None, min_length=3, max_length=255)
    description: str | None = None
    capacity: int | None = Field(default=None, ge=2, le=10000)
    is_prize_event: bool | None = None


class EventTransitionRequest(BaseModel):
    """Event lifecycle transition payload."""

    target_status: str = Field(..., description="Target lifecycle state")
    expected_version: int = Field(..., description="Optimistic locking expected version")
    reason: str | None = Field(
        default=None, max_length=255, description="Audited transition reason"
    )


class EventPauseRequest(BaseModel):
    """Event pause request payload."""

    expected_version: int = Field(..., description="Optimistic locking expected version")
    reason: str = Field(..., min_length=3, max_length=255, description="Audited reason for pause")


class EventResumeRequest(BaseModel):
    """Event resume request payload."""

    expected_version: int = Field(..., description="Optimistic locking expected version")
    reason: str = Field(
        ..., min_length=3, max_length=255, description="Audited reason for resuming"
    )


class EventStatusRead(BaseModel):
    """Realtime event status snapshot."""

    event_id: uuid.UUID
    status: str
    version: int
    is_paused: bool
    pause_started_at: datetime | None = None
    total_pause_duration_seconds: int = 0
    incident_reason: str | None = None
    active_round_id: uuid.UUID | None = None
    round_deadline_at: datetime | None = None
    server_time_ms: int

    model_config = ConfigDict(from_attributes=True)


class ParticipantCheckInResponse(BaseModel):
    """Participant check-in & readiness response."""

    event_id: uuid.UUID
    user_id: uuid.UUID
    status: str
    checked_in_at: datetime | None = None
    is_ready: bool = False
    ready_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)
