"""TypeVector Arena — Registrations Schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class RegistrationRead(BaseModel):
    """Registration status schema."""

    id: uuid.UUID
    event_id: uuid.UUID
    user_id: uuid.UUID
    status: str
    registered_at: datetime
    confirmed_at: datetime | None
    cancelled_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class RegistrationCreate(BaseModel):
    """Request payload to register for an event."""

    claim_id: uuid.UUID | None = None


class EventCapacityStatus(BaseModel):
    """Event capacity and roster summary."""

    event_id: uuid.UUID
    capacity: int
    confirmed_count: int
    is_full: bool
    status: str


class RosterParticipantRead(BaseModel):
    """Detailed participant roster read schema for event organizers."""

    registration_id: uuid.UUID
    event_id: uuid.UUID
    user_id: uuid.UUID
    display_name: str
    email: str
    status: str
    registered_at: datetime
    confirmed_at: datetime | None = None
    cancelled_at: datetime | None = None
    checked_in_at: datetime | None = None
    is_ready: bool = False
    ready_at: datetime | None = None
    is_verified: bool = False
    institution_name: str | None = None


class RosterStatusUpdateRequest(BaseModel):
    """Organizer manual correction payload."""

    target_status: str  # confirmed, checked_in, cancelled, no_show
    reason: str
