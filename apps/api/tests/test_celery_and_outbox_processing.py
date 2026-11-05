"""TypeVector Arena — Celery, Outbox, Notifications, Exports, and Retention Tests.

Comprehensive verification of Phase 12 requirements:
1. Celery configuration & JSON-only serialization (Pickle rejection).
2. Privacy-aware task logging and secret/keystroke redaction.
3. PostgreSQL outbox atomic dispatch to Redis.
4. Outbox transient failure retry and terminal failure bounding (MAX_RETRIES).
5. Stuck outbox event reconciliation (worker crash recovery).
6. Poison payload isolation without worker crash.
7. Redis broker outage tolerance (PostgreSQL authority preserved).
8. Notification provider abstraction (Mock, Log-Only, unconfigured SMTP).
9. Notification delivery pipeline and failure recording.
10. Async export generation with CWE-1236 CSV formula sanitization.
11. Export expiry lifecycle and physical file deletion.
12. Retention engine with dry-run support and protected entity immutability guards.
13. Worker health, queue depths, and outbox lag metrics.
14. Celery Beat single-instance distributed lock safeguard.
"""

import os
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import typevector.models  # noqa: F401
from typevector.celery_app import (
    QUEUE_DEFAULT,
    QUEUE_EXPORTS,
    QUEUE_NOTIFICATIONS,
    QUEUE_OUTBOX,
    QUEUE_RETENTION,
    celery_app,
)
from typevector.domains.audit.models import AuditEvent
from typevector.domains.events.models import Event
from typevector.domains.exports.models import ExportJob
from typevector.domains.exports.service import ExportService
from typevector.domains.identity.models import IdentityClaim, User, UserSession
from typevector.domains.notifications.models import NotificationDelivery, TransactionalOutbox
from typevector.domains.notifications.outbox_dispatcher import MAX_OUTBOX_RETRIES, OutboxDispatcher
from typevector.domains.notifications.providers import (
    LogOnlyNotificationProvider,
    MockNotificationProvider,
    ProviderNotConfiguredError,
    SMTPNotificationProvider,
)
from typevector.domains.notifications.service import NotificationService
from typevector.domains.operations.retention import RetentionEngine
from typevector.domains.operations.worker_health import probe_worker_and_queue_metrics
from typevector.domains.registrations.models import EventRegistration
from typevector.errors import EntityNotFoundError, InvariantViolationError
from typevector.workers.beat_scheduler import LOCK_KEY, SingleInstanceBeatScheduler
from typevector.workers.logging_context import sanitize_payload

# =============================================================================
# Mock Async Session for Isolated Unit Testing
# =============================================================================


