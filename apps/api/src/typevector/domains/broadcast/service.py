"""TypeVector Arena — Broadcast Service (Ephemeral Fanout)."""

import json
import uuid
from typing import Any

from typevector.redis_client import get_redis_client


class BroadcastService:
    """Service managing ephemeral fanout and Redis pub/sub channels."""

    async def publish_event(
        self, event_id: uuid.UUID, channel: str, message: dict[str, Any]
    ) -> None:
        """Publish ephemeral message to Redis fanout channel (non-authoritative)."""
        redis = get_redis_client()
        channel_name = f"arena:broadcast:{event_id}:{channel}"
        await redis.publish(channel_name, json.dumps(message, default=str))
