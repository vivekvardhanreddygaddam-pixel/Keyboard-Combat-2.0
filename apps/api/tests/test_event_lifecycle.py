"""TypeVector Arena — Event Lifecycle, Transition Table, and Fairness Policy Tests."""

import uuid
from datetime import datetime
from unittest.mock import MagicMock

import pytest

import typevector.models  # noqa: F401
from typevector.domains.events.clock import get_server_clock_sample
from typevector.domains.events.lifecycle import (
    CLOCK_UNCERTAINTY_MAX_MS,
    FAIRNESS_POLICY_STATUS,
    FROZEN_EVENT_STATES,
    MAX_PAUSE_DURATION_SECONDS,
    TERMINAL_EVENT_STATES,
    EventStatus,
    find_transition_rule,
)
from typevector.domains.events.models import Event, EventRuleset
from typevector.domains.events.service import EventService
from typevector.domains.registrations.models import EventRegistration
from typevector.domains.rounds.models import ChallengePrompt, Round
from typevector.errors import (
    ConflictError,
    ForbiddenError,
    InvariantViolationError,
)


class MockLifecycleSession:
    """Mock async SQLAlchemy session tracking events, rulesets, rounds, and registrations."""

    def __init__(self) -> None:
        self.events: dict[uuid.UUID, Event] = {}
        self.rulesets: dict[uuid.UUID, list[EventRuleset]] = {}
        self.rounds: dict[uuid.UUID, list[Round]] = {}
        self.prompts: dict[uuid.UUID, list[ChallengePrompt]] = {}
        self.registrations: dict[tuple[uuid.UUID, uuid.UUID], EventRegistration] = {}
        self.added: list[object] = []
        self.executed_statements: list[object] = []

    async def get(self, model: type, identifier: uuid.UUID) -> object | None:
        if model is Event:
            return self.events.get(identifier)
        if model is Round:
            for rnd_list in self.rounds.values():
                for r in rnd_list:
                    if r.id == identifier:
                        return r
        return None

    async def execute(self, stmt: object) -> MagicMock:
        self.executed_statements.append(stmt)
        mock_result = MagicMock()

        # Handle rulesets query
        if "event_rulesets" in str(stmt):
            for _eid, rsets in self.rulesets.items():
                mock_result.scalars.return_value.all.return_value = rsets
                return mock_result
            mock_result.scalars.return_value.all.return_value = []
            return mock_result

        # Handle rounds query
        if "rounds" in str(stmt):
            for _eid, rnds in self.rounds.items():
                mock_result.scalars.return_value.all.return_value = rnds
                return mock_result
            mock_result.scalars.return_value.all.return_value = []
            return mock_result

        # Handle challenge prompts query
        if "challenge_prompts" in str(stmt):
            for _eid, prms in self.prompts.items():
                mock_result.scalars.return_value.all.return_value = prms
                return mock_result
            mock_result.scalars.return_value.all.return_value = []
            return mock_result

        # Handle registrations query
        if "event_registrations" in str(stmt):

            def scalar_one_or_none() -> object | None:
                if self.registrations:
                    return next(iter(self.registrations.values()))
                return None

            mock_result.scalar_one_or_none = scalar_one_or_none
            return mock_result

        # Default fallback
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
            self.rounds.setdefault(instance.event_id, []).append(instance)
        elif isinstance(instance, ChallengePrompt):
            self.prompts.setdefault(instance.event_id, []).append(instance)
        elif isinstance(instance, EventRegistration):
            self.registrations[(instance.event_id, instance.user_id)] = instance

    async def flush(self) -> None:
        pass


def test_fairness_policy_and_transition_table_constants() -> None:
    """Verify tournament fairness draft policy constants and state sets."""
    assert FAIRNESS_POLICY_STATUS == "DRAFT_AWAITING_TOURNAMENT_APPROVAL"
    assert MAX_PAUSE_DURATION_SECONDS == 600
    assert CLOCK_UNCERTAINTY_MAX_MS <= 5.0

    assert EventStatus.CANCELLED in TERMINAL_EVENT_STATES
    assert EventStatus.VOIDED in TERMINAL_EVENT_STATES
    assert EventStatus.ARCHIVED in TERMINAL_EVENT_STATES

    assert EventStatus.PUBLISHED in FROZEN_EVENT_STATES
    assert EventStatus.LIVE in FROZEN_EVENT_STATES
    assert EventStatus.DRAFT not in FROZEN_EVENT_STATES


