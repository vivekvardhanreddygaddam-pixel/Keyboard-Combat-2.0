"""TypeVector Arena — Ranked Input Schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AttemptSummaryRead(BaseModel):
    """Ranked attempt summary schema."""

    id: uuid.UUID
    event_id: uuid.UUID
    round_id: uuid.UUID
    user_id: uuid.UUID
    attempt_number: int
    status: str
    socket_writer_generation: int
    started_at: datetime
    completed_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class InputBatchAck(BaseModel):
    """Server durable ACK returned after PostgreSQL commit."""

    attempt_id: uuid.UUID
    batch_sequence_number: int
    writer_generation: int
    acked_at: datetime
    status: str = Field(default="COMMITTED")
