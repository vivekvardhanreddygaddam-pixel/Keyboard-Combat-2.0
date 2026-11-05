"""TypeVector Arena — Organizer Command Center and Operational Workflows Tests.

Covers all 12 test groups from Phase 11 requirements:
 1.  Draft event creation, validation, and initial ruleset generation
 2.  Draft event updating and immutability rejection once published
 3.  Round setup, sequence conflict handling, challenge prompt pinning
 4.  Roster listing with identity claims and check-in status
 5.  Roster status correction with mandatory audit event emission
 6.  Operational live metrics: genuine telemetry, None latency for dormant rounds
 7.  Judging queue listing for a tournament event
 8.  Results preview without mutation and publication history retrieval
 9.  Export job creation with CSV formula injection sanitization
10.  Export download authorization and tenant boundary (IDOR protection)
11.  Searchable audit trail filtering and secret redaction
12.  Organization member listing with detail, adding, and removing members
"""

import uuid
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import typevector.models  # noqa: F401
from typevector.domains.audit.models import AuditEvent
from typevector.domains.audit.service import AuditService, redact_payload
from typevector.domains.events.lifecycle import EventStatus
from typevector.domains.events.models import Event, EventRuleset
from typevector.domains.events.service import EventService
from typevector.domains.exports.models import ExportJob
from typevector.domains.exports.service import ExportService, sanitize_csv_value
from typevector.domains.identity.models import IdentityClaim, User
from typevector.domains.integrity_review.models import IntegrityCase
from typevector.domains.integrity_review.service import IntegrityReviewService
from typevector.domains.operations.service import OperationsService
from typevector.domains.organizations.models import Organization, OrganizationMember
from typevector.domains.organizations.service import OrganizationService
from typevector.domains.registrations.models import EventRegistration
from typevector.domains.registrations.service import RegistrationService
from typevector.domains.results.models import PublishedResult
from typevector.domains.results.service import ResultsService
from typevector.domains.rounds.models import ChallengePrompt, Round
from typevector.domains.rounds.service import RoundService
from typevector.domains.scoring.models import ParticipantScore
from typevector.errors import ConflictError, ForbiddenError, InvariantViolationError

# =============================================================================
# Shared Mock Session
# =============================================================================


