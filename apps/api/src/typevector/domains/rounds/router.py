"""TypeVector Arena — Rounds API Router."""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select

from typevector.auth import AuthenticatedUser, enforce_csrf
from typevector.dependencies import DbSession
from typevector.domains.events.models import Event
from typevector.domains.organizations.models import OrganizationMember
from typevector.domains.rounds.models import Round
from typevector.domains.rounds.schemas import (
    ChallengePromptCreate,
    ChallengePromptDetailRead,
    RoundCloseRequest,
    RoundCreate,
    RoundRead,
    RoundStartRequest,
    RoundUpdate,
    RoundVoidRequest,
)
from typevector.domains.rounds.service import RoundService
from typevector.errors import EntityNotFoundError, ForbiddenError

router = APIRouter(prefix="/rounds", tags=["Rounds"])


async def _resolve_round_actor_roles(
    session: DbSession,
    user: AuthenticatedUser,
    round_id: uuid.UUID,
) -> tuple[Round, list[str]]:
    """Resolve round and verify actor administrative roles."""
    round_obj = await session.get(Round, round_id)
    if not round_obj:
        raise EntityNotFoundError(entity="Round", identifier=round_id)

    event = await session.get(Event, round_obj.event_id)
    if not event:
        raise EntityNotFoundError(entity="Event", identifier=round_obj.event_id)

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

    return round_obj, roles


@router.get("/event/{event_id}", response_model=list[RoundRead])
async def list_rounds_for_event(event_id: uuid.UUID, session: DbSession) -> list[RoundRead]:
    """List all rounds for a given event."""
    service = RoundService(session)
    rounds = await service.list_by_event(event_id)
    return [RoundRead.model_validate(r) for r in rounds]


@router.post(
    "",
    response_model=RoundRead,
    dependencies=[Depends(enforce_csrf)],
)
async def create_round(
    payload: RoundCreate,
    current_user: AuthenticatedUser,
    session: DbSession,
) -> RoundRead:
    """Create a competition round for an event while in DRAFT status."""
    event = await session.get(Event, payload.event_id)
    if not event:
        raise EntityNotFoundError(entity="Event", identifier=payload.event_id)

    # Permission check
    stmt = select(OrganizationMember).where(
        OrganizationMember.organization_id == event.organization_id,
        OrganizationMember.user_id == current_user.id,
    )
    membership = (await session.execute(stmt)).scalar_one_or_none()
    is_admin = getattr(current_user, "role", None) == "platform_admin" or (
        membership is not None and membership.role in ("owner", "organizer", "admin")
    )
    if not is_admin:
        raise ForbiddenError("Actor is not authorized to configure rounds for this event.")

    service = RoundService(session)
    round_obj = await service.create_round(
        event_id=payload.event_id,
        sequence_number=payload.sequence_number,
        prompt_content=payload.prompt_content,
        scheduled_start_at=payload.scheduled_start_at,
        actor_id=current_user.id,
    )
    await session.commit()
    return RoundRead.model_validate(round_obj)


@router.patch(
    "/{round_id}",
    response_model=RoundRead,
    dependencies=[Depends(enforce_csrf)],
)
async def update_round(
    round_id: uuid.UUID,
    payload: RoundUpdate,
    current_user: AuthenticatedUser,
    session: DbSession,
) -> RoundRead:
    """Update round while event is in DRAFT status."""
    _round_obj, roles = await _resolve_round_actor_roles(session, current_user, round_id)
    if not roles:
        raise ForbiddenError("Actor is not authorized to edit this round.")

    service = RoundService(session)
    updated = await service.update_round(
        round_id=round_id,
        sequence_number=payload.sequence_number,
        scheduled_start_at=payload.scheduled_start_at,
        actor_id=current_user.id,
    )
    await session.commit()
    return RoundRead.model_validate(updated)