class MockAsyncSession:
    """In-memory mock SQLAlchemy async session."""

    def __init__(self) -> None:
        self.outbox_events: dict[uuid.UUID, TransactionalOutbox] = {}
        self.notification_deliveries: dict[uuid.UUID, NotificationDelivery] = {}
        self.export_jobs: dict[uuid.UUID, ExportJob] = {}
        self.users: dict[uuid.UUID, User] = {}
        self.events: dict[uuid.UUID, Event] = {}
        self.registrations: dict[tuple[uuid.UUID, uuid.UUID], EventRegistration] = {}
        self.sessions: dict[uuid.UUID, UserSession] = {}
        self.claims: dict[uuid.UUID, IdentityClaim] = {}
        self.audit_events: list[AuditEvent] = []
        self.retention_records: list[object] = []
        self.deleted: list[object] = []

    def add(self, obj: object) -> None:
        if isinstance(obj, TransactionalOutbox):
            self.outbox_events[obj.id] = obj
        elif isinstance(obj, NotificationDelivery):
            self.notification_deliveries[obj.id] = obj
        elif isinstance(obj, ExportJob):
            self.export_jobs[obj.id] = obj
        elif isinstance(obj, User):
            self.users[obj.id] = obj
        elif isinstance(obj, Event):
            self.events[obj.id] = obj
        elif isinstance(obj, EventRegistration):
            self.registrations[(obj.event_id, obj.user_id)] = obj
        elif isinstance(obj, UserSession):
            self.sessions[obj.id] = obj
        elif isinstance(obj, IdentityClaim):
            self.claims[obj.id] = obj
        elif isinstance(obj, AuditEvent):
            self.audit_events.append(obj)
        else:
            self.retention_records.append(obj)

    async def flush(self) -> None:
        pass

    async def commit(self) -> None:
        pass

    async def get(self, model: type, identifier: uuid.UUID) -> object | None:  # noqa: ANN401
        if model is ExportJob:
            return self.export_jobs.get(identifier)
        if model is Event:
            return self.events.get(identifier)
        if model is NotificationDelivery:
            return self.notification_deliveries.get(identifier)
        if model is User:
            return self.users.get(identifier)
        return None

    async def execute(self, stmt: object) -> MagicMock:  # noqa: C901, ANN401
        mock_result = MagicMock()
        stmt_str = str(stmt).lower()

        # TransactionalOutbox queries
        if "transactional_outbox" in stmt_str:
            all_events = list(self.outbox_events.values())
            compile_fn = getattr(stmt, "compile", None)
            params = compile_fn().params if compile_fn else {}
            params_str = str(params.values()).lower()

            if "count(" in stmt_str:
                if "failed" in stmt_str or "failed" in params_str:
                    mock_result.scalar_one.return_value = sum(
                        1 for e in all_events if e.status == "failed"
                    )
                else:
                    mock_result.scalar_one.return_value = sum(
                        1 for e in all_events if e.status == "pending"
                    )
                return mock_result

            # Age query selects only created_at with limit 1
            if (
                "transactional_outbox.created_at" in stmt_str
                and "transactional_outbox.id" not in stmt_str
            ):
                pending = sorted(
                    [e for e in all_events if e.status == "pending"],
                    key=lambda e: e.created_at,
                )
                mock_result.scalar_one_or_none.return_value = (
                    pending[0].created_at if pending else None
                )
                return mock_result

            if "in_progress" in stmt_str or "in_progress" in params_str:
                mock_result.scalars.return_value.all.return_value = [
                    e for e in all_events if e.status == "in_progress"
                ]
                return mock_result

            # Default pending
            mock_result.scalars.return_value.all.return_value = [
                e for e in all_events if e.status == "pending"
            ]
            return mock_result

        # NotificationDelivery queries
        if "notification_deliveries" in stmt_str:
            all_nd = list(self.notification_deliveries.values())
            target_nd = all_nd[0] if all_nd else None
            try:
                compile_fn = getattr(stmt, "compile", None)
                if compile_fn:
                    params = compile_fn().params
                    for val in params.values():
                        if val in self.notification_deliveries:
                            target_nd = self.notification_deliveries[val]
                            break
            except Exception:
                pass
            mock_result.scalar_one_or_none.return_value = target_nd
            mock_result.scalars.return_value.all.return_value = all_nd
            return mock_result

        # ExportJob queries
        if "export_jobs" in stmt_str:
            all_jobs = list(self.export_jobs.values())
            if "count(" in stmt_str:
                mock_result.scalar_one.return_value = len(all_jobs)
                return mock_result
            mock_result.scalars.return_value.all.return_value = all_jobs
            mock_result.scalar_one_or_none.return_value = all_jobs[0] if all_jobs else None
            return mock_result

        # UserSession queries (retention)
        if "user_sessions" in stmt_str:
            now = datetime.now(UTC)
            expired = [s for s in self.sessions.values() if s.expires_at < now]
            if "count(" in stmt_str:
                mock_result.scalar_one.return_value = len(expired)
                return mock_result
            mock_result.scalars.return_value.all.return_value = expired
            return mock_result

        # IdentityClaim queries (retention)
        if "identity_claims" in stmt_str:
            threshold = datetime.now(UTC) - timedelta(days=90)
            stale = [
                c
                for c in self.claims.values()
                if c.status == "pending" and c.created_at < threshold
            ]
            if "count(" in stmt_str:
                mock_result.scalar_one.return_value = len(stale)
                return mock_result
            mock_result.scalars.return_value.all.return_value = stale
            return mock_result

        # EventRegistration + User join (Export)
        if "event_registrations" in stmt_str and "users" in stmt_str:
            rows = []
            for (_, uid), reg in self.registrations.items():
                user = self.users.get(uid)
                if user:
                    rows.append((reg, user))
            mock_result.all.return_value = rows
            return mock_result

        return mock_result


