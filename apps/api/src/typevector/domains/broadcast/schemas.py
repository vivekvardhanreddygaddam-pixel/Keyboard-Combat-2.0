"""TypeVector Arena — Broadcast Schemas (Ephemeral Fanout)."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class BroadcastChannelSubscription(BaseModel):
    """Channel subscription request for spectator stream."""

    event_id: uuid.UUID
    channel_type: str = "spectator_feed"  # spectator_feed, leaderboard, system_alerts


class BroadcastEventMessage(BaseModel):
    """Payload format dispatched over Redis pub/sub to active subscribers."""

    event_id: uuid.UUID
    message_type: str
    payload: dict[str, Any]
    timestamp: datetime
