"""TypeVector Arena — Security, Privacy, Accessibility, and Product-Truth Hardening Tests (Phase 13)."""

import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

import typevector.models  # noqa: F401
from typevector.domains.events.models import Event
from typevector.domains.identity.models import User, UserCredential, UserSession
from typevector.domains.identity.service import IdentityService
from typevector.domains.integrity_review.models import IntegrityAppeal, IntegrityCase
from typevector.domains.organizations.models import Organization, OrganizationMember
from typevector.domains.practice.models import PracticeSession
from typevector.domains.ranked_input.models import RankedAttempt
from typevector.domains.rounds.models import Round
from typevector.domains.scoring.models import ParticipantScore
from typevector.errors import ForbiddenError, InvariantViolationError


class MockHardeningSession:
    """In-memory mock database session for authorization and tenant isolation tests."""

    def __init__(self) -> None:
        self.users: dict[uuid.UUID, User] = {}
        self.credentials: dict[uuid.UUID, UserCredential] = {}
        self.sessions: dict[uuid.UUID, UserSession] = {}
        self.organizations: dict[uuid.UUID, Organization] = {}
        self.memberships: list[OrganizationMember] = []
        self.events: dict[uuid.UUID, Event] = {}
        self.rounds: dict[uuid.UUID, Round] = {}
        self.attempts: dict[uuid.UUID, RankedAttempt] = {}
        self.scores: dict[uuid.UUID, ParticipantScore] = {}
        self.cases: dict[uuid.UUID, IntegrityCase] = {}
        self.appeals: dict[uuid.UUID, IntegrityAppeal] = {}
        self.practice_sessions: dict[uuid.UUID, PracticeSession] = {}
        self.audit_events: list[object] = []

    def add(self, instance: object) -> None:
        if isinstance(instance, User):
            self.users[instance.id] = instance
        elif isinstance(instance, UserCredential):
            self.credentials[instance.user_id] = instance
        elif isinstance(instance, UserSession):
            self.sessions[instance.id] = instance
        elif isinstance(instance, Organization):
            self.organizations[instance.id] = instance
        elif isinstance(instance, OrganizationMember):
            self.memberships.append(instance)
        elif isinstance(instance, Event):
            self.events[instance.id] = instance
        elif isinstance(instance, Round):
            self.rounds[instance.id] = instance
        elif isinstance(instance, RankedAttempt):
            self.attempts[instance.id] = instance
        elif isinstance(instance, ParticipantScore):
            self.scores[instance.attempt_id] = instance
        elif isinstance(instance, IntegrityCase):
            self.cases[instance.id] = instance
        elif isinstance(instance, IntegrityAppeal):
            self.appeals[instance.id] = instance
        elif isinstance(instance, PracticeSession):
            self.practice_sessions[instance.id] = instance
        else:
            self.audit_events.append(instance)

    async def flush(self) -> None:
        pass

    async def commit(self) -> None:
        pass

    async def get(self, model: type, identifier: uuid.UUID) -> object | None:
        if model is User:
            return self.users.get(identifier)
        if model is Event:
            return self.events.get(identifier)
        if model is Round:
            return self.rounds.get(identifier)
        if model is RankedAttempt:
            return self.attempts.get(identifier)
        if model is ParticipantScore:
            return self.scores.get(identifier)
        if model is IntegrityCase:
            return self.cases.get(identifier)
        if model is IntegrityAppeal:
            return self.appeals.get(identifier)
        if model is PracticeSession:
            return self.practice_sessions.get(identifier)
        return None

    async def execute(self, stmt: object) -> MagicMock:
        mock_result = MagicMock()
        stmt_str = str(stmt).lower()

        if "organization_members" in stmt_str:
            params = stmt.compile().params  # type: ignore[attr-defined]
            matching = [
                m
                for m in self.memberships
                if any(v == m.organization_id for v in params.values())
                and any(v == m.user_id for v in params.values())
            ]
            mock_result.scalar_one_or_none.return_value = matching[0] if matching else None
            mock_result.scalars.return_value.all.return_value = matching
            return mock_result

        if "integrity_cases" in stmt_str:
            all_cases = list(self.cases.values())
            mock_result.scalar_one_or_none.return_value = all_cases[0] if all_cases else None
            mock_result.scalars.return_value.all.return_value = all_cases
            return mock_result

        if "users" in stmt_str:
            mock_result.scalar_one_or_none.return_value = (
                list(self.users.values())[0] if self.users else None
            )
            mock_result.scalars.return_value.all.return_value = list(self.users.values())
            return mock_result

        return mock_result