# =============================================================================
# 1. Celery App Configuration & Serialization Safety
# =============================================================================


def test_celery_configuration_and_json_serialization() -> None:
    """Verify Celery app rejects pickle and enforces JSON-only, acks_late, and queue routing."""
    # Strict serialization enforcement (CWE-502 Defense)
    assert celery_app.conf.task_serializer == "json"
    assert celery_app.conf.result_serializer == "json"
    assert celery_app.conf.accept_content == ["json"]
    assert "pickle" not in celery_app.conf.accept_content

    # Worker crash resilience
    assert celery_app.conf.task_acks_late is True
    assert celery_app.conf.task_reject_on_worker_lost is True
    assert celery_app.conf.worker_prefetch_multiplier == 1

    # Dedicated queues configured
    routes = celery_app.conf.task_routes
    assert routes["typevector.workers.outbox_tasks.*"]["queue"] == QUEUE_OUTBOX
    assert routes["typevector.workers.notification_tasks.*"]["queue"] == QUEUE_NOTIFICATIONS
    assert routes["typevector.workers.export_tasks.*"]["queue"] == QUEUE_EXPORTS
    assert routes["typevector.workers.retention_tasks.*"]["queue"] == QUEUE_RETENTION
    assert routes["*"]["queue"] == QUEUE_DEFAULT

    # Beat schedule registered
    beat = celery_app.conf.beat_schedule
    assert "outbox-dispatcher-sweep" in beat
    assert "reconcile-stuck-outbox" in beat
    assert "retention-daily-sweep" in beat
    assert "purge-expired-exports" in beat


# =============================================================================
# 2. Task Logging Privacy & Secret Redaction
# =============================================================================


def test_task_logging_sanitizes_sensitive_payloads() -> None:
    """Verify passwords, session tokens, keystrokes, and prompts are scrubbed from logs."""
    raw_payload = {
        "user_id": "12345",
        "email": "user@example.com",
        "password": "SuperSecretPassword123!",
        "session_token": "a" * 64,
        "csrf_token": "b" * 64,
        "prompt_content": "The quick brown fox jumps over the lazy dog.",
        "keystrokes": [{"char": "a", "time": 100}, {"char": "b", "time": 200}],
        "nested": {
            "api_key": "sk-live-secret-key",
            "normal_data": "visible_value",
        },
    }

    clean = sanitize_payload(raw_payload)

    assert clean["user_id"] == "12345"
    assert clean["email"] == "user@example.com"
    assert clean["password"] == "[REDACTED]"
    assert clean["session_token"] == "[REDACTED]"
    assert clean["csrf_token"] == "[REDACTED]"
    assert clean["prompt_content"] == "[REDACTED]"
    assert clean["keystrokes"] == "[REDACTED]"
    assert clean["nested"]["api_key"] == "[REDACTED]"
    assert clean["nested"]["normal_data"] == "visible_value"


# =============================================================================
# 3. PostgreSQL Outbox Atomic Claim and Redis Dispatch
# =============================================================================