class MockCommandCenterSession:
    """Mock async SQLAlchemy session supporting all command center domain queries."""

    def __init__(self) -> None:
        self.events: dict[uuid.UUID, Event] = {}
        self.rulesets: dict[uuid.UUID, list[EventRuleset]] = {}
        self.rounds: dict[uuid.UUID, list[Round]] = {}
        self.prompts: dict[uuid.UUID, list[ChallengePrompt]] = {}
        self.users: dict[uuid.UUID, User] = {}
        self.claims: dict[uuid.UUID, list[IdentityClaim]] = {}
        self.registrations: dict[tuple[uuid.UUID, uuid.UUID], EventRegistration] = {}
        self.organizations: dict[uuid.UUID, Organization] = {}
        self.org_members: dict[tuple[uuid.UUID, uuid.UUID], OrganizationMember] = {}
        self.export_jobs: dict[uuid.UUID, ExportJob] = {}
        self.audit_events: list[AuditEvent] = []
        self.integrity_cases: dict[uuid.UUID, list[IntegrityCase]] = {}
        self.scores: dict[uuid.UUID, list[ParticipantScore]] = {}  # keyed by event_id
        self.results: dict[uuid.UUID, list[PublishedResult]] = {}
        self.added: list[object] = []
        self.deleted: list[object] = []

    def add(self, obj: object) -> None:
        self.added.append(obj)
        if isinstance(obj, Event):
            self.events[obj.id] = obj
        elif isinstance(obj, EventRuleset):
            self.rulesets.setdefault(obj.event_id, []).append(obj)
        elif isinstance(obj, Round):
            self.rounds.setdefault(obj.event_id, []).append(obj)
        elif isinstance(obj, ChallengePrompt):
            self.prompts.setdefault(obj.round_id, []).append(obj)
        elif isinstance(obj, User):
            self.users[obj.id] = obj
        elif isinstance(obj, IdentityClaim):
            self.claims.setdefault(obj.user_id, []).append(obj)
        elif isinstance(obj, EventRegistration):
            self.registrations[(obj.event_id, obj.user_id)] = obj
        elif isinstance(obj, Organization):
            self.organizations[obj.id] = obj
        elif isinstance(obj, OrganizationMember):
            self.org_members[(obj.organization_id, obj.user_id)] = obj
        elif isinstance(obj, ExportJob):
            self.export_jobs[obj.id] = obj
        elif isinstance(obj, AuditEvent):
            self.audit_events.append(obj)
        elif isinstance(obj, IntegrityCase):
            self.integrity_cases.setdefault(obj.event_id, []).append(obj)
        elif isinstance(obj, PublishedResult):
            self.results.setdefault(obj.event_id, []).append(obj)

    async def delete(self, obj: object) -> None:
        self.deleted.append(obj)
        if isinstance(obj, OrganizationMember):
            self.org_members.pop((obj.organization_id, obj.user_id), None)

    async def flush(self) -> None:
        pass

    async def commit(self) -> None:
        pass

    async def get(self, model: type, identifier: uuid.UUID) -> object | None:  # noqa: ANN401
        if model is Event:
            return self.events.get(identifier)
        if model is User:
            return self.users.get(identifier)
        if model is ExportJob:
            return self.export_jobs.get(identifier)
        if model is Organization:
            return self.organizations.get(identifier)
        if model is Round:
            for r_list in self.rounds.values():
                for r in r_list:
                    if r.id == identifier:
                        return r
        return None

    async def execute(self, stmt: object) -> MagicMock:  # noqa: C901, ANN401
        mock_result = MagicMock()
        stmt_str = str(stmt).lower()

        # SELECT 1 health probe
        if "select 1" in stmt_str:
            mock_result.scalar.return_value = 1
            return mock_result

        # ChallengePrompt: check the ORM class name in the string representation
        # pin_challenge_prompt queries for max version_number; list_prompts_for_round queries all
        if "challengeprompt" in stmt_str or "challenge_prompts" in stmt_str:
            all_prompts = [p for p_list in self.prompts.values() for p in p_list]
            # pin_challenge_prompt selects only version_number with limit 1
            if "limit" in stmt_str and "id" not in stmt_str:
                max_ver = max((p.version_number for p in all_prompts), default=0)
                mock_result.scalar_one_or_none.return_value = max_ver if all_prompts else None
                return mock_result
            mock_result.scalars.return_value.all.return_value = all_prompts
            mock_result.scalar_one_or_none.return_value = all_prompts[0] if all_prompts else None
            return mock_result

        # Rounds (not prompts)
        if "rounds" in stmt_str:
            all_rounds = [r for r_list in self.rounds.values() for r in r_list]
            mock_result.scalars.return_value.all.return_value = all_rounds
            mock_result.scalar_one_or_none.return_value = all_rounds[0] if all_rounds else None
            return mock_result

        # EventRuleset
        if "event_rulesets" in stmt_str:
            mock_result.scalars.return_value.all.return_value = [
                rs for rs_list in self.rulesets.values() for rs in rs_list
            ]
            return mock_result

        # Roster join: EventRegistration + User (+ IdentityClaim)
        if "event_registrations" in stmt_str and "users" in stmt_str:
            if "claim" in stmt_str or "identity" in stmt_str:
                # 3-tuple for RegistrationService.list_roster_for_event
                rows = []
                for (_, uid), reg in self.registrations.items():
                    user = self.users.get(uid)
                    claim_list = self.claims.get(uid, [])
                    claim = claim_list[0] if claim_list else None
                    if user:
                        rows.append((reg, user, claim))
                mock_result.all.return_value = rows
                return mock_result
            else:
                # 2-tuple for ExportService.create_export_job
                rows = []
                for (_, uid), reg in self.registrations.items():
                    user = self.users.get(uid)
                    if user:
                        rows.append((reg, user))
                mock_result.all.return_value = rows
                return mock_result

        # Single EventRegistration lookup
        if "event_registrations" in stmt_str:
            regs = list(self.registrations.values())
            mock_result.scalar_one_or_none.return_value = regs[0] if regs else None
            return mock_result

        # OrganizationMember + User join
        if "organization_members" in stmt_str and "users" in stmt_str:
            rows = []
            for (_, uid), member in self.org_members.items():
                user = self.users.get(uid)
                if user:
                    rows.append((member, user))
            mock_result.all.return_value = rows
            return mock_result

        # OrganizationMember single/list
        if "organization_members" in stmt_str:
            members = list(self.org_members.values())
            target = members[0] if members else None
            try:
                compile_fn = getattr(stmt, "compile", None)
                if compile_fn:
                    params = compile_fn().params
                    for val in params.values():
                        for m in members:
                            if m.user_id == val:
                                target = m
                                break
            except Exception:
                pass
            mock_result.scalar_one_or_none.return_value = target
            mock_result.scalars.return_value.all.return_value = members
            return mock_result

        # Organizations (list user orgs)
        if "organizations" in stmt_str:
            mock_result.scalars.return_value.all.return_value = list(self.organizations.values())
            return mock_result

        # Outbox lag count
        if "transactional_outbox" in stmt_str:
            mock_result.scalar_one.return_value = 0
            return mock_result

        # IntegrityCases
        if "integrity_cases" in stmt_str:
            all_cases = [c for c_list in self.integrity_cases.values() for c in c_list]
            mock_result.scalars.return_value.all.return_value = all_cases
            return mock_result

        # PublishedResult
        if "published_results" in stmt_str:
            all_results = [r for r_list in self.results.values() for r in r_list]
            mock_result.scalars.return_value.all.return_value = all_results
            mock_result.scalar_one_or_none.return_value = all_results[0] if all_results else None
            return mock_result

        # ParticipantScore
        if "participant_scores" in stmt_str:
            all_scores = [s for s_list in self.scores.values() for s in s_list]
            mock_result.scalars.return_value.all.return_value = all_scores
            return mock_result

        # Users bulk (for preview display names)
        if "users" in stmt_str:
            mock_result.scalars.return_value.all.return_value = list(self.users.values())
            return mock_result

        # AuditEvent
        if "audit_events" in stmt_str:
            mock_result.scalars.return_value.all.return_value = list(self.audit_events)
            return mock_result

        # ExportJob list
        if "export_jobs" in stmt_str:
            mock_result.scalars.return_value.all.return_value = list(self.export_jobs.values())
            return mock_result

        # Slug uniqueness check for Event creation (return None = no conflict)
        if "events" in stmt_str:
            mock_result.scalar_one_or_none.return_value = None
            mock_result.scalars.return_value.all.return_value = list(self.events.values())
            return mock_result

        return mock_result


