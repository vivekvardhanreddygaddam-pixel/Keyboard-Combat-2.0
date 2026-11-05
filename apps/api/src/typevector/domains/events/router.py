"""TypeVector Arena — Events API Router with Full Lifecycle Management."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select

from typevector.auth import AuthenticatedUser, enforce_csrf
from typevector.common.schemas import PaginationParams
from typevector.dependencies import DbSession
from typevector.domains.events.clock import ServerClockSample, get_server_clock_sample
from typevector.domains.events.models import Event
from typevector.domains.events.schemas import (
    EventCreate,
    EventDetailRead,
    EventPauseRequest,
    EventRead,
    EventResumeRequest,
    EventStatusRead,
    EventTransitionRequest,
    EventUpdate,
    ParticipantCheckInResponse,
)
from typevector.domains.events.service import EventService
from typevector.domains.organizations.models import OrganizationMember
from typevector.errors import EntityNotFoundError, ForbiddenError

router = APIRouter(prefix="/events", tags=["Events"])


async def _resolve_actor_roles_for_event(
    session: DbSession,
    user: AuthenticatedUser,
    event_id: uuid.UUID,
) -> tuple[Event, list[str]]:
    """Helper resolving event and the authenticated user's authoritative roles."""
    event = await session.get(Event, event_id)
    if not event:
        raise EntityNotFoundError(entity="Event", identifier=event_id)

    roles: list[str] = []
    if getattr(user, "role", None) == "platform_admin":
        roles.append("platform_admin")

    stmt = select(OrganizationMember).where(
        OrganizationMember.organization_id == event.organization_id,
        OrganizationMember.user_id == user.id,
    )
    res = await session.execute(stmt)
    membership = res.scalar_one_or_none()
    if membership and membership.role in ("owner", "organizer", "admin"):
        roles.append("org_admin")

    return event, roles


@router.get("", response_model=list[EventRead])
async def list_events(
    session: DbSession,
    pagination: Annotated[PaginationParams, Depends()],
) -> list[EventRead]:
    """List public published events."""
    service = EventService(session)
    events = await service.list_published(limit=pagination.limit, offset=pagination.offset)
    return [EventRead.model_validate(e) for e in events]


@router.post(
    "",
    response_model=EventRead,
    dependencies=[Depends(enforce_csrf)],
)
async def create_event(
    payload: EventCreate,
    current_user: AuthenticatedUser,
    session: DbSession,
) -> EventRead:
    """Create a draft event within an organization (requires org_admin or platform_admin)."""
    stmt = select(OrganizationMember).where(
        OrganizationMember.organization_id == payload.organization_id,
        OrganizationMember.user_id == current_user.id,
    )
    membership = (await session.execute(stmt)).scalar_one_or_none()
    is_admin = getattr(current_user, "role", None) == "platform_admin" or (
        membership is not None and membership.role in ("owner", "organizer", "admin")
    )
    if not is_admin:
        raise ForbiddenError("Actor is not authorized to create events for this organization.")

    service = EventService(session)
    event = await service.create_event(
        organization_id=payload.organization_id,
        slug=payload.slug,
        title=payload.title,
        description=payload.description,
        capacity=payload.capacity,
        is_prize_event=payload.is_prize_event,
        min_accuracy_pct=payload.min_accuracy_pct,
        duration_seconds=payload.duration_seconds,
        scoring_formula=payload.scoring_formula,
        actor_id=current_user.id,
    )
    await session.commit()
    return EventRead.model_validate(event)


@router.patch(
    "/{event_id}",
    response_model=EventRead,
    dependencies=[Depends(enforce_csrf)],
)
async def update_event(
    event_id: uuid.UUID,
    payload: EventUpdate,
    current_user: AuthenticatedUser,
    session: DbSession,
) -> EventRead:
    """Update event while in DRAFT status."""
    _event, roles = await _resolve_actor_roles_for_event(session, current_user, event_id)
    if not roles:
        raise ForbiddenError("Actor is not authorized to edit this event.")

    service = EventService(session)
    updated = await service.update_draft_event(
        event_id=event_id,
        actor_id=current_user.id,
        title=payload.title,
        description=payload.description,
        capacity=payload.capacity,
        is_prize_event=payload.is_prize_event,
    )
    await session.commit()
    return EventRead.model_validate(updated)


@router.get("/organization/{organization_id}", response_model=list[EventRead])
async def list_organization_events(
    organization_id: uuid.UUID,
    current_user: AuthenticatedUser,
    session: DbSession,
    pagination: Annotated[PaginationParams, Depends()],
    status: str | None = None,
) -> list[EventRead]:
    """List events for an organization (accessible to org members and platform admins)."""
    stmt = select(OrganizationMember).where(
        OrganizationMember.organization_id == organization_id,
        OrganizationMember.user_id == current_user.id,
    )
    membership = (await session.execute(stmt)).scalar_one_or_none()
    is_admin = getattr(current_user, "role", None) == "platform_admin" or membership is not None
    if not is_admin:
        raise ForbiddenError("Actor is not authorized to view organization event roster.")

    service = EventService(session)
    events = await service.list_for_organization(
        organization_id=organization_id,
        status=status,
        limit=pagination.limit,
        offset=pagination.offset,
    )
    return [EventRead.model_validate(e) for e in events]


