"""TypeVector Arena — Integrity Review, Dual-Approval, and Appeals Tests."""

import uuid
from unittest.mock import MagicMock

import pytest

import typevector.models  # noqa: F401
from typevector.domains.events.models import Event
from typevector.domains.integrity_review.models import IntegrityAppeal, IntegrityCase
from typevector.domains.integrity_review.service import IntegrityReviewService
from typevector.domains.ranked_input.models import RankedAttempt
from typevector.errors import ForbiddenError


class MockIntegritySession:
    """Mock async session tracking integrity cases, appeals, attempts, and events."""

    def __init__(self) -> None:
        self.cases: dict[uuid.UUID, IntegrityCase] = {}
        self.appeals: dict[uuid.UUID, IntegrityAppeal] = {}
        self.attempts: dict[uuid.UUID, RankedAttempt] = {}
        self.events: dict[uuid.UUID, Event] = {}
        self.added: list[object] = []

    async def get(self, model: type, identifier: uuid.UUID) -> object | None:
        if model is IntegrityCase:
            return self.cases.get(identifier)
        if model is IntegrityAppeal:
            return self.appeals.get(identifier)
        if model is RankedAttempt:
            return self.attempts.get(identifier)
        if model is Event:
            return self.events.get(identifier)
        return None

    async def execute(self, stmt: object) -> MagicMock:
        mock_result = MagicMock()
        stmt_str = str(stmt).lower()

        if "integrity_cases" in stmt_str:

            def scalar_one_or_none() -> object | None:
                if self.cases:
                    return next(iter(self.cases.values()))
                return None

            mock_result.scalar_one_or_none = scalar_one_or_none
            return mock_result

        if "integrity_appeals" in stmt_str:

            def appeal_scalar() -> object | None:
                if self.appeals:
                    return next(iter(self.appeals.values()))
                return None

            mock_result.scalar_one_or_none = appeal_scalar
            return mock_result

        mock_result.scalars.return_value.all.return_value = []
        mock_result.scalar_one_or_none.return_value = None
        return mock_result

    def add(self, instance: object) -> None:
        self.added.append(instance)
        if isinstance(instance, IntegrityCase):
            self.cases[instance.id] = instance
        elif isinstance(instance, IntegrityAppeal):
            self.appeals[instance.id] = instance
            if instance.integrity_case_id in self.cases:
                self.cases[instance.integrity_case_id].appeals.append(instance)
        elif isinstance(instance, RankedAttempt):
            self.attempts[instance.id] = instance
        elif isinstance(instance, Event):
            self.events[instance.id] = instance

    async def flush(self) -> None:
        pass


@pytest.mark.asyncio
async def test_primary_resolution_dismissed() -> None:
    """Verify that a dismissed case resolves immediately without secondary approval."""
    session = MockIntegritySession()
    service = IntegrityReviewService(session)

    case_id = uuid.uuid4()
    reviewer_id = uuid.uuid4()

    case = IntegrityCase(
        id=case_id,
        event_id=uuid.uuid4(),
        round_id=uuid.uuid4(),
        attempt_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        status="flagged",
        flag_reasons_json={"type": "high_burst_speed"},
        evidence_references_json={},
    )
    session.add(case)

    resolved = await service.resolve_case(
        case_id=case_id,
        reviewer_id=reviewer_id,
        decision="dismissed",
        rationale="Burst speed verified consistent with physical keyboard stroke overlap.",
    )

    assert resolved.status == "dismissed"
    assert resolved.resolved_at is not None
    assert resolved.assigned_reviewer_id == reviewer_id