def test_transition_table_rules_lookup() -> None:
    """Verify transition table mappings and disallowed invalid transitions."""
    # Allowed transitions
    assert find_transition_rule(EventStatus.DRAFT, EventStatus.PUBLISHED) is not None
    assert find_transition_rule(EventStatus.PUBLISHED, EventStatus.REGISTRATION_OPEN) is not None
    assert (
        find_transition_rule(EventStatus.REGISTRATION_OPEN, EventStatus.CHECK_IN_OPEN) is not None
    )
    assert find_transition_rule(EventStatus.CHECK_IN_OPEN, EventStatus.READY) is not None
    assert find_transition_rule(EventStatus.READY, EventStatus.LIVE) is not None
    assert find_transition_rule(EventStatus.LIVE, EventStatus.PAUSED) is not None
    assert find_transition_rule(EventStatus.PAUSED, EventStatus.LIVE) is not None
    assert find_transition_rule(EventStatus.LIVE, EventStatus.COMPLETED) is not None
    assert find_transition_rule(EventStatus.COMPLETED, EventStatus.REVIEW) is not None
    assert find_transition_rule(EventStatus.REVIEW, EventStatus.RESULTS_PUBLISHED) is not None

    # Disallowed transitions
    assert find_transition_rule(EventStatus.DRAFT, EventStatus.LIVE) is None
    assert find_transition_rule(EventStatus.PUBLISHED, EventStatus.COMPLETED) is None
    assert find_transition_rule(EventStatus.COMPLETED, EventStatus.DRAFT) is None
    assert find_transition_rule(EventStatus.ARCHIVED, EventStatus.LIVE) is None


@pytest.mark.asyncio
async def test_valid_linear_lifecycle_transitions() -> None:
    """Verify clean linear progression across event lifecycle."""
    session = MockLifecycleSession()
    service = EventService(session)

    org_id = uuid.uuid4()
    event_id = uuid.uuid4()
    admin_id = uuid.uuid4()

    event = Event(
        id=event_id,
        organization_id=org_id,
        slug="fast-sprint",
        title="Fast Sprint",
        status=EventStatus.DRAFT,
        version=1,
    )
    session.add(event)

    # Pre-populate ruleset, round, and prompt so DRAFT -> PUBLISHED succeeds
    ruleset = EventRuleset(
        id=uuid.uuid4(),
        event_id=event_id,
        version_number=1,
        ruleset_json={},
        min_accuracy_pct=90.0,
        duration_seconds=60,
    )
    session.add(ruleset)

    round_obj = Round(
        id=uuid.uuid4(),
        event_id=event_id,
        sequence_number=1,
        status="scheduled",
    )
    session.add(round_obj)

    prompt = ChallengePrompt(
        id=uuid.uuid4(),
        round_id=round_obj.id,
        event_id=event_id,
        version_number=1,
        content="Hello World",
        token_count=2,
        checksum_sha256="abc",
        is_active=True,
    )
    session.add(prompt)

    # 1. DRAFT -> PUBLISHED
    ev = await service.transition_event(
        event_id=event_id,
        target_status=EventStatus.PUBLISHED,
        actor_id=admin_id,
        actor_roles=["org_admin"],
        expected_version=1,
    )
    assert ev.status == EventStatus.PUBLISHED
    assert ev.version == 2
    assert service.is_ruleset_frozen(ev) is True

    # 2. PUBLISHED -> REGISTRATION_OPEN
    ev = await service.transition_event(
        event_id=event_id,
        target_status=EventStatus.REGISTRATION_OPEN,
        actor_id=admin_id,
        actor_roles=["org_admin"],
        expected_version=2,
    )
    assert ev.status == EventStatus.REGISTRATION_OPEN
    assert ev.version == 3

    # 3. REGISTRATION_OPEN -> CHECK_IN_OPEN
    ev = await service.transition_event(
        event_id=event_id,
        target_status=EventStatus.CHECK_IN_OPEN,
        actor_id=admin_id,
        actor_roles=["org_admin"],
        expected_version=3,
    )
    assert ev.status == EventStatus.CHECK_IN_OPEN
    assert ev.version == 4

    # 4. CHECK_IN_OPEN -> READY
    ev = await service.transition_event(
        event_id=event_id,
        target_status=EventStatus.READY,
        actor_id=admin_id,
        actor_roles=["org_admin"],
        expected_version=4,
    )
    assert ev.status == EventStatus.READY
    assert ev.version == 5

    # 5. READY -> LIVE
    ev = await service.transition_event(
        event_id=event_id,
        target_status=EventStatus.LIVE,
        actor_id=admin_id,
        actor_roles=["org_admin"],
        expected_version=5,
    )
    assert ev.status == EventStatus.LIVE
    assert ev.version == 6

    # 6. LIVE -> COMPLETED
    ev = await service.transition_event(
        event_id=event_id,
        target_status=EventStatus.COMPLETED,
        actor_id=admin_id,
        actor_roles=["org_admin"],
        expected_version=6,
    )
    assert ev.status == EventStatus.COMPLETED
    assert ev.version == 7


