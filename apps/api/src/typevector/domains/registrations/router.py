"""TypeVector Arena — Registrations API Router."""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select

from typevector.auth import AuthenticatedUser, enforce_csrf
from typevector.dependencies import DbSession
from typevector.domains.events.models import Event
from typevector.domains.organizations.models import OrganizationMember
from typevector.domains.registrations.schemas import (
    EventCapacityStatus,
    RegistrationRead,
    RosterParticipantRead,
    RosterStatusUpdateRequest,
)
from typevector.domains.registrations.service import RegistrationService
from typevector.errors import EntityNotFoundError, ForbiddenError

router = APIRouter(prefix="/registrations", tags=["Registrations"])


@router.post(
    "/{event_id}",
    response_model=RegistrationRead,
    dependencies=[Depends(enforce_csrf)],
)
async def register_for_event(
    event_id: uuid.UUID,
    current_user: AuthenticatedUser,
    session: DbSession,
) -> RegistrationRead:
    """Atomically register the authenticated user for an event with capacity locking."""
    service = RegistrationService(session)
    reg, _created = await service.register_for_event(
        event_id=event_id,
        user_id=current_user.id,
    )
    return RegistrationRead.model_validate(reg)


@router.delete(
    "/{event_id}",
    response_model=RegistrationRead,
    dependencies=[Depends(enforce_csrf)],
)
async def cancel_my_registration(
    event_id: uuid.UUID,
    current_user: AuthenticatedUser,
    session: DbSession,
) -> RegistrationRead:
    """Cancel the authenticated user's registration and release reserved capacity."""
    service = RegistrationService(session)
    reg = await service.cancel_registration(
        event_id=event_id,
        user_id=current_user.id,
        actor_id=current_user.id,
    )
    return RegistrationRead.model_validate(reg)


@router.get("/my", response_model=list[RegistrationRead])
async def list_my_registrations(
    current_user: AuthenticatedUser,
    session: DbSession,
) -> list[RegistrationRead]:
    """List all event registrations belonging to the authenticated participant."""
    service = RegistrationService(session)
    regs = await service.list_user_registrations(current_user.id)
    return [RegistrationRead.model_validate(r) for r in regs]


@router.get("/{event_id}/capacity", response_model=EventCapacityStatus)
async def get_event_capacity(
    event_id: uuid.UUID,
    session: DbSession,
) -> EventCapacityStatus:
    """Public summary of event capacity, confirmed participants, and fill status."""
    service = RegistrationService(session)
    return await service.get_capacity_status(event_id)


@router.get("/{event_id}/{user_id}", response_model=RegistrationRead)
async def get_registration_status(
    event_id: uuid.UUID,
    user_id: uuid.UUID,
    current_user: AuthenticatedUser,
    session: DbSession,
) -> RegistrationRead:
    """Check participant registration status (caller must be self or event organizer)."""
    # IDOR Check: Caller must be the participant, platform admin, or an organizer of the host org
    if current_user.id != user_id and current_user.role != "platform_admin":
        event = await session.get(Event, event_id)
        if not event:
            raise EntityNotFoundError(entity="Event", identifier=event_id)

        stmt = select(OrganizationMember).where(
            OrganizationMember.organization_id == event.organization_id,
            OrganizationMember.user_id == current_user.id,
            OrganizationMember.role.in_(["owner", "organizer", "reviewer"]),
        )
        res = await session.execute(stmt)
        if not res.scalar_one_or_none():
            raise ForbiddenError(
                "You are not authorized to view another participant's registration."
            )

    service = RegistrationService(session)
    reg = await service.get_registration(event_id, user_id)
    return RegistrationRead.model_validate(reg)


@router.get("/{event_id}/roster", response_model=list[RosterParticipantRead])
async def list_event_roster(
    event_id: uuid.UUID,
    current_user: AuthenticatedUser,
    session: DbSession,
) -> list[RosterParticipantRead]:
    """List participant roster for an event with identity claims and check-in readiness."""
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
        raise ForbiddenError("Actor is not authorized to view the participant roster.")

    service = RegistrationService(session)
    roster_rows = await service.list_roster_for_event(event_id)
    return [RosterParticipantRead(**row) for row in roster_rows]


@router.patch(
    "/{event_id}/roster/{user_id}",
    response_model=RegistrationRead,
    dependencies=[Depends(enforce_csrf)],
)
async def update_roster_status(
    event_id: uuid.UUID,
    user_id: uuid.UUID,
    payload: RosterStatusUpdateRequest,
    current_user: AuthenticatedUser,
    session: DbSession,
) -> RegistrationRead:
    """Allow authorized organizers to manually correct a registration status with audit trail."""
    event = await session.get(Event, event_id)
    if not event:
        raise EntityNotFoundError(entity="Event", identifier=event_id)

    stmt = select(OrganizationMember).where(
        OrganizationMember.organization_id == event.organization_id,
        OrganizationMember.user_id == current_user.id,
    )
    membership = (await session.execute(stmt)).scalar_one_or_none()
    is_admin = getattr(current_user, "role", None) == "platform_admin" or (
        membership is not None and membership.role in ("owner", "organizer", "admin")
    )
    if not is_admin:
        raise ForbiddenError("Actor is not authorized to modify registration statuses.")

    service = RegistrationService(session)
    reg = await service.organizer_update_status(
        event_id=event_id,
        user_id=user_id,
        target_status=payload.target_status,
        actor_id=current_user.id,
        reason=payload.reason,
    )
    await session.commit()
    return RegistrationRead.model_validate(reg)
