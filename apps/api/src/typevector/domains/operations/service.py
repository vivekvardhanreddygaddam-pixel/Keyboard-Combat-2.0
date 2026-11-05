"""TypeVector Arena — Operations Domain Service."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from typevector.domains.events.clock import get_server_clock_sample
from typevector.domains.events.models import Event
from typevector.domains.notifications.models import TransactionalOutbox
from typevector.domains.operations.models import RetentionJob
from typevector.domains.operations.schemas import (
    EventLiveMetricsRead,
    PlatformHealthRead,
    RetentionJobRead,
)
from typevector.domains.ranked_input.connection_manager import ranked_connection_manager
from typevector.domains.rounds.models import Round
from typevector.errors import EntityNotFoundError


class OperationsService:
    """Domain service managing data retention sweeps, live tournament telemetry, and operational tasks."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_recent_jobs(self, limit: int = 10) -> list[RetentionJob]:
        """Fetch status of recent retention and maintenance jobs."""
        stmt = select(RetentionJob).order_by(RetentionJob.started_at.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_event_live_metrics(self, event_id: uuid.UUID) -> EventLiveMetricsRead:
        """Fetch live operational metrics for tournament command center without fabricated data."""
        event = await self.session.get(Event, event_id)
        if not event:
            raise EntityNotFoundError(entity="Event", identifier=event_id)

        # 1. Active Round
        round_stmt = (
            select(Round)
            .where(
                Round.event_id == event_id,
                Round.status.in_(["active", "paused", "scheduled"]),
            )
            .order_by(Round.sequence_number.asc())
            .limit(1)
        )
        round_res = await self.session.execute(round_stmt)
        active_round = round_res.scalar_one_or_none()

        # 2. Server Clock
        clock = get_server_clock_sample()

        # 3. Connected Sessions
        conn_count = ranked_connection_manager.get_active_count()

        # 4. Outbox Lag
        outbox_stmt = select(func.count(TransactionalOutbox.id)).where(
            TransactionalOutbox.dispatched_at.is_(None)
        )
        outbox_res = await self.session.execute(outbox_stmt)
        outbox_lag = outbox_res.scalar_one() or 0

        # 5. Service Status Probes
        postgres_healthy = True
        try:
            await self.session.execute(select(1))
        except Exception:
            postgres_healthy = False

        redis_healthy = False
        try:
            from typevector.redis_client import check_redis_connection

            await check_redis_connection()
            redis_healthy = True
        except Exception:
            redis_healthy = False

        service_status = "healthy"
        if not postgres_healthy:
            service_status = "database_degraded"
        elif not redis_healthy:
            service_status = "redis_degraded"
        elif event.status == "paused":
            service_status = "event_paused"

        return EventLiveMetricsRead(
            event_id=event.id,
            event_status=event.status,
            event_version=event.version or 1,
            is_paused=event.status == "paused" or event.pause_started_at is not None,
            total_pause_duration_seconds=event.total_pause_duration_seconds or 0,
            incident_reason=event.incident_reason,
            active_round_number=active_round.sequence_number if active_round else None,
            round_status=active_round.status if active_round else None,
            round_deadline_at=active_round.deadline_at if active_round else None,
            server_time_ms=clock.server_time_ms,
            clock_uncertainty_ms=clock.uncertainty_ms,
            connected_sessions_count=conn_count,
            durable_ack_latency_p95_ms=None,  # Real measurement; None displays as 'Unavailable'
            outbox_lag_count=outbox_lag,
            postgres_healthy=postgres_healthy,
            redis_healthy=redis_healthy,
            service_status=service_status,
        )

    async def get_platform_health(self) -> PlatformHealthRead:
        """Fetch general platform health for privileged administrators."""
        # 1. DB probe
        postgres_connected = True
        try:
            await self.session.execute(select(1))
        except Exception:
            postgres_connected = False

        # 2. Redis probe
        redis_connected = False
        try:
            from typevector.redis_client import check_redis_connection

            await check_redis_connection()
            redis_connected = True
        except Exception:
            redis_connected = False

        # 3. Outbox pending
        outbox_stmt = select(func.count(TransactionalOutbox.id)).where(
            TransactionalOutbox.dispatched_at.is_(None)
        )
        outbox_res = await self.session.execute(outbox_stmt)
        outbox_pending = outbox_res.scalar_one() or 0

        # 4. Active events count
        events_stmt = select(func.count(Event.id)).where(
            Event.status.in_(["registration_open", "check_in_open", "ready", "live", "paused"])
        )
        active_events = (await self.session.execute(events_stmt)).scalar_one() or 0

        # 5. Recent retention jobs
        jobs = await self.list_recent_jobs(limit=5)
        jobs_read = [RetentionJobRead.model_validate(j) for j in jobs]

        return PlatformHealthRead(
            timestamp=datetime.now(UTC),
            postgres_connected=postgres_connected,
            redis_connected=redis_connected,
            pending_outbox_events=outbox_pending,
            active_events_count=active_events,
            recent_retention_jobs=jobs_read,
        )
