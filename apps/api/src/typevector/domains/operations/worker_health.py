"""TypeVector Arena — Background Worker and Queue Depth Telemetry.

Clearly separates:
1. Broker connectivity (Redis reachability on worker DB)
2. Worker process availability (active worker processes)
3. Task delivery and queue backlog metrics (queue depths & outbox lag)
"""

import logging
from datetime import UTC, datetime

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from typevector.config import settings
from typevector.domains.notifications.models import TransactionalOutbox

logger = logging.getLogger(__name__)


class QueueDepthMetrics(BaseModel):
    """Queue depth breakdown per dedicated worker queue."""

    outbox: int = 0
    notifications: int = 0
    exports: int = 0
    retention: int = 0
    default: int = 0


class WorkerHealthRead(BaseModel):
    """Worker and async pipeline health metrics."""

    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    broker_healthy: bool
    workers_online_count: int
    queue_depths: QueueDepthMetrics
    outbox_pending_count: int
    outbox_failed_count: int
    outbox_oldest_pending_age_seconds: float | None
    service_status: str  # healthy, degraded, critical


async def probe_worker_and_queue_metrics(session: AsyncSession) -> WorkerHealthRead:
    """Collect genuine telemetry across Celery broker, worker fleet, and PostgreSQL outbox."""
    now = datetime.now(UTC)

    # 1. Broker Probe (Redis ping on Celery broker URL)
    broker_healthy = False
    queue_depths = QueueDepthMetrics()
    try:
        from redis.asyncio import Redis

        broker_redis = Redis.from_url(settings.celery_broker_url, decode_responses=True)
        await broker_redis.ping()
        broker_healthy = True

        # Query Redis list lengths for queues (Celery standard Redis key format: queue name)
        queue_depths = QueueDepthMetrics(
            outbox=await broker_redis.llen("outbox"),
            notifications=await broker_redis.llen("notifications"),
            exports=await broker_redis.llen("exports"),
            retention=await broker_redis.llen("retention"),
            default=await broker_redis.llen("celery"),  # Celery default queue name
        )
        await broker_redis.aclose()
    except Exception as exc:
        logger.warning("Broker health probe failed: %s", exc)
        broker_healthy = False

    # 2. Worker fleet probe via Celery inspect ping
    workers_online_count = 0
    try:
        from typevector.celery_app import celery_app

        # Non-blocking inspect with timeout
        inspect = celery_app.control.inspect(timeout=0.5)
        ping_res = inspect.ping()
        if ping_res:
            workers_online_count = len(ping_res)
    except Exception:
        workers_online_count = 0

    # 3. PostgreSQL Outbox Backlog & Age
    pending_stmt = select(func.count(TransactionalOutbox.id)).where(
        TransactionalOutbox.status == "pending"
    )
    pending_count = (await session.execute(pending_stmt)).scalar_one() or 0

    failed_stmt = select(func.count(TransactionalOutbox.id)).where(
        TransactionalOutbox.status == "failed"
    )
    failed_count = (await session.execute(failed_stmt)).scalar_one() or 0

    oldest_stmt = (
        select(TransactionalOutbox.created_at)
        .where(TransactionalOutbox.status == "pending")
        .order_by(TransactionalOutbox.created_at.asc())
        .limit(1)
    )
    oldest_created = (await session.execute(oldest_stmt)).scalar_one_or_none()

    oldest_age_seconds: float | None = None
    if oldest_created:
        oldest_age_seconds = max((now - oldest_created).total_seconds(), 0.0)

    # 4. Service status synthesis
    if not broker_healthy:
        service_status = "critical"
    elif failed_count > 10 or (oldest_age_seconds and oldest_age_seconds > 300):
        service_status = "degraded"
    else:
        service_status = "healthy"

    return WorkerHealthRead(
        timestamp=now,
        broker_healthy=broker_healthy,
        workers_online_count=workers_online_count,
        queue_depths=queue_depths,
        outbox_pending_count=pending_count,
        outbox_failed_count=failed_count,
        outbox_oldest_pending_age_seconds=oldest_age_seconds,
        service_status=service_status,
    )