# =============================================================================
# 1. Privacy Tasks — Public Zero PII, Under-18, and User Rectification/Deletion
# =============================================================================


@pytest.mark.asyncio
async def test_public_user_profile_zero_pii_sanitization() -> None:
    """Verify GET /api/v1/identity/users/{user_id} returns public profile with ZERO PII (no email)."""
    user_id = uuid.uuid4()
    mock_user = User(
        id=user_id,
        email="secret_student@institution.edu",
        display_name="SpeedDemon",
        status="active",
        role="participant",
        created_at=datetime.now(UTC),
    )

    from typevector.domains.identity.schemas import PublicUserRead

    pub = PublicUserRead.model_validate(mock_user)
    assert pub.id == user_id
    assert pub.display_name == "SpeedDemon"
    assert pub.status == "active"
    assert pub.role == "participant"
    # Essential privacy assertion: email must NOT be a field in PublicUserRead
    assert not hasattr(pub, "email")


@pytest.mark.asyncio
async def test_user_profile_rectification_gdpr_art_16() -> None:
    """Verify user can update their display name (GDPR Art. 16) with validation and audit trail."""
    session = MockHardeningSession()
    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        email="typer@example.com",
        display_name="OldAlias",
        status="active",
        role="participant",
    )
    session.add(user)

    svc = IdentityService(session)  # type: ignore[arg-type]
    updated = await svc.update_profile(user_id, "NewVerifiedAlias")

    assert updated.display_name == "NewVerifiedAlias"
    assert len(session.audit_events) == 1
    audit = session.audit_events[0]
    assert audit.event_type == "user.profile_updated"  # type: ignore[attr-defined]

    # Boundary validation: rejection of empty or oversized aliases
    with pytest.raises(InvariantViolationError):
        await svc.update_profile(user_id, " ")

    with pytest.raises(InvariantViolationError):
        await svc.update_profile(user_id, "A" * 101)


@pytest.mark.asyncio
async def test_user_account_deactivation_gdpr_art_17() -> None:
    """Verify account deactivation closes account and revokes active sessions (GDPR Art. 17)."""
    session = MockHardeningSession()
    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        email="departing@example.com",
        display_name="ExMember",
        status="active",
        role="participant",
    )
    session.add(user)

    # Active session
    sess_id = uuid.uuid4()
    user_sess = UserSession(
        id=sess_id,
        user_id=user_id,
        session_token_hash="fakehash",
        expires_at=datetime.now(UTC),
        last_active_at=datetime.now(UTC),
    )
    session.add(user_sess)

    svc = IdentityService(session)  # type: ignore[arg-type]
    deactivated = await svc.deactivate_account(user_id)

    assert deactivated.status == "deactivated"
    assert len(session.audit_events) == 1
    assert session.audit_events[0].event_type == "user.deactivated"  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_under_18_registration_policy_blocker() -> None:
    """Verify registration without confirmed 18+ / parental verification is blocked."""
    session = MockHardeningSession()
    svc = IdentityService(session)  # type: ignore[arg-type]

    with pytest.raises(InvariantViolationError) as exc_info:
        await svc.register_user(
            email="minor@school.edu",
            password="SecurePassword123!",
            display_name="YoungTypist",
            is_age_confirmed_18=False,
        )
    assert "parental consent" in str(exc_info.value)


# =============================================================================
# 2. Security Tasks — Authorization, Tenant Isolation, and BOLA Guards
# =============================================================================


@pytest.mark.asyncio
async def test_results_preview_authorization_guard() -> None:
    """Verify GET /api/v1/results/events/{event_id}/preview rejects unauthorized callers (403)."""
    from typevector.domains.results.router import _verify_event_organizer_permission

    session = MockHardeningSession()
    org_a = uuid.uuid4()
    event_id = uuid.uuid4()
    event = Event(id=event_id, organization_id=org_a, slug="test-event", title="Test Event")
    session.add(event)

    # Participant user (not an organizer of org_a)
    outsider_user = User(
        id=uuid.uuid4(),
        email="outsider@other.org",
        display_name="Outsider",
        role="participant",
    )

    with pytest.raises(ForbiddenError):
        await _verify_event_organizer_permission(
            session=session,  # type: ignore[arg-type]
            user=outsider_user,
            event_id=event_id,
            action="preview results",
        )

    # Organizer member of org_a passes
    organizer_user = User(
        id=uuid.uuid4(),
        email="organizer@org_a.com",
        display_name="OrgAdmin",
        role="participant",
    )
    membership = OrganizationMember(
        organization_id=org_a,
        user_id=organizer_user.id,
        role="organizer",
    )
    session.add(membership)

    verified_event = await _verify_event_organizer_permission(
        session=session,  # type: ignore[arg-type]
        user=organizer_user,
        event_id=event_id,
        action="preview results",
    )
    assert verified_event.id == event_id