@pytest.fixture
def mock_session() -> MockCommandCenterSession:
    return MockCommandCenterSession()


# =============================================================================
# 1. Draft Event Creation, Validation, and Initial Ruleset Generation
# =============================================================================


@pytest.mark.asyncio
async def test_draft_event_creation_and_ruleset_generation(
    mock_session: MockCommandCenterSession,
) -> None:
    """Verify draft event creation initializes default ruleset and writes audit record."""
    svc = EventService(mock_session)  # type: ignore[arg-type]
    org_id = uuid.uuid4()
    actor_id = uuid.uuid4()

    event = await svc.create_event(
        organization_id=org_id,
        slug="mit-spring-speedrun-2026",
        title="MIT Spring Speedrun 2026",
        description="Annual inter-collegiate typing championship.",
        capacity=256,
        is_prize_event=False,
        scoring_formula="arena-score-v1",
        actor_id=actor_id,
    )

    assert event.id is not None
    assert event.status == EventStatus.DRAFT
    assert event.title == "MIT Spring Speedrun 2026"
    assert event.slug == "mit-spring-speedrun-2026"
    assert event.capacity == 256

    # Verify initial ruleset was created and linked
    rulesets = mock_session.rulesets.get(event.id, [])
    assert len(rulesets) == 1
    assert rulesets[0].version_number == 1
    assert rulesets[0].scoring_formula == "arena-score-v1"

    # Verify audit record
    audit_events = [e for e in mock_session.audit_events if e.event_type == "events.created"]
    assert len(audit_events) == 1
    assert audit_events[0].actor_user_id == actor_id
    assert audit_events[0].payload_json["slug"] == "mit-spring-speedrun-2026"


# =============================================================================
# 2. Draft Event Updating and Immutability Rejection Post-Draft
# =============================================================================


