"""TypeVector Arena — Transactional Outbox Dispatcher with Resilient Redis Fanout.

Architectural Invariants:
1. PostgreSQL is the exclusive system of record. Redis is strictly an ephemeral fanout broker.
2. Redis unavailability or network partitions must NEVER block database transactions.
3. Concurrency-safe row claiming prevents duplicate processing across parallel workers.
4. Poison payloads (unparseable or corrupted JSON) are isolated and marked failed without halting the worker.
"""

import contextlib
import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Final

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from typevector.domains.notifications.models import TransactionalOutbox
from typevector.redis_client import get_redis_client

logger = logging.getLogger(__name__)

MAX_OUTBOX_RETRIES: Final[int] = 5


class OutboxDispatcher:
    """Dispatches pending outbox events to Redis pub/sub with resilient failure tolerance."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def dispatch_pending(self, batch_size: int = 50) -> int:
        """Poll and dispatch pending outbox events with safe row claiming."""
        now = datetime.now(UTC)

        stmt = (
            select(TransactionalOutbox)
            .where(
                TransactionalOutbox.status == "pending",
                TransactionalOutbox.retry_count < MAX_OUTBOX_RETRIES,
            )
            .order_by(TransactionalOutbox.created_at.asc())
            .limit(batch_size)
        )

        # Attempt concurrency-safe row locking if supported by the backend dialect
        with contextlib.suppress(Exception):
            stmt = stmt.with_for_update(skip_locked=True)

        res = await self.session.execute(stmt)
        pending_events = list(res.scalars().all())

        if not pending_events:
            return 0

        dispatched_count = 0
        try:
            redis_client = get_redis_client()
        except Exception as exc:
            logger.warning(
                "Redis client acquisition failed; postponing outbox dispatch: %s",
                exc,
            )
            return 0

        for event in pending_events:
            # Poison payload guard
            try:
                channel = self._resolve_channel(event)
                payload_str = json.dumps(
                    {
                        "outbox_id": str(event.id),
                        "event_type": event.event_type,
                        "payload": event.payload_json,
                        "dispatched_at": now.isoformat(),
                    }
                )
            except (TypeError, ValueError, AttributeError) as json_err:
                # Permanent failure: poison payload cannot be serialized
                event.status = "failed"
                event.retry_count = MAX_OUTBOX_RETRIES
                logger.error(
                    "Poison payload in outbox event %s; marked failed: %s",
                    event.id,
                    json_err,
                )
                continue

            try:
                await redis_client.publish(channel, payload_str)
                event.status = "dispatched"
                event.dispatched_at = now
                dispatched_count += 1
            except Exception as exc:
                event.retry_count += 1
                logger.warning(
                    "Redis pub/sub delivery failed for outbox %s (attempt %d/%d): %s",
                    event.id,
                    event.retry_count,
                    MAX_OUTBOX_RETRIES,
                    exc,
                )
                if event.retry_count >= MAX_OUTBOX_RETRIES:
                    event.status = "failed"

        await self.session.flush()
        return dispatched_count

    async def reconcile_stuck(self, timeout_seconds: int = 300) -> int:
        """Find and recover outbox events stuck in 'in_progress' due to worker failure."""
        threshold = datetime.now(UTC) - timedelta(seconds=timeout_seconds)
        stmt = (
            select(TransactionalOutbox)
            .where(
                TransactionalOutbox.status == "in_progress",
                TransactionalOutbox.created_at < threshold,
            )
            .limit(100)
        )
        res = await self.session.execute(stmt)
        stuck_events = list(res.scalars().all())

        reconciled = 0
        for event in stuck_events:
            event.status = "pending"
            event.retry_count += 1
            if event.retry_count >= MAX_OUTBOX_RETRIES:
                event.status = "failed"
            reconciled += 1
            logger.warning(
                "Reconciled stuck outbox event %s (attempt %d/%d)",
                event.id,
                event.retry_count,
                MAX_OUTBOX_RETRIES,
            )

        if reconciled > 0:
            await self.session.flush()
        return reconciled

    def _resolve_channel(self, event: TransactionalOutbox) -> str:
        """Map outbox event types to partitioned Redis channel namespaces."""
        event_id = (
            event.payload_json.get("event_id") if isinstance(event.payload_json, dict) else None
        )
        if event.event_type.startswith("arena:"):
            if event_id and "{event_id}" in event.event_type:
                return event.event_type.format(event_id=event_id)
            if event_id and not event.event_type.count(":") > 2:
                # e.g. arena:events:lifecycle -> arena:events:{event_id}:lifecycle
                parts = event.event_type.split(":")
                return f"arena:events:{event_id}:{parts[-1]}"
            return event.event_type

        # Fallback format: arena:events:{event_id}:{event_type}
        if event_id:
            return f"arena:events:{event_id}:{event.event_type}"
        return f"arena:global:{event.event_type}"
