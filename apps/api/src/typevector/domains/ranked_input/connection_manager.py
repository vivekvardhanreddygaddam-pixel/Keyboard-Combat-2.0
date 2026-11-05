"""TypeVector Arena — Ranked WebSocket Connection Manager with Writer Fencing & Rate Limiting."""

import time
import uuid

from fastapi import WebSocket

from typevector.domains.ranked_input.protocol import ErrorMsg
from typevector.logging import get_logger

logger = get_logger("arena.connection_manager")


class RankedConnectionManager:
    """Manages active WebSocket connections for ranked attempts, enforcing writer fencing."""

    def __init__(self) -> None:
        self.active_connections: dict[uuid.UUID, WebSocket] = {}
        self.writer_generations: dict[uuid.UUID, int] = {}
        self.rate_buckets: dict[uuid.UUID, list[float]] = {}

    async def register_writer(
        self, attempt_id: uuid.UUID, generation: int, websocket: WebSocket
    ) -> None:
        """Register active writer connection for an attempt and evict existing stale sockets.

        Task 3: Writer-generation fencing. Stale connections are disconnected immediately.
        """
        existing = self.active_connections.get(attempt_id)
        if existing is not None and existing != websocket:
            logger.info(
                "connection_manager.evicting_stale_writer",
                extra={
                    "attempt_id": str(attempt_id),
                    "old_gen": self.writer_generations.get(attempt_id, 0),
                    "new_gen": generation,
                },
            )
            try:
                eviction_msg = ErrorMsg(
                    error_code="STALE_WRITER_EVICTED",
                    message="A newer writer session has taken control of this attempt.",
                    fatal=True,
                )
                await existing.send_json(eviction_msg.model_dump(mode="json"))
                # Custom close code 4409: Stale Generation
                await existing.close(code=4409, reason="Stale writer generation")
            except Exception as exc:
                logger.debug(f"Failed to cleanly close evicted socket: {exc}")

        self.active_connections[attempt_id] = websocket
        self.writer_generations[attempt_id] = generation
        self.rate_buckets[attempt_id] = []

    def check_rate_limit(self, attempt_id: uuid.UUID, max_per_sec: int = 30) -> bool:
        """Rate limit per-connection input message arrival."""
        now = time.monotonic()
        bucket = self.rate_buckets.setdefault(attempt_id, [])
        # Prune timestamps older than 1 second
        self.rate_buckets[attempt_id] = [t for t in bucket if now - t < 1.0]
        if len(self.rate_buckets[attempt_id]) >= max_per_sec:
            return False
        self.rate_buckets[attempt_id].append(now)
        return True

    def disconnect(self, attempt_id: uuid.UUID, websocket: WebSocket) -> None:
        """Deregister active connection if matching."""
        if self.active_connections.get(attempt_id) == websocket:
            self.active_connections.pop(attempt_id, None)
            self.writer_generations.pop(attempt_id, None)
            self.rate_buckets.pop(attempt_id, None)

    def get_active_count(self) -> int:
        """Return total active connected WebSocket sessions."""
        return len(self.active_connections)


# Global singleton connection manager
ranked_connection_manager = RankedConnectionManager()