@router.get("/{event_id}/detail", response_model=EventDetailRead)
async def get_event_detail(
    event_id: uuid.UUID,
    session: DbSession,
) -> EventDetailRead:
    """Fetch event details along with all rulesets."""
    from sqlalchemy.orm import selectinload

    stmt = select(Event).where(Event.id == event_id).options(selectinload(Event.rulesets))
    res = await session.execute(stmt)
    full_event = res.scalar_one_or_none()
    if not full_event:
        raise EntityNotFoundError(entity="Event", identifier=event_id)
    return EventDetailRead.model_validate(full_event)


@router.get("/clock", response_model=ServerClockSample)
async def get_clock() -> ServerClockSample:
    """Return authoritative server clock sample with bounded uncertainty."""
    return get_server_clock_sample()


@router.get("/{event_id}", response_model=EventRead)
async def get_event(event_id: uuid.UUID, session: DbSession) -> EventRead:
    """Fetch event details by UUID."""
    service = EventService(session)
    event = await service.get_by_id(event_id)
    return EventRead.model_validate(event)


@router.get("/{event_id}/status", response_model=EventStatusRead)
async def get_event_status(event_id: uuid.UUID, session: DbSession) -> EventStatusRead:
    """Fetch live event status, pause metrics, and server clock timestamp."""
    service = EventService(session)
    return await service.get_event_status_read(event_id)


@router.post(
    "/{event_id}/transition",
    response_model=EventRead,
    dependencies=[Depends(enforce_csrf)],
)
async def transition_event_status(
    event_id: uuid.UUID,
    payload: EventTransitionRequest,
    current_user: AuthenticatedUser,
    session: DbSession,
) -> EventRead:
    """Execute authoritative event lifecycle transition with optimistic locking."""
    _event, roles = await _resolve_actor_roles_for_event(session, current_user, event_id)
    if not roles:
        raise ForbiddenError("Actor is not authorized to transition event lifecycle.")

    service = EventService(session)
    updated_event = await service.transition_event(
        event_id=event_id,
        target_status=payload.target_status,
        actor_id=current_user.id,
        actor_roles=roles,
        expected_version=payload.expected_version,
        reason=payload.reason,
    )
    await session.commit()
    return EventRead.model_validate(updated_event)


@router.post(
    "/{event_id}/pause",
    response_model=EventRead,
    dependencies=[Depends(enforce_csrf)],
)
async def pause_event_competition(
    event_id: uuid.UUID,
    payload: EventPauseRequest,
    current_user: AuthenticatedUser,
    session: DbSession,
) -> EventRead:
    """Pause live competition event under published fairness policy."""
    _event, roles = await _resolve_actor_roles_for_event(session, current_user, event_id)
    if not roles:
        raise ForbiddenError("Actor is not authorized to pause this event.")

    service = EventService(session)
    updated_event = await service.pause_event(
        event_id=event_id,
        actor_id=current_user.id,
        actor_roles=roles,
        expected_version=payload.expected_version,
        reason=payload.reason,
    )
    await session.commit()
    return EventRead.model_validate(updated_event)


@router.post(
    "/{event_id}/resume",
    response_model=EventRead,
    dependencies=[Depends(enforce_csrf)],
)
async def resume_event_competition(
    event_id: uuid.UUID,
    payload: EventResumeRequest,
    current_user: AuthenticatedUser,
    session: DbSession,
) -> EventRead:
    """Resume paused competition event with uniform deadline extensions."""
    _event, roles = await _resolve_actor_roles_for_event(session, current_user, event_id)
    if not roles:
        raise ForbiddenError("Actor is not authorized to resume this event.")

    service = EventService(session)
    updated_event = await service.resume_event(
        event_id=event_id,
        actor_id=current_user.id,
        actor_roles=roles,
        expected_version=payload.expected_version,
        reason=payload.reason,
    )
    await session.commit()
    return EventRead.model_validate(updated_event)


@router.post(
    "/{event_id}/check-in",
    response_model=ParticipantCheckInResponse,
    dependencies=[Depends(enforce_csrf)],
)
async def check_in_for_event(
    event_id: uuid.UUID,
    current_user: AuthenticatedUser,
    session: DbSession,
) -> ParticipantCheckInResponse:
    """Check in authenticated participant during CHECK_IN_OPEN or READY."""
    service = EventService(session)
    reg = await service.check_in_participant(event_id=event_id, user_id=current_user.id)
    await session.commit()
    return ParticipantCheckInResponse.model_validate(reg)


@router.post(
    "/{event_id}/ready",
    response_model=ParticipantCheckInResponse,
    dependencies=[Depends(enforce_csrf)],
)
async def signal_readiness_for_event(
    event_id: uuid.UUID,
    current_user: AuthenticatedUser,
    session: DbSession,
) -> ParticipantCheckInResponse:
    """Signal participant readiness for the upcoming round."""
    service = EventService(session)
    reg = await service.mark_participant_ready(event_id=event_id, user_id=current_user.id)
    await session.commit()
    return ParticipantCheckInResponse.model_validate(reg)