@pytest.mark.asyncio
async def test_high_impact_upheld_decision_requires_dual_approval() -> None:
    """POLICY INVARIANT: High-impact decision 'upheld' requires dual-approval and transitions to pending_second_approval."""
    session = MockIntegritySession()
    service = IntegrityReviewService(session)

    case_id = uuid.uuid4()
    primary_judge_id = uuid.uuid4()
    secondary_judge_id = uuid.uuid4()

    attempt = RankedAttempt(
        id=uuid.uuid4(),
        event_id=uuid.uuid4(),
        round_id=uuid.uuid4(),
        registration_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        status="completed",
    )
    session.add(attempt)

    case = IntegrityCase(
        id=case_id,
        event_id=attempt.event_id,
        round_id=attempt.round_id,
        attempt_id=attempt.id,
        user_id=attempt.user_id,
        status="flagged",
        flag_reasons_json={"type": "robotic_cadence"},
        evidence_references_json={},
    )
    session.add(case)

    # 1. Primary judge upholds
    resolved = await service.resolve_case(
        case_id=case_id,
        reviewer_id=primary_judge_id,
        decision="upheld",
        rationale="Standard deviation of inter-key latency < 1.0ms across 400 keystrokes.",
    )
    assert resolved.status == "pending_second_approval"
    assert resolved.resolved_at is None  # Not yet fully resolved!

    # 2. Primary judge attempting to provide second approval is BLOCKED
    with pytest.raises(ForbiddenError) as exc:
        await service.second_approve_case(
            case_id=case_id,
            second_reviewer_id=primary_judge_id,  # Same reviewer!
            approval_decision="approved",
            second_notes="Self-approving.",
        )
    assert "prohibits the primary reviewer from providing second approval" in str(exc.value)

    # 3. Independent second judge approves
    second_approved = await service.second_approve_case(
        case_id=case_id,
        second_reviewer_id=secondary_judge_id,  # Independent reviewer!
        approval_decision="approved",
        second_notes="Independently analyzed telemetry distributions; bot script confirmed.",
    )
    assert second_approved.status == "upheld"
    assert second_approved.resolved_at is not None
    assert second_approved.second_reviewer_id == secondary_judge_id
    assert attempt.status == "disqualified"


@pytest.mark.asyncio
async def test_participant_appeal_and_independent_appellate_review() -> None:
    """Verify appeal submission and independent appellate adjudication with reviewer separation."""
    session = MockIntegritySession()
    service = IntegrityReviewService(session)

    participant_id = uuid.uuid4()
    imposter_id = uuid.uuid4()
    judge1_id = uuid.uuid4()
    judge2_id = uuid.uuid4()
    appellate_judge_id = uuid.uuid4()

    attempt = RankedAttempt(
        id=uuid.uuid4(),
        event_id=uuid.uuid4(),
        round_id=uuid.uuid4(),
        registration_id=uuid.uuid4(),
        user_id=participant_id,
        status="disqualified",
    )
    session.add(attempt)

    case = IntegrityCase(
        id=uuid.uuid4(),
        event_id=attempt.event_id,
        round_id=attempt.round_id,
        attempt_id=attempt.id,
        user_id=participant_id,
        status="upheld",
        assigned_reviewer_id=judge1_id,
        second_reviewer_id=judge2_id,
        flag_reasons_json={"type": "robotic_cadence"},
        evidence_references_json={},
    )
    session.add(case)

    # 1. Imposter cannot appeal on behalf of participant
    with pytest.raises(ForbiddenError):
        await service.submit_appeal(
            case_id=case.id,
            participant_id=imposter_id,
            appeal_statement="Appealing someone else's case.",
        )

    # 2. Participant submits appeal
    appeal = await service.submit_appeal(
        case_id=case.id,
        participant_id=participant_id,
        appeal_statement="I was using a custom mechanical keyboard with rapid-trigger switches causing low jitter.",
    )
    assert appeal.status == "pending"

    # 3. Previous trial judges cannot decide the appeal
    with pytest.raises(ForbiddenError) as exc1:
        await service.decide_appeal(
            appeal_id=appeal.id,
            reviewer_id=judge1_id,
            decision="rejected",
            review_notes="Rejecting appeal.",
        )
    assert "requires an independent judge separate from prior case reviewers" in str(exc1.value)

    # 4. Independent appellate judge accepts appeal
    decided = await service.decide_appeal(
        appeal_id=appeal.id,
        reviewer_id=appellate_judge_id,
        decision="accepted",
        review_notes="Rapid-trigger mechanical switch firmware telemetry matches observed pattern; disqualification overturned.",
    )
    assert decided.status == "accepted"
    assert case.status == "dismissed"
    assert attempt.status == "completed"  # Restored from disqualified
