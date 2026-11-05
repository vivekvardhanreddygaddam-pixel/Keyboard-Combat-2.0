"""TypeVector Arena — Integrity Review & Appeals API Router."""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select

from typevector.auth import AuthenticatedUser, enforce_csrf
from typevector.dependencies import DbSession
from typevector.domains.events.models import Event
from typevector.domains.integrity_review.models import IntegrityAppeal, IntegrityCase
from typevector.domains.integrity_review.schemas import (
    AppealDecisionRequest,
    AppealSubmissionRequest,
    CaseResolutionRequest,
    IntegrityAppealRead,
    IntegrityCaseRead,
    SecondApprovalRequest,
)
from typevector.domains.integrity_review.service import IntegrityReviewService
from typevector.domains.organizations.models import OrganizationMember
from typevector.errors import EntityNotFoundError, ForbiddenError

router = APIRouter(prefix="/integrity", tags=["Integrity Review"])


async def _verify_case_reviewer_permission(
    session: DbSession,
    user: AuthenticatedUser,
    case_id: uuid.UUID,
    action: str,
) -> tuple[IntegrityCase, Event]:
    """Verify actor is an authorized reviewer/organizer of the case's host organization."""
    service = IntegrityReviewService(session)
    case = await service.get_case(case_id)
    event = await session.get(Event, case.event_id)
    if not event:
        raise EntityNotFoundError(entity="Event", identifier=case.event_id)

    if getattr(user, "role", None) == "platform_admin":
        return case, event

    stmt = select(OrganizationMember).where(
        OrganizationMember.organization_id == event.organization_id,
        OrganizationMember.user_id == user.id,
    )
    membership = (await session.execute(stmt)).scalar_one_or_none()
    if not membership or membership.role not in ("owner", "organizer", "admin", "reviewer"):
        raise ForbiddenError(
            f"Actor is not authorized to {action} for this event's integrity cases."
        )

    return case, event


@router.get("/events/{event_id}/cases", response_model=list[IntegrityCaseRead])
async def list_event_integrity_cases(
    event_id: uuid.UUID,
    current_user: AuthenticatedUser,
    session: DbSession,
) -> list[IntegrityCaseRead]:
    """List all integrity review cases for an event (restricted to organizers/reviewers/admins)."""
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
        raise ForbiddenError("Actor is not authorized to access judging cases.")

    service = IntegrityReviewService(session)
    cases = await service.list_cases_for_event(event_id)
    return [IntegrityCaseRead.model_validate(c) for c in cases]


@router.get("/cases/{case_id}", response_model=IntegrityCaseRead)
async def get_integrity_case(
    case_id: uuid.UUID,
    current_user: AuthenticatedUser,
    session: DbSession,
) -> IntegrityCaseRead:
    """Fetch integrity case with privacy-scoped access control."""
    service = IntegrityReviewService(session)
    case = await service.get_case(case_id)

    # Privacy Scope: Participant may only view their own case.
    # Organizers / platform admins of the host organization may view event cases.
    if case.user_id != current_user.id and getattr(current_user, "role", None) != "platform_admin":
        event = await session.get(Event, case.event_id)
        if not event:
            raise EntityNotFoundError(entity="Event", identifier=case.event_id)
        stmt = select(OrganizationMember).where(
            OrganizationMember.organization_id == event.organization_id,
            OrganizationMember.user_id == current_user.id,
        )
        membership = (await session.execute(stmt)).scalar_one_or_none()
        if not membership or membership.role not in ("owner", "organizer", "admin", "reviewer"):
            raise ForbiddenError("You are not authorized to view this integrity case.")

    return IntegrityCaseRead.model_validate(case)


@router.post(
    "/cases/{case_id}/resolve",
    response_model=IntegrityCaseRead,
    dependencies=[Depends(enforce_csrf)],
)
async def resolve_case_primary(
    case_id: uuid.UUID,
    payload: CaseResolutionRequest,
    current_user: AuthenticatedUser,
    session: DbSession,
) -> IntegrityCaseRead:
    """Primary judge case resolution (upheld requires second approval)."""
    await _verify_case_reviewer_permission(session, current_user, case_id, "resolve")
    service = IntegrityReviewService(session)
    case = await service.resolve_case(
        case_id=case_id,
        reviewer_id=current_user.id,
        decision=payload.decision,
        rationale=payload.rationale,
        evidence_references=payload.evidence_references,
    )
    await session.commit()
    return IntegrityCaseRead.model_validate(case)


@router.post(
    "/cases/{case_id}/second-approve",
    response_model=IntegrityCaseRead,
    dependencies=[Depends(enforce_csrf)],
)
async def second_approve_case(
    case_id: uuid.UUID,
    payload: SecondApprovalRequest,
    current_user: AuthenticatedUser,
    session: DbSession,
) -> IntegrityCaseRead:
    """Secondary judge confirmation for high-impact disqualification findings."""
    await _verify_case_reviewer_permission(session, current_user, case_id, "second-approve")
    service = IntegrityReviewService(session)
    case = await service.second_approve_case(
        case_id=case_id,
        second_reviewer_id=current_user.id,
        approval_decision=payload.approval_decision,
        second_notes=payload.second_notes,
    )
    await session.commit()
    return IntegrityCaseRead.model_validate(case)


@router.post(
    "/cases/{case_id}/appeal",
    response_model=IntegrityAppealRead,
    dependencies=[Depends(enforce_csrf)],
)
async def submit_case_appeal(
    case_id: uuid.UUID,
    payload: AppealSubmissionRequest,
    current_user: AuthenticatedUser,
    session: DbSession,
) -> IntegrityAppealRead:
    """Submit formal participant appeal against an adverse finding."""
    service = IntegrityReviewService(session)
    appeal = await service.submit_appeal(
        case_id=case_id,
        participant_id=current_user.id,
        appeal_statement=payload.appeal_statement,
    )
    await session.commit()
    return IntegrityAppealRead.model_validate(appeal)


@router.post(
    "/appeals/{appeal_id}/decide",
    response_model=IntegrityAppealRead,
    dependencies=[Depends(enforce_csrf)],
)
async def decide_appeal(
    appeal_id: uuid.UUID,
    payload: AppealDecisionRequest,
    current_user: AuthenticatedUser,
    session: DbSession,
) -> IntegrityAppealRead:
    """Adjudicate participant appeal with reviewer separation."""
    appeal_obj = await session.get(IntegrityAppeal, appeal_id)
    if not appeal_obj:
        raise EntityNotFoundError(entity="IntegrityAppeal", identifier=appeal_id)
    await _verify_case_reviewer_permission(
        session, current_user, appeal_obj.integrity_case_id, "decide appeals on"
    )

    service = IntegrityReviewService(session)
    appeal = await service.decide_appeal(
        appeal_id=appeal_id,
        reviewer_id=current_user.id,
        decision=payload.decision,
        review_notes=payload.review_notes,
    )
    await session.commit()
    return IntegrityAppealRead.model_validate(appeal)