@router.post(
    "/{round_id}/prompts",
    response_model=ChallengePromptDetailRead,
    dependencies=[Depends(enforce_csrf)],
)
async def pin_prompt(
    round_id: uuid.UUID,
    payload: ChallengePromptCreate,
    current_user: AuthenticatedUser,
    session: DbSession,
) -> ChallengePromptDetailRead:
    """Pin or update a challenge prompt for a round (requires organizer or admin)."""
    _round_obj, roles = await _resolve_round_actor_roles(session, current_user, round_id)
    if not roles:
        raise ForbiddenError("Actor is not authorized to pin prompts to this round.")

    service = RoundService(session)
    token_count = len(payload.content.split())
    prompt = await service.pin_challenge_prompt(
        round_id=round_id,
        content=payload.content,
        token_count=token_count,
    )
    await session.commit()
    return ChallengePromptDetailRead.model_validate(prompt)


@router.get(
    "/{round_id}/prompts",
    response_model=list[ChallengePromptDetailRead],
)
async def list_round_prompts(
    round_id: uuid.UUID,
    current_user: AuthenticatedUser,
    session: DbSession,
) -> list[ChallengePromptDetailRead]:
    """List challenge prompts for a round (restricted to organizers/admins)."""
    _round_obj, roles = await _resolve_round_actor_roles(session, current_user, round_id)
    if not roles:
        raise ForbiddenError("Actor is not authorized to view challenge prompts for this round.")

    service = RoundService(session)
    prompts = await service.list_prompts_for_round(round_id)
    return [ChallengePromptDetailRead.model_validate(p) for p in prompts]


@router.get("/{round_id}", response_model=RoundRead)
async def get_round(round_id: uuid.UUID, session: DbSession) -> RoundRead:
    """Fetch specific round details."""
    service = RoundService(session)
    round_obj = await service.get_round(round_id)
    return RoundRead.model_validate(round_obj)


@router.post(
    "/{round_id}/start",
    response_model=RoundRead,
    dependencies=[Depends(enforce_csrf)],
)
async def start_round(
    round_id: uuid.UUID,
    payload: RoundStartRequest,
    current_user: AuthenticatedUser,
    session: DbSession,
) -> RoundRead:
    """Start scheduled round with server-authoritative deadline."""
    _round_obj, roles = await _resolve_round_actor_roles(session, current_user, round_id)
    if not roles:
        raise ForbiddenError("Actor is not authorized to start this round.")

    service = RoundService(session)
    started = await service.start_round(
        round_id=round_id,
        actor_id=current_user.id,
        actor_roles=roles,
        expected_version=payload.expected_version,
    )
    await session.commit()
    return RoundRead.model_validate(started)


@router.post(
    "/{round_id}/close",
    response_model=RoundRead,
    dependencies=[Depends(enforce_csrf)],
)
async def close_round(
    round_id: uuid.UUID,
    payload: RoundCloseRequest,
    current_user: AuthenticatedUser,
    session: DbSession,
) -> RoundRead:
    """Close active or paused round, cutting off input admissions."""
    _round_obj, roles = await _resolve_round_actor_roles(session, current_user, round_id)
    if not roles:
        raise ForbiddenError("Actor is not authorized to close this round.")

    service = RoundService(session)
    closed = await service.close_round(
        round_id=round_id,
        actor_id=current_user.id,
        actor_roles=roles,
        expected_version=payload.expected_version,
    )
    await session.commit()
    return RoundRead.model_validate(closed)


@router.post(
    "/{round_id}/void",
    response_model=RoundRead,
    dependencies=[Depends(enforce_csrf)],
)
async def void_round(
    round_id: uuid.UUID,
    payload: RoundVoidRequest,
    current_user: AuthenticatedUser,
    session: DbSession,
) -> RoundRead:
    """Void a round under material incident policy (platform admin only)."""
    _round_obj, roles = await _resolve_round_actor_roles(session, current_user, round_id)
    if "platform_admin" not in roles:
        raise ForbiddenError("Platform admin role is required to void a round.")

    service = RoundService(session)
    voided = await service.void_round(
        round_id=round_id,
        actor_id=current_user.id,
        actor_roles=roles,
        expected_version=payload.expected_version,
        reason=payload.reason,
    )
    await session.commit()
    return RoundRead.model_validate(voided)