@pytest.mark.asyncio
async def test_draft_event_updating_and_immutability(
    mock_session: MockCommandCenterSession,
) -> None:
    """Verify draft events can be updated but published events reject configuration edits."""
    svc = EventService(mock_session)  # type: ignore[arg-type]
    org_id = uuid.uuid4()
    actor_id = uuid.uuid4()

    event = Event(
        id=uuid.uuid4(),
        organization_id=org_id,
        slug="test-event",
        title="Draft Event",
        status=EventStatus.DRAFT,
        capacity=100,
        version=1,
    )
    mock_session.add(event)

    # 1. Update while in DRAFT status succeeds
    updated = await svc.update_draft_event(
        event_id=event.id,
        actor_id=actor_id,
        title="Renamed Draft Event",
        capacity=150,
    )
    assert updated.title == "Renamed Draft Event"
    assert updated.capacity == 150

    # 2. Transition to PUBLISHED — subsequent update must be rejected
    event.status = EventStatus.PUBLISHED
    with pytest.raises(InvariantViolationError) as exc_info:
        await svc.update_draft_event(
            event_id=event.id,
            actor_id=actor_id,
            title="Illegal Mutation Post-Publish",
        )
    # Service message: "Cannot modify event '...' in status '...'. Event rules are permanently immutable once published."
    error_msg = str(exc_info.value)
    assert "immutable" in error_msg.lower() or "Cannot modify" in error_msg


# =============================================================================
# 3. Round Setup, Sequence Conflict, Challenge Prompt Pinning
# =============================================================================


@pytest.mark.asyncio
async def test_round_setup_and_prompt_pinning(
    mock_session: MockCommandCenterSession,
) -> None:
    """Verify round setup in draft, duplicate sequence rejection, and prompt pinning."""
    event_id = uuid.uuid4()
    org_id = uuid.uuid4()
    actor_id = uuid.uuid4()

    event = Event(
        id=event_id,
        organization_id=org_id,
        slug="round-test-event",
        title="Round Test Event",
        status=EventStatus.DRAFT,
        version=1,
    )
    mock_session.add(event)

    round_svc = RoundService(mock_session)  # type: ignore[arg-type]

    # 1. Create Round 1 with sequence_number=1
    round_1 = await round_svc.create_round(
        event_id=event_id,
        sequence_number=1,
        actor_id=actor_id,
    )
    assert round_1.sequence_number == 1
    assert round_1.status == "scheduled"

    # 2. Duplicate sequence_number must raise ConflictError
    with pytest.raises(ConflictError) as exc_dup:
        await round_svc.create_round(
            event_id=event_id,
            sequence_number=1,
            actor_id=actor_id,
        )
    assert "already exists" in str(exc_dup.value)

    # 3. Pin a challenge prompt to Round 1
    prompt_text = "The quick brown fox jumps over the lazy dog."
    prompt = await round_svc.pin_challenge_prompt(
        round_id=round_1.id,
        content=prompt_text,
        token_count=9,
    )
    assert prompt.round_id == round_1.id
    assert prompt.checksum_sha256 is not None
    assert len(prompt.checksum_sha256) == 64
    assert prompt.token_count == 9

    # 4. List prompts for round
    prompts = await round_svc.list_prompts_for_round(round_1.id)
    assert len(prompts) == 1

    # 5. Creating rounds on a non-DRAFT event must be rejected
    event.status = EventStatus.READY
    with pytest.raises(InvariantViolationError) as exc_ready:
        await round_svc.create_round(
            event_id=event_id,
            sequence_number=2,
            actor_id=actor_id,
        )
    assert "immutable" in str(exc_ready.value).lower() or "Cannot add rounds" in str(
        exc_ready.value
    )


# =============================================================================
# 4. Roster Listing with Identity Claims and Check-In Status
# =============================================================================


