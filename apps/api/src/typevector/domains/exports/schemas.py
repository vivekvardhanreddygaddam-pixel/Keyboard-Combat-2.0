"""TypeVector Arena — Exports Schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ExportJobRead(BaseModel):
    """Export job status schema."""

    id: uuid.UUID
    organization_id: uuid.UUID
    export_type: str
    status: str
    row_count: int
    created_at: datetime
    completed_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class ExportJobCreateRequest(BaseModel):
    """Payload to request an event or organization data export."""

    organization_id: uuid.UUID
    export_type: str  # event_standings, roster, audit_trail
    event_id: uuid.UUID | None = None
