"""TypeVector Arena — Results API Router."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from typevector.auth import AuthenticatedUser, enforce_csrf
from typevector.dependencies import DbSession
from typevector.domains.events.models import Event
from typevector.domains.organizations.models import OrganizationMember
from typevector.domains.results.schemas import (
    PublicPublishedResultRead,
    PublishedResultRead,
    ResultAmendRequest,
    ResultPreviewRead,
    ResultPublishRequest,
)
from typevector.domains.results.service import ResultsService
from typevector.errors import EntityNotFoundError, ForbiddenError

router = APIRouter(prefix="/results", tags=["Results"])


async def _verify_event_organizer_permission(
    session: DbSession,
    user: AuthenticatedUser,
    event_id: uuid.UUID,
    action: str,
) -> Event:
    """Verify actor is an authorized organizer/owner of the event or platform admin."""
    event = await session.get(Event, event_id)
    if not event:
        raise EntityNotFoundError(entity="Event", identifier=event_id)

    if getattr(user, "role", None) == "platform_admin":
        return event

    stmt = select(OrganizationMember).where(
        OrganizationMember.organization_id == event.organization_id,
        OrganizationMember.user_id == user.id,
    )
    membership = (await session.execute(stmt)).scalar_one_or_none()
    if not membership or membership.role not in ("owner", "organizer", "admin"):
        raise ForbiddenError(f"Actor is not authorized to {action} for this event.")

    return event


@router.get("/events/{event_id}", response_model=PublishedResultRead)
async def get_published_results(
    event_id: uuid.UUID,
    session: DbSession,
) -> PublishedResultRead:
    """Fetch current official published results for an event."""
    service = ResultsService(session)
    result = await service.get_by_event(event_id)
    return PublishedResultRead.model_validate(result)


@router.get("/events/{event_id}/preview", response_model=ResultPreviewRead)
async def preview_event_results(
    event_id: uuid.UUID,
    current_user: AuthenticatedUser,
    session: DbSession,
) -> ResultPreviewRead:
    """Preview server-compiled results for an event prior to official publication."""
    await _verify_event_organizer_permission(session, current_user, event_id, "preview results")
    service = ResultsService(session)
    preview = await service.preview_results(event_id)
    return ResultPreviewRead(**preview)


@router.get("/events/{event_id}/history", response_model=list[PublishedResultRead])
async def list_results_history(
    event_id: uuid.UUID,
    session: DbSession,
) -> list[PublishedResultRead]:
    """Fetch complete immutable publication history (v1, v2, etc.) for an event."""
    service = ResultsService(session)
    results = await service.list_event_results(event_id)
    return [PublishedResultRead.model_validate(r) for r in results]


@router.get("/events/{event_id}/public", response_model=PublicPublishedResultRead)
async def get_public_leaderboard(
    event_id: uuid.UUID,
    session: DbSession,
    version: Annotated[int | None, Query(description="Optional specific version number")] = None,
) -> PublicPublishedResultRead:
    """Fetch privacy-sanitized public tournament leaderboard (Zero PII, pseudonymous aliases only)."""
    service = ResultsService(session)
    return await service.get_public_leaderboard(event_id=event_id, version_number=version)


@router.post(
    "/events/{event_id}/publish",
    response_model=PublishedResultRead,
    dependencies=[Depends(enforce_csrf)],
)
async def publish_official_results(
    event_id: uuid.UUID,
    payload: ResultPublishRequest,
    current_user: AuthenticatedUser,
    session: DbSession,
) -> PublishedResultRead:
    """Publish immutable Version 1 official results for an event."""
    await _verify_event_organizer_permission(
        session, current_user, event_id, "publish official results"
    )
    service = ResultsService(session)
    result = await service.publish_official_results(
        event_id=event_id,
        publisher_id=current_user.id,
        note=payload.note,
    )
    await session.commit()
    return PublishedResultRead.model_validate(result)


@router.post(
    "/events/{event_id}/amend",
    response_model=PublishedResultRead,
    dependencies=[Depends(enforce_csrf)],
)
async def publish_amended_results(
    event_id: uuid.UUID,
    payload: ResultAmendRequest,
    current_user: AuthenticatedUser,
    session: DbSession,
) -> PublishedResultRead:
    """Publish amended results creating Version K+1 following formal appeal decisions."""
    await _verify_event_organizer_permission(
        session, current_user, event_id, "publish amended results"
    )
    service = ResultsService(session)
    result = await service.publish_amended_results(
        event_id=event_id,
        approver_id=current_user.id,
        amendment_reason=payload.amendment_reason,
    )
    await session.commit()
    return PublishedResultRead.model_validate(result)
