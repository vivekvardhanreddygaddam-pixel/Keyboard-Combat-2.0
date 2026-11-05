"""TypeVector Arena — Rounds Schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RoundRead(BaseModel):
    """Round status and schedule schema."""

    id: uuid.UUID
    event_id: uuid.UUID
    sequence_number: int
    status: str
    version: int
    scheduled_start_at: datetime | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    deadline_at: datetime | None = None
    total_pause_duration_seconds: int = 0

    model_config = ConfigDict(from_attributes=True)


class RoundStartRequest(BaseModel):
    """Round start payload with optimistic version locking."""

    expected_version: int = Field(..., description="Optimistic locking expected version")


class RoundCloseRequest(BaseModel):
    """Round close payload with optimistic version locking."""

    expected_version: int = Field(..., description="Optimistic locking expected version")


class RoundVoidRequest(BaseModel):
    """Round void payload with optimistic version locking and audit reason."""

    expected_version: int = Field(..., description="Optimistic locking expected version")
    reason: str = Field(..., min_length=3, max_length=255, description="Audited voiding reason")


class PromptRead(BaseModel):
    """Challenge prompt schema without revealing text before start."""

    id: uuid.UUID
    round_id: uuid.UUID
    version_number: int
    token_count: int
    checksum_sha256: str
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class ChallengePromptDetailRead(BaseModel):
    """Full challenge prompt read schema including content for authorized organizers."""

    id: uuid.UUID
    round_id: uuid.UUID
    event_id: uuid.UUID
    version_number: int
    content: str
    token_count: int
    checksum_sha256: str
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RoundCreate(BaseModel):
    """Round creation payload."""

    event_id: uuid.UUID
    sequence_number: int = Field(ge=1, le=100)
    prompt_content: str | None = Field(default=None, min_length=5, max_length=10000)
    scheduled_start_at: datetime | None = None


class RoundUpdate(BaseModel):
    """Round update payload."""

    sequence_number: int | None = Field(default=None, ge=1, le=100)
    scheduled_start_at: datetime | None = None


class ChallengePromptCreate(BaseModel):
    """Challenge prompt assignment payload."""

    round_id: uuid.UUID
    event_id: uuid.UUID
    content: str = Field(min_length=5, max_length=10000)
