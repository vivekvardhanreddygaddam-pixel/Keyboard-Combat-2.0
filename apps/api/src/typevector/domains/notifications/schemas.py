"""TypeVector Arena — Notifications Schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class NotificationDeliveryRead(BaseModel):
    """Notification delivery status schema."""

    id: uuid.UUID
    user_id: uuid.UUID
    notification_type: str
    recipient: str
    status: str
    sent_at: datetime | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