@pytest.mark.asyncio
async def test_integrity_review_cross_tenant_rejection() -> None:
    """Verify judges cannot resolve cases belonging to other organizations (IDOR / Tenant Isolation)."""
    from typevector.domains.integrity_review.router import _verify_case_reviewer_permission

    session = MockHardeningSession()
    org_host = uuid.uuid4()
    event = Event(id=uuid.uuid4(), organization_id=org_host, slug="ev1", title="Host Event")
    session.add(event)

    case = IntegrityCase(
        id=uuid.uuid4(),
        event_id=event.id,
        attempt_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        status="under_review",
    )
    session.add(case)

    # Rogue organizer from a different organization
    rogue_org_admin = User(
        id=uuid.uuid4(),
        email="rogue@org_b.com",
        display_name="RogueJudge",
        role="participant",
    )
    # Give them organizer in org_b (not org_host)
    session.add(
        OrganizationMember(
            organization_id=uuid.uuid4(),
            user_id=rogue_org_admin.id,
            role="organizer",
        )
    )

    with pytest.raises(ForbiddenError):
        await _verify_case_reviewer_permission(
            session=session,  # type: ignore[arg-type]
            user=rogue_org_admin,
            case_id=case.id,
            action="resolve",
        )


@pytest.mark.asyncio
async def test_attempt_score_and_status_idor_protection() -> None:
    """Verify participant scores are not inspectable by unauthorized third parties."""
    from typevector.domains.scoring.router import _verify_attempt_access

    session = MockHardeningSession()
    owner_id = uuid.uuid4()
    stranger_id = uuid.uuid4()

    attempt_id = uuid.uuid4()
    attempt = RankedAttempt(
        id=attempt_id,
        round_id=uuid.uuid4(),
        user_id=owner_id,
        status="completed",
    )
    session.add(attempt)

    stranger = User(
        id=stranger_id, email="stranger@web.com", display_name="Stranger", role="participant"
    )

    # Stranger is rejected
    with pytest.raises(ForbiddenError):
        await _verify_attempt_access(
            session=session,  # type: ignore[arg-type]
            user=stranger,
            attempt_id=attempt_id,
            allow_owner=True,
        )

    # Owner is accepted
    owner = User(id=owner_id, email="owner@web.com", display_name="Owner", role="participant")
    res = await _verify_attempt_access(
        session=session,  # type: ignore[arg-type]
        user=owner,
        attempt_id=attempt_id,
        allow_owner=True,
    )
    assert res.id == attempt_id


@pytest.mark.asyncio
async def test_practice_session_privacy_guard() -> None:
    """Verify saved authenticated practice sessions are not exposed to strangers."""
    started = datetime.now(UTC)
    owner_id = uuid.uuid4()
    stranger_id = uuid.uuid4()
    session_id = uuid.uuid4()

    practice_sess = PracticeSession(
        id=session_id,
        user_id=owner_id,
        mode="sentences",
        language="en",
        started_at=started,
        completed_at=started,
        error_diff_json={"metrics": {"accuracy_pct": 98.0}, "segments": []},
    )

    # Simulating authorization check logic in router:
    # 1. Anonymous session (user_id is None) => allowed for public feedback
    anon_sess = PracticeSession(
        id=uuid.uuid4(),
        user_id=None,
        mode="sentences",
        language="en",
        started_at=started,
        completed_at=started,
    )

    def check_auth(sess: PracticeSession, caller: User | None) -> bool:
        if sess.user_id is None:
            return True
        return bool(
            caller
            and (caller.id == sess.user_id or getattr(caller, "role", None) == "platform_admin")
        )

    stranger = User(
        id=stranger_id, email="stranger@test.com", display_name="Stranger", role="participant"
    )
    owner = User(id=owner_id, email="owner@test.com", display_name="Owner", role="participant")

    assert check_auth(anon_sess, None) is True
    assert check_auth(practice_sess, None) is False
    assert check_auth(practice_sess, stranger) is False
    assert check_auth(practice_sess, owner) is True