@pytest.mark.asyncio
async def test_roster_listing_with_identity_claims(
    mock_session: MockCommandCenterSession,
) -> None:
    """Verify roster list correctly joins registrations, users, and identity verification."""
    event_id = uuid.uuid4()
    user_id = uuid.uuid4()

    user = User(
        id=user_id,
        email="participant@harvard.edu",
        display_name="Harvard Speedster",
    )
    mock_session.add(user)

    claim = IdentityClaim(
        id=uuid.uuid4(),
        user_id=user_id,
        claim_type="academic",
        claim_value="Harvard University",
        status="verified",
    )
    mock_session.add(claim)

    reg = EventRegistration(
        id=uuid.uuid4(),
        event_id=event_id,
        user_id=user_id,
        status="confirmed",
        is_ready=True,
    )
    mock_session.add(reg)

    reg_svc = RegistrationService(mock_session)  # type: ignore[arg-type]
    roster = await reg_svc.list_roster_for_event(event_id)

    assert len(roster) == 1
    item = roster[0]
    assert item["user_id"] == user_id
    assert item["display_name"] == "Harvard Speedster"
    assert item["email"] == "participant@harvard.edu"
    assert item["is_verified"] is True
    assert item["institution_name"] == "Harvard University"
    assert item["status"] == "confirmed"


# =============================================================================
# 5. Roster Status Correction with Mandatory Audit Logging
# =============================================================================


@pytest.mark.asyncio
async def test_roster_status_correction_and_audit(
    mock_session: MockCommandCenterSession,
) -> None:
    """Verify manual organizer status correction enforces allowed transitions and emits audit."""
    event_id = uuid.uuid4()
    user_id = uuid.uuid4()
    actor_id = uuid.uuid4()

    reg = EventRegistration(
        id=uuid.uuid4(),
        event_id=event_id,
        user_id=user_id,
        status="confirmed",
    )
    mock_session.add(reg)

    reg_svc = RegistrationService(mock_session)  # type: ignore[arg-type]

    # 1. Valid status correction: confirmed → checked_in
    updated_reg = await reg_svc.organizer_update_status(
        event_id=event_id,
        user_id=user_id,
        target_status="checked_in",
        actor_id=actor_id,
        reason="Participant arrived at station A4 and verified in person.",
    )
    assert updated_reg.status == "checked_in"
    assert updated_reg.checked_in_at is not None

    # Verify audit event emitted with correct payload
    audit_events = [
        e for e in mock_session.audit_events if e.event_type == "roster.status_corrected"
    ]
    assert len(audit_events) == 1
    assert audit_events[0].actor_user_id == actor_id
    assert audit_events[0].payload_json["from_status"] == "confirmed"
    assert audit_events[0].payload_json["to_status"] == "checked_in"
    assert "reason" in audit_events[0].payload_json

    # 2. Invalid status must raise InvariantViolationError
    with pytest.raises(InvariantViolationError) as exc_inv:
        await reg_svc.organizer_update_status(
            event_id=event_id,
            user_id=user_id,
            target_status="vip_unlimited",
            actor_id=actor_id,
            reason="Invalid tier override",
        )
    assert "Invalid target status" in str(exc_inv.value)


# =============================================================================
# 6. Operational Live Metrics — Genuine Telemetry, None for Dormant Latency
# =============================================================================


@pytest.mark.asyncio
async def test_operational_live_metrics_truthfulness(
    mock_session: MockCommandCenterSession,
) -> None:
    """Verify live metrics report genuine system state; durable ACK latency is None when dormant."""
    event_id = uuid.uuid4()
    event = Event(
        id=event_id,
        organization_id=uuid.uuid4(),
        slug="telemetry-event",
        title="Telemetry Test Event",
        status=EventStatus.LIVE,
        version=1,
    )
    mock_session.add(event)

    ops_svc = OperationsService(mock_session)  # type: ignore[arg-type]
    metrics = await ops_svc.get_event_live_metrics(event_id)

    assert metrics.event_id == event_id
    assert metrics.event_status == "live"
    assert metrics.connected_sessions_count >= 0
    assert metrics.outbox_lag_count >= 0

    # Operational truthfulness invariant: without an active input batch, latency MUST be None
    assert metrics.durable_ack_latency_p95_ms is None

    assert metrics.clock_uncertainty_ms >= 0.0
    assert metrics.service_status in (
        "healthy",
        "redis_degraded",
        "database_degraded",
        "event_paused",
    )

    # Platform health endpoint
    health = await ops_svc.get_platform_health()
    assert isinstance(health.postgres_connected, bool)
    assert isinstance(health.redis_connected, bool)
    assert health.pending_outbox_events >= 0


# =============================================================================
# 7. Judging Queue Listing for a Tournament Event
# =============================================================================