@pytest.mark.asyncio
async def test_outbox_atomic_claiming_and_dispatch() -> None:
    """Verify outbox dispatcher publishes pending events to Redis and marks dispatched."""
    session = MockAsyncSession()
    event_id = uuid.uuid4()
    outbox_item = TransactionalOutbox(
        id=uuid.uuid4(),
        event_type="arena:events:lifecycle",
        payload_json={"event_id": str(event_id), "status": "live"},
        status="pending",
        retry_count=0,
        created_at=datetime.now(UTC),
    )
    session.add(outbox_item)

    mock_redis = AsyncMock()
    mock_redis.publish.return_value = 1

    dispatcher = OutboxDispatcher(session)  # type: ignore[arg-type]

    with patch(
        "typevector.domains.notifications.outbox_dispatcher.get_redis_client",
        return_value=mock_redis,
    ):
        dispatched = await dispatcher.dispatch_pending(batch_size=10)

    assert dispatched == 1
    assert outbox_item.status == "dispatched"
    assert outbox_item.dispatched_at is not None
    mock_redis.publish.assert_called_once()
    published_channel, published_payload = mock_redis.publish.call_args[0]
    assert str(event_id) in published_channel
    assert "lifecycle" in published_channel
    assert str(outbox_item.id) in published_payload


# =============================================================================
# 4. Outbox Bounded Retries and Terminal Failure
# =============================================================================


@pytest.mark.asyncio
async def test_outbox_retry_and_bounded_failure() -> None:
    """Verify outbox retries on transient Redis errors and marks failed after MAX_RETRIES."""
    session = MockAsyncSession()
    outbox_item = TransactionalOutbox(
        id=uuid.uuid4(),
        event_type="arena:events:scores",
        payload_json={"score_id": "s1"},
        status="pending",
        retry_count=MAX_OUTBOX_RETRIES - 1,  # 4 retries already
        created_at=datetime.now(UTC),
    )
    session.add(outbox_item)

    mock_redis = AsyncMock()
    mock_redis.publish.side_effect = ConnectionError("Redis cluster unreachable")

    dispatcher = OutboxDispatcher(session)  # type: ignore[arg-type]

    with patch(
        "typevector.domains.notifications.outbox_dispatcher.get_redis_client",
        return_value=mock_redis,
    ):
        dispatched = await dispatcher.dispatch_pending(batch_size=10)

    assert dispatched == 0
    assert outbox_item.retry_count == MAX_OUTBOX_RETRIES
    assert outbox_item.status == "failed"
    assert outbox_item.dispatched_at is None


# =============================================================================
# 5. Outbox Stuck Event Reconciliation
# =============================================================================


@pytest.mark.asyncio
async def test_outbox_stuck_event_reconciliation() -> None:
    """Verify outbox events abandoned in in_progress state are safely recovered to pending."""
    session = MockAsyncSession()
    stuck_item = TransactionalOutbox(
        id=uuid.uuid4(),
        event_type="arena:events:rounds",
        payload_json={"round_id": "r1"},
        status="in_progress",
        retry_count=1,
        created_at=datetime.now(UTC) - timedelta(minutes=10),
    )
    session.add(stuck_item)

    dispatcher = OutboxDispatcher(session)  # type: ignore[arg-type]
    reconciled = await dispatcher.reconcile_stuck(timeout_seconds=300)

    assert reconciled == 1
    assert stuck_item.status == "pending"
    assert stuck_item.retry_count == 2


# =============================================================================
# 6. Poison Payload Isolation
# =============================================================================


@pytest.mark.asyncio
async def test_outbox_poison_payload_handling() -> None:
    """Verify poison payloads (unserializable data) fail safely without halting processing."""
    session = MockAsyncSession()

    # Payload with non-serializable object
    poison_item = TransactionalOutbox(
        id=uuid.uuid4(),
        event_type="arena:events:corrupt",
        payload_json={"bad_object": object()},  # Non-JSON serializable
        status="pending",
        retry_count=0,
        created_at=datetime.now(UTC),
    )
    session.add(poison_item)

    dispatcher = OutboxDispatcher(session)  # type: ignore[arg-type]
    mock_redis = AsyncMock()

    with patch(
        "typevector.domains.notifications.outbox_dispatcher.get_redis_client",
        return_value=mock_redis,
    ):
        dispatched = await dispatcher.dispatch_pending(batch_size=10)

    assert dispatched == 0
    assert poison_item.status == "failed"
    assert poison_item.retry_count == MAX_OUTBOX_RETRIES
    # Redis was never called for the poison item
    mock_redis.publish.assert_not_called()


