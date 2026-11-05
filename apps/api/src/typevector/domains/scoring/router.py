"""TypeVector Arena — Scoring API Router."""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select

from typevector.auth import AuthenticatedUser, enforce_csrf
from typevector.dependencies import DbSession
from typevector.domains.events.models import Event
from typevector.domains.organizations.models import OrganizationMember
from typevector.domains.ranked_input.models import RankedAttempt
from typevector.domains.rounds.models import Round
from typevector.domains.scoring.schemas import (
    MetricGlossaryResponse,
    ParticipantScoreRead,
    ReconciliationReport,
)
from typevector.domains.scoring.service import ScoringService
from typevector.errors import EntityNotFoundError, ForbiddenError

router = APIRouter(prefix="/scores", tags=["Scoring"])


async def _verify_attempt_access(
    session: DbSession,
    user: AuthenticatedUser,
    attempt_id: uuid.UUID,
    allow_owner: bool = True,
) -> RankedAttempt:
    """Verify actor is attempt owner, event organizer, or platform admin."""
    attempt = await session.get(RankedAttempt, attempt_id)
    if not attempt:
        raise EntityNotFoundError(entity="RankedAttempt", identifier=attempt_id)

    if allow_owner and attempt.user_id == user.id:
        return attempt

    if getattr(user, "role", None) == "platform_admin":
        return attempt

    round_obj = await session.get(Round, attempt.round_id)
    if round_obj:
        event = await session.get(Event, round_obj.event_id)
        if event:
            stmt = select(OrganizationMember).where(
                OrganizationMember.organization_id == event.organization_id,
                OrganizationMember.user_id == user.id,
            )
            membership = (await session.execute(stmt)).scalar_one_or_none()
            if membership and membership.role in ("owner", "organizer", "admin", "reviewer"):
                return attempt

    raise ForbiddenError("Actor is not authorized to access this attempt score.")


@router.get("/metrics-glossary", response_model=MetricGlossaryResponse)
async def get_metrics_glossary(session: DbSession) -> MetricGlossaryResponse:
    """Return user metric definitions, sources, denominators, rounding, and limitations."""
    service = ScoringService(session)
    return MetricGlossaryResponse(metrics=service.get_metrics_glossary())


@router.get("/attempts/{attempt_id}", response_model=ParticipantScoreRead)
async def get_attempt_score(
    attempt_id: uuid.UUID,
    current_user: AuthenticatedUser,
    session: DbSession,
) -> ParticipantScoreRead:
    """Fetch authoritative score record for a ranked attempt (restricted to owner or organizer)."""
    await _verify_attempt_access(session, current_user, attempt_id, allow_owner=True)
    service = ScoringService(session)
    score = await service.get_by_attempt(attempt_id)
    return ParticipantScoreRead.model_validate(score)


@router.post(
    "/attempts/{attempt_id}/calculate",
    response_model=ParticipantScoreRead,
    dependencies=[Depends(enforce_csrf)],
)
async def calculate_attempt_score(
    attempt_id: uuid.UUID,
    current_user: AuthenticatedUser,
    session: DbSession,
) -> ParticipantScoreRead:
    """Trigger authoritative server calculation and storage of attempt score."""
    await _verify_attempt_access(session, current_user, attempt_id, allow_owner=True)
    service = ScoringService(session)
    score = await service.calculate_and_persist_attempt_score(attempt_id)
    await session.commit()
    return ParticipantScoreRead.model_validate(score)


@router.post(
    "/attempts/{attempt_id}/reconcile",
    response_model=ReconciliationReport,
    dependencies=[Depends(enforce_csrf)],
)
async def reconcile_attempt_score(
    attempt_id: uuid.UUID,
    _current_user: AuthenticatedUser,
    session: DbSession,
) -> ReconciliationReport:
    """Audit stored score against deterministic recomputation without silent mutation (organizer required)."""
    await _verify_attempt_access(session, _current_user, attempt_id, allow_owner=False)
    service = ScoringService(session)
    report = await service.reconcile_attempt_score(attempt_id)
    await session.commit()
    return report
