"""TypeVector Arena — Spectator Broadcast Connection Manager with Rate Throttling."""

import json
import logging
import time
import uuid
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)

# Enforce 1 Hz maximum frequency for leaderboard broadcast updates
# to guarantee zero contention with participant input admission / ACKs.
LEADERBOARD_THROTTLE_SECONDS = 1.0


class SpectatorConnectionManager:
    """Manages active spectator and lobby WebSocket connections with 1 Hz throttled updates."""

    def __init__(self) -> None:
        self._active_connections: dict[uuid.UUID, set[WebSocket]] = defaultdict(set)
        self._last_leaderboard_broadcast: dict[uuid.UUID, float] = {}

    async def connect(self, event_id: uuid.UUID, websocket: WebSocket) -> None:
        """Accept and register a new spectator WebSocket."""
        await websocket.accept()
        self._active_connections[event_id].add(websocket)
        logger.info(
            "Spectator connected to event %s (total: %d)",
            event_id,
            len(self._active_connections[event_id]),
        )

    def disconnect(self, event_id: uuid.UUID, websocket: WebSocket) -> None:
        """Unregister a disconnected spectator."""
        if event_id in self._active_connections:
            self._active_connections[event_id].discard(websocket)
            if not self._active_connections[event_id]:
                del self._active_connections[event_id]
        logger.info("Spectator disconnected from event %s", event_id)

    async def broadcast_event_message(
        self,
        event_id: uuid.UUID,
        message_type: str,
        payload: dict[str, Any],
    ) -> int:
        """Broadcast lifecycle or round state changes to all event spectators immediately."""
        connections = self._active_connections.get(event_id, set())
        if not connections:
            return 0

        envelope = {
            "version": "arena-ws-v1",
            "type": message_type,
            "event_id": str(event_id),
            "payload": payload,
            "server_time": datetime.now(UTC).isoformat(),
        }
        text_data = json.dumps(envelope)

        dead_connections: list[WebSocket] = []
        sent_count = 0
        for ws in list(connections):
            try:
                await ws.send_text(text_data)
                sent_count += 1
            except Exception:
                dead_connections.append(ws)

        for ws in dead_connections:
            self.disconnect(event_id, ws)

        return sent_count

    async def broadcast_leaderboard_throttled(
        self,
        event_id: uuid.UUID,
        leaderboard_data: list[dict[str, Any]],
    ) -> bool:
        """Broadcast non-authoritative leaderboard update throttled to 1 Hz max."""
        now = time.monotonic()
        last_time = self._last_leaderboard_broadcast.get(event_id, 0.0)
        if now - last_time < LEADERBOARD_THROTTLE_SECONDS:
            # Throttled; drop non-authoritative high-frequency snapshot
            return False

        self._last_leaderboard_broadcast[event_id] = now
        await self.broadcast_event_message(
            event_id=event_id,
            message_type="LEADERBOARD_SNAPSHOT",
            payload={"rankings": leaderboard_data},
        )
        return True


spectator_manager = SpectatorConnectionManager()