# =============================================================================
# 7. Redis Outage Preserves PostgreSQL Authority
# =============================================================================


@pytest.mark.asyncio
async def test_redis_outage_preserves_postgresql_authority() -> None:
    """Verify that complete Redis loss leaves PostgreSQL outbox records intact."""
    session = MockAsyncSession()
    outbox_item = TransactionalOutbox(
        id=uuid.uuid4(),
        event_type="arena:events:lifecycle",
        payload_json={"action": "pause"},
        status="pending",
        retry_count=0,
        created_at=datetime.now(UTC),
    )
    session.add(outbox_item)

    dispatcher = OutboxDispatcher(session)  # type: ignore[arg-type]

    # Simulate get_redis_client raising exception
    with patch(
        "typevector.domains.notifications.outbox_dispatcher.get_redis_client",
        side_effect=ConnectionError("Cannot connect to Redis"),
    ):
        dispatched = await dispatcher.dispatch_pending()

    assert dispatched == 0
    # State remains cleanly pending in PostgreSQL
    assert outbox_item.status == "pending"
    assert outbox_item.retry_count == 0


# =============================================================================
# 8. Notification Provider Abstraction
# =============================================================================


@pytest.mark.asyncio
async def test_notification_provider_abstraction() -> None:
    """Verify provider abstraction enforces truthful delivery claims."""
    # 1. Mock Provider
    mock_p = MockNotificationProvider()
    assert mock_p.name == "mock"
    assert mock_p.is_configured is True
    res = await mock_p.send_email("alice@test.com", "Test Subject", "Body text")
    assert res.success is True
    assert res.provider_message_id is not None
    assert len(mock_p.sent_messages) == 1

    # 2. Log-Only Provider (Explicitly unconfigured)
    log_p = LogOnlyNotificationProvider()
    assert log_p.name == "log_only"
    assert log_p.is_configured is False
    res_log = await log_p.send_email("bob@test.com", "Notice", "Body text")
    assert res_log.success is True
    assert res_log.provider_message_id == "log-only-suppressed"

    # 3. SMTP Provider without credentials
    smtp_unconf = SMTPNotificationProvider(host=None)
    assert smtp_unconf.is_configured is False
    with pytest.raises(ProviderNotConfiguredError) as exc_smtp:
        await smtp_unconf.send_email("carol@test.com", "Subject", "Body")
    assert "not configured" in str(exc_smtp.value)


# =============================================================================
# 9. Notification Delivery Pipeline & Error Recording
# =============================================================================


@pytest.mark.asyncio
async def test_notification_delivery_service_and_retries() -> None:
    """Verify notification delivery updates delivery status or records error message."""
    session = MockAsyncSession()
    user_id = uuid.uuid4()
    notif_svc = NotificationService(session)  # type: ignore[arg-type]

    # 1. Successful delivery
    delivery = await notif_svc.create_notification_delivery(
        user_id=user_id,
        notification_type="registration_confirmed",
        recipient="alice@test.com",
    )
    assert delivery.status == "queued"

    mock_provider = MockNotificationProvider(simulate_failure=False)
    delivered = await notif_svc.deliver_notification(
        delivery_id=delivery.id,
        subject="Welcome",
        text_body="Welcome to the event!",
        provider=mock_provider,
    )
    assert delivered.status == "sent"
    assert delivered.sent_at is not None
    assert delivered.error_message is None

    # 2. Failed delivery records error
    delivery_fail = await notif_svc.create_notification_delivery(
        user_id=user_id,
        notification_type="round_starting",
        recipient="bob@test.com",
    )
    failing_provider = MockNotificationProvider(simulate_failure=True)
    delivered_fail = await notif_svc.deliver_notification(
        delivery_id=delivery_fail.id,
        subject="Round 1",
        text_body="Starting now",
        provider=failing_provider,
    )
    assert delivered_fail.status == "failed"
    assert delivered_fail.sent_at is None
    assert "simulated network timeout" in str(delivered_fail.error_message)