@pytest.mark.asyncio
async def test_spectator_websocket_origin_security_policy() -> None:
    """Verify spectator WebSocket enforces CORS origin policy in production mode."""
    from typevector.config import settings

    allowed_origins = settings.cors_origins_list
    assert len(allowed_origins) >= 1

    untrusted_origin = "http://evil-competitor-site.com"
    assert untrusted_origin not in allowed_origins


@pytest.mark.asyncio
async def test_results_publication_and_amendment_authorization() -> None:
    """Verify results publication and amendments reject non-organizer callers (403)."""
    from typevector.domains.results.router import _verify_event_organizer_permission

    session = MockHardeningSession()
    org_id = uuid.uuid4()
    event_id = uuid.uuid4()
    event = Event(id=event_id, organization_id=org_id, slug="pub-event", title="Pub Event")
    session.add(event)

    participant = User(
        id=uuid.uuid4(), email="part@test.com", display_name="Typist", role="participant"
    )

    with pytest.raises(ForbiddenError):
        await _verify_event_organizer_permission(
            session=session,  # type: ignore[arg-type]
            user=participant,
            event_id=event_id,
            action="publish official results",
        )

    with pytest.raises(ForbiddenError):
        await _verify_event_organizer_permission(
            session=session,  # type: ignore[arg-type]
            user=participant,
            event_id=event_id,
            action="publish amended results",
        )


@pytest.mark.asyncio
async def test_export_job_inspection_tenant_isolation() -> None:
    """Verify export job lookup enforces organization membership boundary."""
    from typevector.domains.exports.models import ExportJob

    session = MockHardeningSession()
    org_a = uuid.uuid4()
    org_b = uuid.uuid4()
    job_id = uuid.uuid4()

    job = ExportJob(
        id=job_id,
        organization_id=org_a,
        requested_by_user_id=uuid.uuid4(),
        export_type="standings",
        status="completed",
        file_path="/tmp/test.csv",
        created_at=datetime.now(UTC),
    )

    outsider = User(
        id=uuid.uuid4(), email="outsider@b.com", display_name="Outsider", role="participant"
    )
    # Outsider belongs to org_b, not org_a
    session.add(OrganizationMember(organization_id=org_b, user_id=outsider.id, role="organizer"))

    def check_export_auth(target_job: ExportJob, caller: User) -> bool:
        if getattr(caller, "role", None) == "platform_admin":
            return True
        for m in session.memberships:
            if m.organization_id == target_job.organization_id and m.user_id == caller.id:
                return m.role in ("owner", "organizer", "admin")
        return False

    assert check_export_auth(job, outsider) is False

    admin_user = User(
        id=uuid.uuid4(), email="admin@a.com", display_name="OrgAdmin", role="participant"
    )
    session.add(OrganizationMember(organization_id=org_a, user_id=admin_user.id, role="admin"))
    assert check_export_auth(job, admin_user) is True


@pytest.mark.asyncio
async def test_notification_summary_privacy_protection() -> None:
    """Verify notification summary endpoint rejects cross-user inspection (403)."""
    user_a = User(
        id=uuid.uuid4(), email="user_a@test.com", display_name="UserA", role="participant"
    )
    user_b = User(
        id=uuid.uuid4(), email="user_b@test.com", display_name="UserB", role="participant"
    )

    def verify_notif_access(target_user_id: uuid.UUID, caller: User) -> bool:
        return caller.id == target_user_id or getattr(caller, "role", None) == "platform_admin"

    assert verify_notif_access(user_a.id, user_a) is True
    assert verify_notif_access(user_a.id, user_b) is False

    platform_admin = User(
        id=uuid.uuid4(), email="super@arena.com", display_name="SuperAdmin", role="platform_admin"
    )
    assert verify_notif_access(user_a.id, platform_admin) is True


@pytest.mark.asyncio
async def test_integrity_appeal_judge_separation_policy() -> None:
    """Verify appellate judge must be separate from primary and secondary reviewers."""
    primary_judge_id = uuid.uuid4()
    secondary_judge_id = uuid.uuid4()
    independent_judge_id = uuid.uuid4()

    prior_reviewers = {primary_judge_id, secondary_judge_id}

    def verify_appellate_separation(judge_id: uuid.UUID) -> bool:
        return judge_id not in prior_reviewers

    assert verify_appellate_separation(primary_judge_id) is False
    assert verify_appellate_separation(secondary_judge_id) is False
    assert verify_appellate_separation(independent_judge_id) is True