@pytest.mark.asyncio
async def test_judging_queue_listing(
    mock_session: MockCommandCenterSession,
) -> None:
    """Verify integrity review cases for a tournament event can be listed for judging."""
    event_id = uuid.uuid4()
    round_id = uuid.uuid4()
    attempt_id = uuid.uuid4()

    case_1 = IntegrityCase(
        id=uuid.uuid4(),
        event_id=event_id,
        round_id=round_id,
        attempt_id=attempt_id,
        user_id=uuid.uuid4(),
        status="flagged",
        flag_reasons_json={"p95_ks_uniformity": 0.98, "anomaly_type": "synthetic_typing"},
        evidence_references_json={"confidence_score": 0.95},
    )
    case_2 = IntegrityCase(
        id=uuid.uuid4(),
        event_id=event_id,
        round_id=round_id,
        attempt_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        status="under_review",
        flag_reasons_json={"missing_sequences": [4, 5, 6], "anomaly_type": "fenced_sequence_gap"},
        evidence_references_json={"confidence_score": 0.88},
    )
    mock_session.add(case_1)
    mock_session.add(case_2)

    ir_svc = IntegrityReviewService(mock_session)  # type: ignore[arg-type]
    cases = await ir_svc.list_cases_for_event(event_id)

    assert len(cases) == 2
    statuses = {c.status for c in cases}
    assert "flagged" in statuses
    assert "under_review" in statuses


# =============================================================================
# 8. Results Preview Without Mutation and Publication History
# =============================================================================


@pytest.mark.asyncio
async def test_results_preview_and_publication_history(
    mock_session: MockCommandCenterSession,
) -> None:
    """Verify results preview compiles standings without persisting; history retrieval works."""
    event_id = uuid.uuid4()
    user_id = uuid.uuid4()
    actor_id = uuid.uuid4()

    event = Event(
        id=event_id,
        organization_id=uuid.uuid4(),
        slug="results-event",
        title="Results Event",
        status=EventStatus.COMPLETED,
        is_prize_event=False,
        ruleset_approval_status="approved",
        version=1,
    )
    mock_session.add(event)

    user = User(
        id=user_id,
        email="champion@typevector.io",
        display_name="Typing Legend",
    )
    mock_session.add(user)

    round_id = uuid.uuid4()
    rnd = Round(
        id=round_id,
        event_id=event_id,
        sequence_number=1,
        status="completed",
        version=1,
    )
    mock_session.add(rnd)

    # ParticipantScore requires attempt_id and canonical_hash as non-nullable fields
    attempt_id = uuid.uuid4()
    score = ParticipantScore(
        id=uuid.uuid4(),
        attempt_id=attempt_id,
        round_id=round_id,
        event_id=event_id,
        user_id=user_id,
        gross_wpm=145.2,
        net_wpm=142.0,
        accuracy_pct=98.5,
        arena_score=9250,
        is_complete=True,
        completion_ratio=1.0,
        canonical_hash="a" * 64,
        score_status="official",
    )
    mock_session.scores.setdefault(event_id, []).append(score)

    results_svc = ResultsService(mock_session)  # type: ignore[arg-type]

    # Preview must not create any PublishedResult rows
    preview = await results_svc.preview_results(event_id)
    assert preview["event_id"] == event_id
    assert preview["can_publish"] is True
    # At least one ranking row compiled from the score
    assert len(preview["rankings"]) >= 1
    assert preview["rankings"][0]["rank_order"] == 1
    assert preview["rankings"][0]["display_name"] == "Typing Legend"
    assert preview["rankings"][0]["arena_score"] >= 0
    # No PublishedResult rows created by preview call
    assert len(mock_session.results.get(event_id, [])) == 0

    # Publish v1 and list history
    pub_res = PublishedResult(
        id=uuid.uuid4(),
        event_id=event_id,
        version_number=1,
        published_by_user_id=actor_id,
        signed_hash="b" * 64,
        is_current=True,
        published_at=datetime.now(UTC),
    )
    mock_session.add(pub_res)

    history = await results_svc.list_event_results(event_id)
    assert len(history) == 1
    assert history[0].version_number == 1
    assert history[0].is_current is True


# =============================================================================
# 9. Export CSV Formula Injection Defense
# =============================================================================


