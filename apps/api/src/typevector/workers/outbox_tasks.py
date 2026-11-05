"""TypeVector Arena — Celery Background Outbox Tasks.

Executes periodic outbox event sweeping and reconciliation of stuck events.
Ensures that outbox events committed to PostgreSQL are safely dispatched to Redis.
"""

import asyncio
import logging
from typing import Any

from celery import shared_task

from typevector.database import async_session_factory
from typevector.domains.notifications.outbox_dispatcher import OutboxDispatcher
from typevector.workers.logging_context import task_logging_wrapper

logger = logging.getLogger(__name__)


@shared_task(
    name="typevector.workers.outbox_tasks.sweep_pending_outbox",
    max_retries=2,
    default_retry_delay=5,
)
@task_logging_wrapper("sweep_pending_outbox")
def sweep_pending_outbox(
    batch_size: int = 50,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """Poll and dispatch pending PostgreSQL outbox events to Redis."""

    async def _run_sweep() -> int:
        async with async_session_factory() as session:
            dispatcher = OutboxDispatcher(session)
            dispatched = await dispatcher.dispatch_pending(batch_size=batch_size)
            await session.commit()
            return dispatched

    dispatched = asyncio.run(_run_sweep())
    return {"dispatched_count": dispatched, "status": "completed"}


@shared_task(
    name="typevector.workers.outbox_tasks.reconcile_stuck_outbox",
    max_retries=2,
    default_retry_delay=10,
)
@task_logging_wrapper("reconcile_stuck_outbox")
def reconcile_stuck_outbox(
    timeout_seconds: int = 300,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """Find and recover outbox events stuck in in_progress state."""

    async def _run_reconciliation() -> int:
        async with async_session_factory() as session:
            dispatcher = OutboxDispatcher(session)
            reconciled = await dispatcher.reconcile_stuck(timeout_seconds=timeout_seconds)
            await session.commit()
            return reconciled

    reconciled = asyncio.run(_run_reconciliation())
    return {"reconciled_count": reconciled, "status": "completed"}
