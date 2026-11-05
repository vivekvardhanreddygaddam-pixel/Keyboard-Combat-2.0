"""TypeVector Arena — Integrity Review and Appeals Domain Service."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from typevector.domains.audit.models import AuditEvent
from typevector.domains.events.models import Event
from typevector.domains.integrity_review.models import IntegrityAppeal, IntegrityCase
from typevector.domains.ranked_input.models import RankedAttempt
from typevector.errors import (
    ConflictError,
    EntityNotFoundError,
    ForbiddenError,
    InvariantViolationError,
)


class IntegrityReviewService:
    """Domain service managing human-in-the-loop integrity adjudication and participant appeals."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_case(self, case_id: uuid.UUID) -> IntegrityCase:
        """Fetch integrity case with loaded appeals."""
        stmt = (
            select(IntegrityCase)
            .where(IntegrityCase.id == case_id)
            .options(selectinload(IntegrityCase.appeals))
        )
        res = await self.session.execute(stmt)
        case = res.scalar_one_or_none()
        if not case:
            raise EntityNotFoundError(entity="IntegrityCase", identifier=case_id)
        return case

    async def list_cases_for_event(self, event_id: uuid.UUID) -> list[IntegrityCase]:
        """Fetch all integrity review cases for an event with loaded appeals."""
        stmt = (
            select(IntegrityCase)
            .where(IntegrityCase.event_id == event_id)
            .options(selectinload(IntegrityCase.appeals))
            .order_by(IntegrityCase.created_at.desc())
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def create_flagged_case(
        self,
        event_id: uuid.UUID,
        round_id: uuid.UUID,
        attempt_id: uuid.UUID,
        user_id: uuid.UUID,
        flag_reasons: dict[str, Any],
        evidence_references: dict[str, Any] | None = None,
    ) -> IntegrityCase:
        """Create a new flagged case for human judging triage."""
        case = IntegrityCase(
            id=uuid.uuid4(),
            event_id=event_id,
            round_id=round_id,
            attempt_id=attempt_id,
            user_id=user_id,
            status="flagged",
            flag_reasons_json=flag_reasons,
            evidence_references_json=evidence_references or {},
        )
        self.session.add(case)
        await self.session.flush()
        return case

    async def resolve_case(
        self,
        case_id: uuid.UUID,
        reviewer_id: uuid.UUID,
        decision: str,
        rationale: str,
        evidence_references: dict[str, Any] | None = None,
    ) -> IntegrityCase:
        """Execute primary judge resolution.

        POLICY: High-impact decision 'upheld' (leading to disqualification) requires
        dual-approval and transitions to 'pending_second_approval'.
        """
        case = await self.get_case(case_id)
        if case.status in ("upheld", "dismissed"):
            raise ConflictError(f"Case {case_id} has already been resolved as '{case.status}'.")

        now = datetime.now(UTC)
        case.assigned_reviewer_id = reviewer_id
        case.resolution_notes = rationale
        if evidence_references:
            case.evidence_references_json.update(evidence_references)

        if decision == "dismissed":
            case.status = "dismissed"
            case.resolved_at = now
        elif decision == "upheld":
            # High-impact decision: requires secondary approval
            case.status = "pending_second_approval"
        else:
            raise InvariantViolationError(f"Invalid judging decision '{decision}'.")

        event = await self.session.get(Event, case.event_id)
        audit = AuditEvent(
            id=uuid.uuid4(),
            organization_id=event.organization_id if event else None,
            actor_user_id=reviewer_id,
            event_type="integrity.case_resolved_primary",
            target_type="integrity_case",
            target_id=str(case.id),
            payload_json={
                "decision": decision,
                "status": case.status,
                "rationale": rationale,
            },
        )
        self.session.add(audit)
        await self.session.flush()
        return case

    async def second_approve_case(
        self,
        case_id: uuid.UUID,
        second_reviewer_id: uuid.UUID,
        approval_decision: str,
        second_notes: str,
    ) -> IntegrityCase:
        """Provide secondary confirmation for a high-impact integrity finding.

        POLICY INVARIANT: The second reviewer must be strictly separate from the primary reviewer.
        """
        case = await self.get_case(case_id)
        if case.status != "pending_second_approval":
            raise ConflictError(
                f"Case {case_id} is in status '{case.status}'; expected 'pending_second_approval'."
            )

        # Reviewer separation rule
        if second_reviewer_id == case.assigned_reviewer_id:
            raise ForbiddenError(
                "Dual-approval policy prohibits the primary reviewer from providing second approval."
            )

        now = datetime.now(UTC)
        case.second_reviewer_id = second_reviewer_id
        case.second_approved_at = now
        case.second_approval_notes = second_notes

        if approval_decision == "approved":
            case.status = "upheld"
            case.resolved_at = now

            # Disqualify the attempt
            attempt = await self.session.get(RankedAttempt, case.attempt_id)
            if attempt:
                attempt.status = "disqualified"
        elif approval_decision == "rejected":
            case.status = "under_review"  # Reverts for further judging deliberation
        else:
            raise InvariantViolationError(
                f"Invalid second approval decision '{approval_decision}'."
            )

        event = await self.session.get(Event, case.event_id)
        audit = AuditEvent(
            id=uuid.uuid4(),
            organization_id=event.organization_id if event else None,
            actor_user_id=second_reviewer_id,
            event_type="integrity.case_second_approved",
            target_type="integrity_case",
            target_id=str(case.id),
            payload_json={
                "approval_decision": approval_decision,
                "final_status": case.status,
                "second_notes": second_notes,
            },
        )
        self.session.add(audit)
        await self.session.flush()
        return case

    async def submit_appeal(
        self,
        case_id: uuid.UUID,
        participant_id: uuid.UUID,
        appeal_statement: str,
    ) -> IntegrityAppeal:
        """Submit a formal participant appeal against an adverse integrity finding."""
        case = await self.get_case(case_id)

        # IDOR check: Only the affected participant can submit an appeal
        if case.user_id != participant_id:
            raise ForbiddenError("You may only submit an appeal for your own flagged attempts.")

        # Check existing pending appeals
        for existing in case.appeals:
            if existing.status == "pending":
                raise ConflictError("An active appeal is already pending review for this case.")

        appeal = IntegrityAppeal(
            id=uuid.uuid4(),
            integrity_case_id=case_id,
            user_id=participant_id,
            appeal_statement=appeal_statement,
            status="pending",
        )
        self.session.add(appeal)

        event = await self.session.get(Event, case.event_id)
        audit = AuditEvent(
            id=uuid.uuid4(),
            organization_id=event.organization_id if event else None,
            actor_user_id=participant_id,
            event_type="integrity.appeal_submitted",
            target_type="integrity_appeal",
            target_id=str(appeal.id),
            payload_json={"case_id": str(case_id), "appeal_statement": appeal_statement},
        )
        self.session.add(audit)
        await self.session.flush()
        return appeal

    async def decide_appeal(
        self,
        appeal_id: uuid.UUID,
        reviewer_id: uuid.UUID,
        decision: str,
        review_notes: str,
    ) -> IntegrityAppeal:
        """Adjudicate participant appeal with strict separation from prior case reviewers."""
        stmt = (
            select(IntegrityAppeal)
            .where(IntegrityAppeal.id == appeal_id)
            .options(selectinload(IntegrityAppeal.case))
        )
        res = await self.session.execute(stmt)
        appeal = res.scalar_one_or_none()
        if not appeal:
            raise EntityNotFoundError(entity="IntegrityAppeal", identifier=appeal_id)

        if appeal.status != "pending":
            raise ConflictError(
                f"Appeal {appeal_id} has already been adjudicated as '{appeal.status}'."
            )

        case = appeal.case
        # Reviewer separation: appellate judge cannot be primary or secondary reviewer
        prior_reviewers = {case.assigned_reviewer_id, case.second_reviewer_id}
        if reviewer_id in prior_reviewers:
            raise ForbiddenError(
                "Appellate review requires an independent judge separate from prior case reviewers."
            )

        appeal.reviewed_by_user_id = reviewer_id
        appeal.review_notes = review_notes

        if decision == "accepted":
            appeal.status = "accepted"
            case.status = "dismissed"
            # Restore attempt if it was disqualified
            attempt = await self.session.get(RankedAttempt, case.attempt_id)
            if attempt and attempt.status == "disqualified":
                attempt.status = "completed"
        elif decision == "rejected":
            appeal.status = "rejected"
        else:
            raise InvariantViolationError(f"Invalid appeal decision '{decision}'.")

        event = await self.session.get(Event, case.event_id)
        audit = AuditEvent(
            id=uuid.uuid4(),
            organization_id=event.organization_id if event else None,
            actor_user_id=reviewer_id,
            event_type="integrity.appeal_decided",
            target_type="integrity_appeal",
            target_id=str(appeal.id),
            payload_json={
                "case_id": str(case.id),
                "decision": decision,
                "review_notes": review_notes,
            },
        )
        self.session.add(audit)
        await self.session.flush()
        return appeal
