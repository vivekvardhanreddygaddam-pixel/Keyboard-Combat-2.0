"""TypeVector Arena — Operations API Router."""

import uuid

from fastapi import APIRouter
from sqlalchemy import select

from typevector.auth import AuthenticatedUser
from typevector.dependencies import DbSession
from typevector.domains.events.models import Event
from typevector.domains.operations.schemas import (
    EventLiveMetricsRead,
    PlatformHealthRead,
    RetentionJobRead,
)
from typevector.domains.operations.service import OperationsService
from typevector.domains.operations.worker_health import (
    WorkerHealthRead,
    probe_worker_and_queue_metrics,
)
from typevector.domains.organizations.models import OrganizationMember
from typevector.errors import EntityNotFoundError, ForbiddenError

router = APIRouter(prefix="/operations", tags=["Operations"])


@router.get("/retention-jobs", response_model=list[RetentionJobRead])
async def list_retention_jobs(
    current_user: AuthenticatedUser,
    session: DbSession,
) -> list[RetentionJobRead]:
    """List recent background retention sweeps (restricted to organizers and admins)."""
    is_admin = getattr(current_user, "role", None) in ("platform_admin", "organizer", "admin")
    if not is_admin:
        raise ForbiddenError("Actor is not authorized to inspect retention jobs.")

    service = OperationsService(session)
    jobs = await service.list_recent_jobs()
    return [RetentionJobRead.model_validate(j) for j in jobs]


@router.get("/events/{event_id}/live-metrics", response_model=EventLiveMetricsRead)
async def get_live_metrics(
    event_id: uuid.UUID,
    current_user: AuthenticatedUser,
    session: DbSession,
) -> EventLiveMetricsRead:
    """Fetch live operational dashboard metrics for tournament operations."""
    event = await session.get(Event, event_id)
    if not event:
        raise EntityNotFoundError(entity="Event", identifier=event_id)

    stmt = select(OrganizationMember).where(
        OrganizationMember.organization_id == event.organization_id,
        OrganizationMember.user_id == current_user.id,
    )
    membership = (await session.execute(stmt)).scalar_one_or_none()
    is_admin = getattr(current_user, "role", None) == "platform_admin" or (
        membership is not None and membership.role in ("owner", "organizer", "admin", "reviewer")
    )
    if not is_admin:
        raise ForbiddenError("Actor is not authorized to view live operational metrics.")

    service = OperationsService(session)
    return await service.get_event_live_metrics(event_id)


@router.get("/platform-health", response_model=PlatformHealthRead)
async def get_platform_health(
    current_user: AuthenticatedUser,
    session: DbSession,
) -> PlatformHealthRead:
    """Fetch global platform health signals (restricted to platform_admin and organizers)."""
    is_admin = getattr(current_user, "role", None) in ("platform_admin", "organizer", "admin")
    if not is_admin:
        raise ForbiddenError("Actor is not authorized to access platform health.")

    service = OperationsService(session)
    return await service.get_platform_health()


@router.get("/worker-health", response_model=WorkerHealthRead)
async def get_worker_health(
    current_user: AuthenticatedUser,
    session: DbSession,
) -> WorkerHealthRead:
    """Fetch background worker fleet, broker health, and queue depth metrics."""
    is_admin = getattr(current_user, "role", None) in ("platform_admin", "organizer", "admin")
    if not is_admin:
        raise ForbiddenError("Actor is not authorized to access worker health metrics.")

    return await probe_worker_and_queue_metrics(session)