@pytest.mark.asyncio
async def test_illegal_lifecycle_transitions_rejected() -> None:
    """Verify that jumping states or illegal transitions are blocked."""
    session = MockLifecycleSession()
    service = EventService(session)

    event_id = uuid.uuid4()
    admin_id = uuid.uuid4()

    event = Event(
        id=event_id,
        organization_id=uuid.uuid4(),
        slug="jump-test",
        title="Jump Test",
        status=EventStatus.DRAFT,
        version=1,
    )
    session.add(event)

    # Attempt illegal jump DRAFT -> LIVE
    with pytest.raises(InvariantViolationError) as exc:
        await service.transition_event(
            event_id=event_id,
            target_status=EventStatus.LIVE,
            actor_id=admin_id,
            actor_roles=["org_admin"],
            expected_version=1,
        )
    assert "Illegal lifecycle transition" in str(exc.value)


@pytest.mark.asyncio
async def test_optimistic_locking_conflict() -> None:
    """Verify optimistic version conflict prevents stale or concurrent transitions."""
    session = MockLifecycleSession()
    service = EventService(session)

    event_id = uuid.uuid4()
    admin_id = uuid.uuid4()

    event = Event(
        id=event_id,
        organization_id=uuid.uuid4(),
        slug="conflict-test",
        title="Conflict Test",
        status=EventStatus.DRAFT,
        version=5,
    )
    session.add(event)

    with pytest.raises(ConflictError) as exc:
        await service.transition_event(
            event_id=event_id,
            target_status=EventStatus.PUBLISHED,
            actor_id=admin_id,
            actor_roles=["org_admin"],
            expected_version=4,  # Stale version!
        )
    assert "Concurrent modification detected" in str(exc.value)


@pytest.mark.asyncio
async def test_role_authorization_enforced() -> None:
    """Verify unauthorized actors cannot trigger privileged state transitions."""
    session = MockLifecycleSession()
    service = EventService(session)

    event_id = uuid.uuid4()
    user_id = uuid.uuid4()

    event = Event(
        id=event_id,
        organization_id=uuid.uuid4(),
        slug="auth-test",
        title="Auth Test",
        status=EventStatus.DRAFT,
        version=1,
    )
    session.add(event)

    with pytest.raises(ForbiddenError) as exc:
        await service.transition_event(
            event_id=event_id,
            target_status=EventStatus.PUBLISHED,
            actor_id=user_id,
            actor_roles=["participant"],  # Lacks org_admin
            expected_version=1,
        )
    assert "Actor lacks required role" in str(exc.value)


@pytest.mark.asyncio
async def test_terminal_state_immutability() -> None:
    """Verify that cancelled, voided, or archived events cannot re-enter active status."""
    session = MockLifecycleSession()
    service = EventService(session)

    event_id = uuid.uuid4()
    admin_id = uuid.uuid4()

    # Cancelled event
    cancelled_event = Event(
        id=event_id,
        organization_id=uuid.uuid4(),
        slug="cancelled-event",
        title="Cancelled Event",
        status=EventStatus.CANCELLED,
        version=1,
    )
    session.add(cancelled_event)

    # Attempt to reopen cancelled event to LIVE
    with pytest.raises(ConflictError) as exc:
        await service.transition_event(
            event_id=event_id,
            target_status=EventStatus.LIVE,
            actor_id=admin_id,
            actor_roles=["platform_admin"],
            expected_version=1,
        )
    assert "Cannot transition event in terminal state" in str(exc.value)


@pytest.mark.asyncio
async def test_check_in_and_readiness_workflow() -> None:
    """Verify participant check-in and readiness signals are gated to appropriate windows."""
    session = MockLifecycleSession()
    service = EventService(session)

    event_id = uuid.uuid4()
    user_id = uuid.uuid4()

    event = Event(
        id=event_id,
        organization_id=uuid.uuid4(),
        slug="checkin-test",
        title="Check-In Test",
        status=EventStatus.PUBLISHED,  # Check-in not yet open
        version=1,
    )
    session.add(event)

    reg = EventRegistration(
        id=uuid.uuid4(),
        event_id=event_id,
        user_id=user_id,
        status="confirmed",
    )
    session.add(reg)

    # Check-in fails when status is PUBLISHED
    with pytest.raises(ConflictError) as exc:
        await service.check_in_participant(event_id, user_id)
    assert "Check-in is not permitted" in str(exc.value)

    # Advance to CHECK_IN_OPEN
    event.status = EventStatus.CHECK_IN_OPEN

    # Check-in succeeds
    checked_reg = await service.check_in_participant(event_id, user_id)
    assert checked_reg.status == "checked_in"
    assert checked_reg.checked_in_at is not None

    # Readiness signal succeeds
    ready_reg = await service.mark_participant_ready(event_id, user_id)
    assert ready_reg.is_ready is True
    assert ready_reg.ready_at is not None


def test_server_clock_sampling_uncertainty_bound() -> None:
    """Verify that server clock sampling endpoint adheres to server clock authority."""
    sample = get_server_clock_sample()
    assert sample.uncertainty_ms <= CLOCK_UNCERTAINTY_MAX_MS
    assert sample.uncertainty_ms > 0
    assert sample.clock_status == "synchronized"
    assert sample.server_time_ms > 0
    assert isinstance(sample.server_time_utc, datetime)