# =============================================================================
# 10. Async Export Generation & CWE-1236 Formula Sanitization
# =============================================================================


@pytest.mark.asyncio
async def test_async_export_generation_and_cwe1236_defense() -> None:
    """Verify async export generation escapes formula triggers and persists cleanly."""
    session = MockAsyncSession()
    org_id = uuid.uuid4()
    event_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    user_id = uuid.uuid4()

    event = Event(
        id=event_id, organization_id=org_id, slug="exp-ev", title="Export Event", version=1
    )
    session.add(event)

    user = User(
        id=user_id,
        email="=HYPERLINK('http://evil.com')@test.com",
        display_name="+cmd|'/c calc'!A0",
    )
    session.add(user)

    reg = EventRegistration(
        id=uuid.uuid4(),
        event_id=event_id,
        user_id=user_id,
        status="confirmed",
        registered_at=datetime.now(UTC),
    )
    session.add(reg)

    exp_svc = ExportService(session)  # type: ignore[arg-type]
    job_id = uuid.uuid4()

    job = await exp_svc.generate_export_file(
        job_id=job_id,
        organization_id=org_id,
        requested_by_user_id=actor_id,
        export_type="roster",
        event_id=event_id,
    )

    assert job.status == "ready"
    assert job.row_count == 1
    assert job.file_path is not None
    assert os.path.exists(job.file_path)

    with open(job.file_path, encoding="utf-8") as f:
        csv_content = f.read()

    # Formulas must be escaped with single quote
    assert "'+cmd|'/c calc'!A0" in csv_content
    assert "'=HYPERLINK" in csv_content


# =============================================================================
# 11. Export Expiry Lifecycle & Deletion
# =============================================================================


@pytest.mark.asyncio
async def test_export_expiry_and_physical_deletion_lifecycle() -> None:
    """Verify expired export files are deleted from disk and rejected on download."""
    session = MockAsyncSession()
    org_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    job_id = uuid.uuid4()
    test_file = Path("data/exports/test_expiry.csv")
    test_file.parent.mkdir(parents=True, exist_ok=True)
    with open(test_file, "w", encoding="utf-8") as f:
        f.write("id,data\n1,test\n")

    # Completed 8 days ago (> 7-day retention)
    job = ExportJob(
        id=job_id,
        organization_id=org_id,
        requested_by_user_id=actor_id,
        export_type="roster",
        status="ready",
        file_path=str(test_file),
        row_count=1,
        created_at=datetime.now(UTC) - timedelta(days=8),
        completed_at=datetime.now(UTC) - timedelta(days=8),
    )
    session.add(job)

    exp_svc = ExportService(session)  # type: ignore[arg-type]
    purged = await exp_svc.purge_expired_exports(retention_days=7)

    assert purged == 1
    assert job.status == "expired"
    # Physical file deleted from disk
    assert not os.path.exists(test_file)

    # Download must be rejected
    with pytest.raises(EntityNotFoundError) as exc_down:
        await exp_svc.download_export_content(
            job_id=job_id,
            requesting_user_id=actor_id,
            user_role="platform_admin",
        )
    assert "expired" in str(exc_down.value).lower() or "exportfile" in str(exc_down.value).lower()


# =============================================================================
# 12. Retention Engine Dry-Run & Protected Entity Guards
# =============================================================================


