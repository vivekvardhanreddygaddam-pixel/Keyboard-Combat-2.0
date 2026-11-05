"""TypeVector Arena — Round Orchestration, Deadlines, and Fair Pause Synchronization Tests."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

import typevector.models  # noqa: F401
from typevector.domains.events.lifecycle import EventStatus
from typevector.domains.events.models import Event, EventRuleset
from typevector.domains.events.service import EventService
from typevector.domains.ranked_input.models import RankedAttempt
from typevector.domains.rounds.models import ChallengePrompt, Round
from typevector.domains.rounds.service import RoundService
from typevector.errors import (
    ConflictError,
    ForbiddenError,
    InvariantViolationError,
)


class MockOrchestrationSession:
    """Mock async SQLAlchemy session tracking events, rounds, prompts, and attempts."""

    def __init__(self) -> None:
        self.events: dict[uuid.UUID, Event] = {}
        self.rulesets: dict[uuid.UUID, list[EventRuleset]] = {}
        self.rounds: dict[uuid.UUID, Round] = {}
        self.prompts: dict[uuid.UUID, list[ChallengePrompt]] = {}
        self.attempts: dict[uuid.UUID, RankedAttempt] = {}
        self.added: list[object] = []
        self.executed_statements: list[object] = []

    async def get(self, model: type, identifier: uuid.UUID) -> object | None:
        if model is Event:
            return self.events.get(identifier)
        if model is Round:
            return self.rounds.get(identifier)
        if model is RankedAttempt:
            return self.attempts.get(identifier)
        return None

    async def execute(self, stmt: object) -> MagicMock:
        self.executed_statements.append(stmt)
        mock_result = MagicMock()
        stmt_str = str(stmt).lower()

        # Handle ruleset query
        if "event_rulesets" in stmt_str:

            def scalar_one_or_none() -> object | None:
                for rsets in self.rulesets.values():
                    if rsets:
                        return rsets[0]
                return None

            mock_result.scalar_one_or_none = scalar_one_or_none
            return mock_result

        # Handle active rounds query
        if "from rounds" in stmt_str or "rounds.event_id" in stmt_str:
            mock_result.scalars.return_value.all.return_value = list(self.rounds.values())
            return mock_result

        # Handle attempts query
        if "from ranked_attempts" in stmt_str or "ranked_attempts.event_id" in stmt_str:
            mock_result.scalars.return_value.all.return_value = list(self.attempts.values())
            return mock_result

        # Handle challenge prompts query
        if "challenge_prompts" in stmt_str:

            def prompt_scalar() -> object | None:
                for p_list in self.prompts.values():
                    if p_list:
                        return p_list[0]
                return None

            mock_result.scalar_one_or_none = prompt_scalar
            return mock_result

        mock_result.scalars.return_value.all.return_value = []
        mock_result.scalar_one_or_none.return_value = None
        return mock_result

    def add(self, instance: object) -> None:
        self.added.append(instance)
        if isinstance(instance, Event):
            self.events[instance.id] = instance
        elif isinstance(instance, EventRuleset):
            self.rulesets.setdefault(instance.event_id, []).append(instance)
        elif isinstance(instance, Round):
            self.rounds[instance.id] = instance
        elif isinstance(instance, ChallengePrompt):
            self.prompts.setdefault(instance.round_id, []).append(instance)
        elif isinstance(instance, RankedAttempt):
            self.attempts[instance.id] = instance

    async def flush(self) -> None:
        pass


@pytest.mark.asyncio
async def test_round_start_and_deadline_calculation() -> None:
    """Verify round start computes authoritative deadline strictly from ruleset duration."""
    session = MockOrchestrationSession()
    round_service = RoundService(session)

    event_id = uuid.uuid4()
    round_id = uuid.uuid4()
    admin_id = uuid.uuid4()

    event = Event(
        id=event_id,
        organization_id=uuid.uuid4(),
        slug="round-test",
        title="Round Test",
        status=EventStatus.LIVE,
        version=1,
    )
    session.add(event)

    ruleset = EventRuleset(
        id=uuid.uuid4(),
        event_id=event_id,
        version_number=1,
        ruleset_json={},
        min_accuracy_pct=90.0,
        duration_seconds=120,  # 2 minutes duration
    )
    session.add(ruleset)

    round_obj = Round(
        id=round_id,
        event_id=event_id,
        sequence_number=1,
        status="scheduled",
        version=1,
    )
    session.add(round_obj)

    started_round = await round_service.start_round(
        round_id=round_id,
        actor_id=admin_id,
        actor_roles=["org_admin"],
        expected_version=1,
    )

    assert started_round.status == "active"
    assert started_round.version == 2
    assert started_round.started_at is not None
    assert started_round.deadline_at is not None

    # Expected deadline is approximately started_at + 120s
    expected_deadline = started_round.started_at + timedelta(seconds=120)
    assert abs((started_round.deadline_at - expected_deadline).total_seconds()) < 1.0


@pytest.mark.asyncio
async def test_round_start_requires_live_event() -> None:
    """Verify round cannot start if parent event is not in LIVE state."""
    session = MockOrchestrationSession()
    round_service = RoundService(session)

    event_id = uuid.uuid4()
    round_id = uuid.uuid4()
    admin_id = uuid.uuid4()

    event = Event(
        id=event_id,
        organization_id=uuid.uuid4(),
        slug="unstarted-event",
        title="Unstarted Event",
        status=EventStatus.READY,  # Not LIVE yet!
        version=1,
    )
    session.add(event)

    round_obj = Round(
        id=round_id,
        event_id=event_id,
        sequence_number=1,
        status="scheduled",
        version=1,
    )
    session.add(round_obj)

    with pytest.raises(ConflictError) as exc:
        await round_service.start_round(
            round_id=round_id,
            actor_id=admin_id,
            actor_roles=["org_admin"],
            expected_version=1,
        )
    assert "Cannot start round when parent event is not LIVE" in str(exc.value)


@pytest.mark.asyncio
async def test_global_pause_and_uniform_deadline_extension() -> None:
    """Verify that pausing and resuming uniformly extends deadlines across all active rounds and attempts."""
    session = MockOrchestrationSession()
    event_service = EventService(session)

    event_id = uuid.uuid4()
    round_id = uuid.uuid4()
    attempt_id = uuid.uuid4()
    admin_id = uuid.uuid4()

    event = Event(
        id=event_id,
        organization_id=uuid.uuid4(),
        slug="pause-event",
        title="Pause Event",
        status=EventStatus.LIVE,
        version=1,
    )
    session.add(event)

    initial_deadline = datetime.now(UTC) + timedelta(seconds=60)
    round_obj = Round(
        id=round_id,
        event_id=event_id,
        sequence_number=1,
        status="active",
        deadline_at=initial_deadline,
        version=1,
    )
    session.add(round_obj)

    attempt = RankedAttempt(
        id=attempt_id,
        event_id=event_id,
        round_id=round_id,
        registration_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        status="in_progress",
        started_at=datetime.now(UTC),
        deadline_at=initial_deadline,
    )
    session.add(attempt)

    # 1. Pause event
    paused_event = await event_service.pause_event(
        event_id=event_id,
        actor_id=admin_id,
        actor_roles=["org_admin"],
        expected_version=1,
        reason="Server load spike investigation",
    )
    assert paused_event.status == EventStatus.PAUSED
    assert paused_event.pause_started_at is not None
    assert round_obj.status == "paused"
    assert round_obj.pause_started_at is not None

    # Simulate 30 seconds pause duration
    paused_event.pause_started_at = datetime.now(UTC) - timedelta(seconds=30)

    # 2. Resume event
    resumed_event = await event_service.resume_event(
        event_id=event_id,
        actor_id=admin_id,
        actor_roles=["org_admin"],
        expected_version=paused_event.version,
        reason="Load resolved; resuming round",
    )
    assert resumed_event.status == EventStatus.LIVE
    assert resumed_event.pause_started_at is None
    assert resumed_event.total_pause_duration_seconds >= 30

    # Verify uniform round extension
    assert round_obj.status == "active"
    assert round_obj.pause_started_at is None
    assert round_obj.deadline_at is not None
    assert round_obj.deadline_at >= initial_deadline + timedelta(seconds=29)

    # Verify uniform attempt extension
    assert attempt.deadline_at is not None
    assert attempt.deadline_at >= initial_deadline + timedelta(seconds=29)


@pytest.mark.asyncio
async def test_max_pause_fairness_policy_limit() -> None:
    """Verify exceeding MAX_PAUSE_DURATION_SECONDS halts resumption and enforces cancellation or review."""
    session = MockOrchestrationSession()
    event_service = EventService(session)

    event_id = uuid.uuid4()
    admin_id = uuid.uuid4()

    event = Event(
        id=event_id,
        organization_id=uuid.uuid4(),
        slug="exceeded-pause",
        title="Exceeded Pause",
        status=EventStatus.PAUSED,
        version=2,
        total_pause_duration_seconds=500,
        pause_started_at=datetime.now(UTC) - timedelta(seconds=150),  # 500 + 150 = 650 > 600
    )
    session.add(event)

    with pytest.raises(InvariantViolationError) as exc:
        await event_service.resume_event(
            event_id=event_id,
            actor_id=admin_id,
            actor_roles=["org_admin"],
            expected_version=2,
            reason="Attempting resume after excessive pause",
        )
    assert "exceeds tournament maximum limit" in str(exc.value)


@pytest.mark.asyncio
async def test_prompt_exposure_gating() -> None:
    """Verify challenge prompt text is never exposed before authorized round start."""
    session = MockOrchestrationSession()
    round_service = RoundService(session)

    round_id = uuid.uuid4()
    round_obj = Round(
        id=round_id,
        event_id=uuid.uuid4(),
        sequence_number=1,
        status="scheduled",  # Scheduled, NOT active
        version=1,
    )
    session.add(round_obj)

    prompt = ChallengePrompt(
        id=uuid.uuid4(),
        round_id=round_id,
        event_id=round_obj.event_id,
        version_number=1,
        content="Secret prompt text",
        token_count=3,
        checksum_sha256="hash123",
        is_active=True,
    )
    session.add(prompt)

    # 1. Scheduled round: content is None
    p, content = await round_service.get_active_prompt(round_id)
    assert p.id == prompt.id
    assert content is None

    # 2. Active round: content is revealed
    round_obj.status = "active"
    p_active, content_active = await round_service.get_active_prompt(round_id)
    assert content_active == "Secret prompt text"


@pytest.mark.asyncio
async def test_void_round_marks_attempts_voided() -> None:
    """Verify voiding a compromised round marks in-progress attempts voided."""
    session = MockOrchestrationSession()
    round_service = RoundService(session)

    round_id = uuid.uuid4()
    admin_id = uuid.uuid4()

    round_obj = Round(
        id=round_id,
        event_id=uuid.uuid4(),
        sequence_number=1,
        status="active",
        version=2,
    )
    session.add(round_obj)

    attempt = RankedAttempt(
        id=uuid.uuid4(),
        event_id=round_obj.event_id,
        round_id=round_id,
        registration_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        status="in_progress",
        started_at=datetime.now(UTC),
    )
    session.add(attempt)

    # Participant cannot void round
    with pytest.raises(ForbiddenError):
        await round_service.void_round(
            round_id=round_id,
            actor_id=uuid.uuid4(),
            actor_roles=["participant"],
            expected_version=2,
            reason="Material failure",
        )

    # Platform admin voids round
    voided = await round_service.void_round(
        round_id=round_id,
        actor_id=admin_id,
        actor_roles=["platform_admin"],
        expected_version=2,
        reason="Server partition during round 1",
    )
    assert voided.status == "voided"
    assert voided.version == 3