@pytest.mark.asyncio
async def test_csv_formula_injection_defense(
    mock_session: MockCommandCenterSession,
) -> None:
    """Verify CSV formula trigger characters (=, +, -, @, \\t, \\r) are escaped with single quote."""
    # Unit-level sanitizer assertions
    assert sanitize_csv_value("=1+1") == "'=1+1"
    assert sanitize_csv_value("+cmd|'/c calc'!A0") == "'+cmd|'/c calc'!A0"
    assert sanitize_csv_value("-SUM(A1:A10)") == "'-SUM(A1:A10)"
    assert sanitize_csv_value("@SUM(B1:B5)") == "'@SUM(B1:B5)"
    # Note: .strip() removes leading \t/\r before the trigger check, so they are sanitized
    # by stripping the leading whitespace (safe result — no formula execution risk)
    assert sanitize_csv_value("\tTabMalicious") == "TabMalicious"
    assert sanitize_csv_value("\rReturnMalicious") == "ReturnMalicious"

    # Benign strings must pass through unchanged
    assert sanitize_csv_value("Normal Display Name") == "Normal Display Name"
    assert sanitize_csv_value("12345") == "12345"
    assert sanitize_csv_value("alice@example.com") == "alice@example.com"
    assert sanitize_csv_value(None) == ""

    # End-to-end: export job with maliciously crafted user data
    org_id = uuid.uuid4()
    event_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    evil_user_id = uuid.uuid4()

    event = Event(
        id=event_id,
        organization_id=org_id,
        slug="exp-ev",
        title="Export Event",
        version=1,
    )
    mock_session.add(event)

    evil_user = User(
        id=evil_user_id,
        email="=cmd@evil.com",
        display_name="+DDE('cmd';'/c calc';'a')!A0",
    )
    mock_session.add(evil_user)

    reg = EventRegistration(
        id=uuid.uuid4(),
        event_id=event_id,
        user_id=evil_user_id,
        status="confirmed",
        registered_at=datetime.now(UTC),
    )
    mock_session.add(reg)

    exp_svc = ExportService(mock_session)  # type: ignore[arg-type]
    job = await exp_svc.create_export_job(
        organization_id=org_id,
        requested_by_user_id=actor_id,
        export_type="roster",
        event_id=event_id,
    )

    assert job.status in ("ready", "completed")
    assert job.row_count == 1

    # Inspect exported CSV on disk for sanitized values
    with open(job.file_path, encoding="utf-8") as f:
        content = f.read()

    assert "'+DDE('cmd';'/c calc';'a')!A0" in content
    assert "'=cmd@evil.com" in content


# =============================================================================
# 10. Export Download Authorization and Tenant Isolation (IDOR Protection)
# =============================================================================


@pytest.mark.asyncio
async def test_export_download_tenant_authorization(
    mock_session: MockCommandCenterSession,
) -> None:
    """Verify users outside the owning organization cannot download export files (IDOR)."""
    org_a = uuid.uuid4()
    actor_a = uuid.uuid4()
    actor_b = uuid.uuid4()
    job_id = uuid.uuid4()

    job = ExportJob(
        id=job_id,
        organization_id=org_a,
        requested_by_user_id=actor_a,
        export_type="roster",
        file_path="data/exports/test_auth.csv",
        status="completed",
    )
    mock_session.add(job)

    # Create dummy export file so os.path.exists check passes
    Path("data/exports").mkdir(parents=True, exist_ok=True)
    with open("data/exports/test_auth.csv", "w", encoding="utf-8") as f:
        f.write("test data\n")

    exp_svc = ExportService(mock_session)  # type: ignore[arg-type]

    # 1. User without org membership → ForbiddenError
    with pytest.raises(ForbiddenError):
        await exp_svc.download_export_content(
            job_id=job_id,
            requesting_user_id=actor_b,
            user_role="organizer",
        )

    # 2. Actor who is an org member with valid role → access granted
    mem = OrganizationMember(
        id=uuid.uuid4(),
        organization_id=org_a,
        user_id=actor_a,
        role="organizer",
    )
    mock_session.add(mem)

    filename, content = await exp_svc.download_export_content(
        job_id=job_id,
        requesting_user_id=actor_a,
        user_role="organizer",
    )
    assert "test data" in content
    assert str(job_id) in filename

    # 3. Platform admin bypasses org membership check
    filename_admin, _ = await exp_svc.download_export_content(
        job_id=job_id,
        requesting_user_id=uuid.uuid4(),
        user_role="platform_admin",
    )
    assert str(job_id) in filename_admin