@pytest.mark.asyncio
async def test_retention_engine_dry_run_and_protected_entity_guard() -> None:
    """Verify retention engine supports dry-run and protects permanent competition records."""
    session = MockAsyncSession()
    now = datetime.now(UTC)

    # 1 expired session and 1 active session
    expired_sess = UserSession(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        session_token_hash="hash1",
        expires_at=now - timedelta(hours=1),
        created_at=now - timedelta(days=2),
    )
    active_sess = UserSession(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        session_token_hash="hash2",
        expires_at=now + timedelta(hours=5),
        created_at=now,
    )
    session.add(expired_sess)
    session.add(active_sess)

    engine = RetentionEngine(session)  # type: ignore[arg-type]

    # 1. Dry run execution
    dry_job = await engine.execute_retention_sweep("purge_expired_sessions", dry_run=True)
    assert dry_job.status == "dry_run"
    assert dry_job.records_affected == 1

    # 2. Live execution
    live_job = await engine.execute_retention_sweep("purge_expired_sessions", dry_run=False)
    assert live_job.status == "completed"
    assert live_job.records_affected == 1

    # 3. Protected entities CANNOT be purged
    with pytest.raises(InvariantViolationError) as exc_prot:
        await engine.execute_retention_sweep("purge_participant_scores")
    assert "Invalid or unreviewed retention job_type" in str(exc_prot.value)


# =============================================================================
# 13. Worker Health, Queue Depths, and Outbox Lag Telemetry
# =============================================================================


@pytest.mark.asyncio
async def test_worker_health_and_queue_lag_metrics() -> None:
    """Verify genuine metrics across Celery broker, worker process inspect, and outbox lag."""
    session = MockAsyncSession()
    now = datetime.now(UTC)

    # 2 pending outbox rows, oldest is 45 seconds old
    session.add(
        TransactionalOutbox(
            id=uuid.uuid4(),
            event_type="e1",
            payload_json={},
            status="pending",
            retry_count=0,
            created_at=now - timedelta(seconds=45),
        )
    )
    session.add(
        TransactionalOutbox(
            id=uuid.uuid4(),
            event_type="e2",
            payload_json={},
            status="pending",
            retry_count=0,
            created_at=now - timedelta(seconds=10),
        )
    )

    mock_redis = AsyncMock()
    mock_redis.ping.return_value = True
    mock_redis.llen.return_value = 0

    with (
        patch("redis.asyncio.Redis.from_url", return_value=mock_redis),
        patch("typevector.celery_app.celery_app.control.inspect") as mock_inspect,
    ):
        mock_inspect.return_value.ping.return_value = {"celery@worker1": "pong"}
        metrics = await probe_worker_and_queue_metrics(session)  # type: ignore[arg-type]

    assert metrics.broker_healthy is True
    assert metrics.workers_online_count == 1
    assert metrics.outbox_pending_count == 2
    assert metrics.outbox_failed_count == 0
    assert metrics.outbox_oldest_pending_age_seconds is not None
    assert metrics.outbox_oldest_pending_age_seconds >= 40.0
    assert metrics.service_status == "healthy"


# =============================================================================
# 14. Celery Beat Single-Instance Distributed Lock
# =============================================================================


def test_celery_beat_single_instance_distributed_lock() -> None:
    """Verify distributed lock prevents dual-scheduler task double-scheduling."""
    mock_redis = MagicMock()
    mock_redis.set.return_value = True  # Lock acquired

    scheduler = SingleInstanceBeatScheduler(app=celery_app)
    scheduler.redis_client = mock_redis

    # First attempt: acquires lock
    assert scheduler.acquire_lock() is True
    assert scheduler._has_lock is True
    mock_redis.set.assert_called_with(
        LOCK_KEY,
        scheduler.instance_id,
        nx=True,
        ex=30,
    )

    # Second instance attempting to acquire while held by another:
    mock_redis.set.return_value = False
    mock_redis.get.return_value = "other_host:1234:5678"
    other_scheduler = SingleInstanceBeatScheduler(app=celery_app)
    other_scheduler.redis_client = mock_redis

    assert other_scheduler.acquire_lock() is False
    assert other_scheduler._has_lock is False
