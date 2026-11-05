"""TypeVector Arena — Operations Schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class RetentionJobRead(BaseModel):
    """Retention job summary schema."""

    id: uuid.UUID
    job_type: str
    records_affected: int
    status: str
    started_at: datetime
    completed_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class EventLiveMetricsRead(BaseModel):
    """Realtime operational dashboard metrics for live tournament operations."""

    event_id: uuid.UUID
    event_status: str
    event_version: int
    is_paused: bool
    total_pause_duration_seconds: int
    incident_reason: str | None = None
    active_round_number: int | None = None
    round_status: str | None = None
    round_deadline_at: datetime | None = None
    server_time_ms: int
    clock_uncertainty_ms: float
    connected_sessions_count: int
    durable_ack_latency_p95_ms: float | None = None
    outbox_lag_count: int
    postgres_healthy: bool
    redis_healthy: bool
    service_status: str


class PlatformHealthRead(BaseModel):
    """Restricted platform health metrics for administrators."""

    timestamp: datetime
    postgres_connected: bool
    redis_connected: bool
    pending_outbox_events: int
    active_events_count: int
    recent_retention_jobs: list[RetentionJobRead]