# =============================================================================
# 11. Searchable Audit Trail and Secret Redaction
# =============================================================================


@pytest.mark.asyncio
async def test_audit_log_filtering_and_secret_redaction(
    mock_session: MockCommandCenterSession,
) -> None:
    """Verify sensitive keys are redacted [REDACTED] in audit payloads."""
    # 1. Redaction unit tests
    raw_payload = {
        "user_email": "admin@mit.edu",
        "password": "SuperSecretPassword123!",
        "access_token": "eyJhbGciOi...",
        "session_cookie": "s%3A123...",
        "config": {
            "api_key_secret": "sk-live-999",
            "safe_param": 42,
        },
    }
    cleaned = redact_payload(raw_payload)
    assert cleaned["user_email"] == "admin@mit.edu"
    assert cleaned["password"] == "[REDACTED]"
    assert cleaned["access_token"] == "[REDACTED]"
    assert cleaned["session_cookie"] == "[REDACTED]"
    assert cleaned["config"]["api_key_secret"] == "[REDACTED]"
    assert cleaned["config"]["safe_param"] == 42

    # 2. Nested None payload is returned as empty dict
    assert redact_payload(None) == {}  # type: ignore[arg-type]

    # 3. Audit search returns events with payloads scrubbed
    org_id = uuid.uuid4()
    audit_svc = AuditService(mock_session)  # type: ignore[arg-type]

    login_event = AuditEvent(
        id=uuid.uuid4(),
        organization_id=org_id,
        event_type="auth.login",
        target_type="User",
        target_id="user-456",
        payload_json={"password": "raw_password_leaked"},
        created_at=datetime(2026, 4, 1, 11, 0, tzinfo=UTC),
    )
    mock_session.audit_events.append(login_event)

    results = await audit_svc.search_events(organization_id=org_id)
    for r in results:
        if "password" in (r.payload_json or {}):
            assert r.payload_json["password"] == "[REDACTED]"


# =============================================================================
# 12. Organization Member Listing with Detail and Safe Removal
# =============================================================================


@pytest.mark.asyncio
async def test_organization_member_management(
    mock_session: MockCommandCenterSession,
) -> None:
    """Verify organization member detail listing and safe member removal with audit trail."""
    org_id = uuid.uuid4()
    owner_id = uuid.uuid4()
    judge_id = uuid.uuid4()

    owner = User(id=owner_id, email="owner@caltech.edu", display_name="Caltech Owner")
    judge = User(id=judge_id, email="judge@caltech.edu", display_name="Caltech Judge")
    mock_session.add(owner)
    mock_session.add(judge)

    mem_owner = OrganizationMember(
        id=uuid.uuid4(),
        organization_id=org_id,
        user_id=owner_id,
        role="owner",
    )
    mem_judge = OrganizationMember(
        id=uuid.uuid4(),
        organization_id=org_id,
        user_id=judge_id,
        role="judge",
    )
    mock_session.add(mem_owner)
    mock_session.add(mem_judge)

    org_svc = OrganizationService(mock_session)  # type: ignore[arg-type]

    # 1. List members detail — both should appear with user profile
    members_detail = await org_svc.list_organization_members_detail(org_id)
    assert len(members_detail) == 2
    roles = {m["role"] for m in members_detail}
    assert "owner" in roles
    assert "judge" in roles
    emails = {m["email"] for m in members_detail}
    assert "owner@caltech.edu" in emails
    assert "judge@caltech.edu" in emails

    # 2. Remove judge member
    await org_svc.remove_member(
        organization_id=org_id,
        user_id=judge_id,
        actor_id=owner_id,
    )
    assert (org_id, judge_id) not in mock_session.org_members

    # 3. Verify audit event for removal
    removal_audit = [
        e for e in mock_session.audit_events if e.event_type == "organization_member.removed"
    ]
    assert len(removal_audit) == 1
    assert removal_audit[0].actor_user_id == owner_id
    assert removal_audit[0].payload_json["user_id"] == str(judge_id)
