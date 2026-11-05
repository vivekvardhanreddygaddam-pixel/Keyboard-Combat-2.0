"""TypeVector Arena — Results Schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PublishedRankRowRead(BaseModel):
    """Row in published official standings."""

    rank_order: int
    user_id: uuid.UUID
    score_id: uuid.UUID
    gross_wpm: float
    net_wpm: float
    accuracy_pct: float
    arena_score: int
    tier: str

    model_config = ConfigDict(from_attributes=True)


class PublishedResultRead(BaseModel):
    """Full published official result schema."""

    id: uuid.UUID
    event_id: uuid.UUID
    version_number: int
    published_by_user_id: uuid.UUID
    signed_hash: str
    is_current: bool
    published_at: datetime
    note: str | None = None
    previous_version_id: uuid.UUID | None = None
    amendment_reason: str | None = None
    ruleset_approval_status: str
    rows: list[PublishedRankRowRead] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class PublicLeaderboardRow(BaseModel):
    """Privacy-sanitized leaderboard row (Zero PII)."""

    rank: int
    display_alias: str = Field(..., description="Public alias or masked participant code")
    arena_score: int
    net_wpm: float
    accuracy_pct: float
    tier: str
    is_eligible: bool


class PublicPublishedResultRead(BaseModel):
    """Publicly viewable official tournament result without private PII or integrity notes."""

    event_id: uuid.UUID
    version_number: int
    published_at: datetime
    is_current: bool
    is_amended: bool
    amendment_reason: str | None = None
    signed_hash: str
    total_ranked_participants: int
    rankings: list[PublicLeaderboardRow]


class ResultPublishRequest(BaseModel):
    """Payload to publish official initial results."""

    note: str | None = Field(default=None, max_length=500)


class ResultAmendRequest(BaseModel):
    """Payload to publish an amended results version following appeals."""

    amendment_reason: str = Field(
        ..., min_length=10, max_length=1000, description="Mandatory audit rationale for amendment"
    )


class ResultPreviewRow(BaseModel):
    user_id: uuid.UUID
    display_name: str
    rank_order: int
    gross_wpm: float
    net_wpm: float
    accuracy_pct: float
    arena_score: int
    tier: str


class ResultPreviewRead(BaseModel):
    event_id: uuid.UUID
    total_participants: int
    signed_hash: str
    ruleset_approval_status: str
    is_prize_event: bool
    can_publish: bool
    block_reason: str | None = None
    rankings: list[ResultPreviewRow]
