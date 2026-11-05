"""TypeVector Arena — Ranked Input Service Conformance & Replay Tests."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

import typevector.models  # noqa: F401
from typevector.domains.ranked_input.models import RankedAttempt, RankedInputBatch
from typevector.domains.ranked_input.protocol import (
    InputAckMsg,
    InputBatchMsg,
    InputRejectedMsg,
    InsertOp,
    compute_operations_digest,
)
from typevector.domains.ranked_input.service import RankedInputService


class MockAsyncSession:
    """Mock async SQLAlchemy session tracking attempts, batches, and outbox in memory."""

    def __init__(self) -> None:
        self.attempts: dict[uuid.UUID, RankedAttempt] = {}
        self.batches: dict[tuple[uuid.UUID, int], RankedInputBatch] = {}
        self.added: list[object] = []
        self.committed = False

    async def execute(self, stmt: object) -> MagicMock:
        mock_result = MagicMock()
        # Handle select(RankedAttempt)
        if hasattr(stmt, "whereclause"):
            pass

        # Default mock scalar retrieval
        def scalar_one_or_none() -> object | None:
            # If checking batch
            for (att_id, seq), b in self.batches.items():
                if getattr(stmt, "_batch_lookup", None) == (att_id, seq):
                    return b
            # Default to first attempt if available
            if self.attempts:
                return next(iter(self.attempts.values()))
            return None

        mock_result.scalar_one_or_none = scalar_one_or_none
        return mock_result

    async def get(self, model: type, identifier: uuid.UUID) -> object | None:
        if model is RankedAttempt:
            return self.attempts.get(identifier)
        return None

    def add(self, instance: object) -> None:
        self.added.append(instance)
        if isinstance(instance, RankedInputBatch):
            self.batches[(instance.attempt_id, instance.batch_sequence_number)] = instance

    async def commit(self) -> None:
        self.committed = True

    async def flush(self) -> None:
        pass


@pytest.fixture
def mock_attempt() -> RankedAttempt:
    att_id = uuid.uuid4()
    user_id = uuid.uuid4()
    event_id = uuid.uuid4()
    round_id = uuid.uuid4()
    now = datetime.now(UTC)

    return RankedAttempt(
        id=att_id,
        event_id=event_id,
        round_id=round_id,
        registration_id=uuid.uuid4(),
        user_id=user_id,
        attempt_number=1,
        status="in_progress",
        socket_writer_generation=1,
        started_at=now,
        last_committed_sequence=0,
        current_text_projection="",
        projection_digest_sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        keystroke_count=0,
        backspace_count=0,
        deadline_at=now + timedelta(minutes=5),
        canonical_version="v1_standard",
    )


@pytest.mark.asyncio
async def test_writer_generation_registration_increments(mock_attempt: RankedAttempt) -> None:
    """Task 3: Writer registration increments socket_writer_generation to fence stale tabs."""
    session = MockAsyncSession()
    session.attempts[mock_attempt.id] = mock_attempt

    service = RankedInputService(session=session)  # type: ignore[arg-type]
    attempt = await service.register_writer_connection(
        attempt_id=mock_attempt.id,
        user_id=mock_attempt.user_id,
        client_session_id="tab-1",
    )
    assert attempt.socket_writer_generation == 2
    assert attempt.client_session_id == "tab-1"
    assert session.committed is True


@pytest.mark.asyncio
async def test_writer_generation_stale_fenced(mock_attempt: RankedAttempt) -> None:
    """Task 3: Stale writer generation is rejected immediately."""
    session = MockAsyncSession()
    mock_attempt.socket_writer_generation = 3
    session.attempts[mock_attempt.id] = mock_attempt

    ops = [InsertOp(text="hello")]
    batch = InputBatchMsg(
        attempt_id=mock_attempt.id,
        batch_sequence_number=1,
        writer_generation=2,  # Stale! Current is 3
        operations=ops,
        payload_digest_sha256=compute_operations_digest(ops),
    )

    service = RankedInputService(session=session)  # type: ignore[arg-type]
    outcome = await service.process_input_batch(
        attempt_id=mock_attempt.id,
        user_id=mock_attempt.user_id,
        batch=batch,
    )

    assert isinstance(outcome, InputRejectedMsg)
    assert outcome.rejection_reason == "STALE_GENERATION"
    assert outcome.writer_generation == 3
    assert outcome.recovery_instruction == "UPGRADE_WRITER_GENERATION"


@pytest.mark.asyncio
async def test_monotonic_sequence_admission_and_watermark_update(
    mock_attempt: RankedAttempt,
) -> None:
    """Task 4 & 5: Monotonic sequence 1 is admitted, projection updated, batch saved, and ACK returned."""
    session = MockAsyncSession()
    session.attempts[mock_attempt.id] = mock_attempt

    ops = [InsertOp(text="TypeVector")]
    batch = InputBatchMsg(
        attempt_id=mock_attempt.id,
        batch_sequence_number=1,
        writer_generation=1,
        operations=ops,
        payload_digest_sha256=compute_operations_digest(ops),
    )

    service = RankedInputService(session=session)  # type: ignore[arg-type]
    outcome = await service.process_input_batch(
        attempt_id=mock_attempt.id,
        user_id=mock_attempt.user_id,
        batch=batch,
    )

    assert isinstance(outcome, InputAckMsg)
    assert outcome.batch_sequence_number == 1
    assert outcome.committed_sequence_watermark == 1
    assert outcome.resulting_text_length == 10
    assert mock_attempt.last_committed_sequence == 1
    assert mock_attempt.current_text_projection == "TypeVector"
    assert session.committed is True


@pytest.mark.asyncio
async def test_idempotent_duplicate_replay_same_digest(mock_attempt: RankedAttempt) -> None:
    """Task 4 & 6: Same sequence + same digest returns original committed outcome without re-applying."""
    session = MockAsyncSession()
    mock_attempt.last_committed_sequence = 1
    mock_attempt.current_text_projection = "Alpha"
    session.attempts[mock_attempt.id] = mock_attempt

    ops = [InsertOp(text="Alpha")]
    digest = compute_operations_digest(ops)

    existing_batch = RankedInputBatch(
        id=uuid.uuid4(),
        attempt_id=mock_attempt.id,
        event_id=mock_attempt.event_id,
        batch_sequence_number=1,
        writer_generation=1,
        raw_events_json={},
        payload_digest_sha256=digest,
        resulting_text_length=5,
        resulting_projection_digest="digest_alpha",
        server_admitted_at=datetime.now(UTC),
        acked_at=datetime.now(UTC),
    )
    session.batches[(mock_attempt.id, 1)] = existing_batch

    # Configure session.execute to return existing_batch on batch lookup
    async def mock_execute(stmt: object) -> MagicMock:
        res = MagicMock()
        # If it's the attempt query
        if "ranked_attempts" in str(stmt):
            res.scalar_one_or_none.return_value = mock_attempt
        else:
            res.scalar_one_or_none.return_value = existing_batch
        return res

    session.execute = mock_execute  # type: ignore[method-assign]

    replay_batch = InputBatchMsg(
        attempt_id=mock_attempt.id,
        batch_sequence_number=1,
        writer_generation=1,
        operations=ops,
        payload_digest_sha256=digest,
    )

    service = RankedInputService(session=session)  # type: ignore[arg-type]
    outcome = await service.process_input_batch(
        attempt_id=mock_attempt.id,
        user_id=mock_attempt.user_id,
        batch=replay_batch,
    )

    assert isinstance(outcome, InputAckMsg)
    assert outcome.batch_sequence_number == 1
    assert outcome.resulting_text_length == 5
    # Text must NOT be duplicated to "AlphaAlpha"
    assert mock_attempt.current_text_projection == "Alpha"


@pytest.mark.asyncio
async def test_conflicting_replay_different_digest_rejected(mock_attempt: RankedAttempt) -> None:
    """Task 4: Same sequence + different digest is a conflict and must be rejected."""
    session = MockAsyncSession()
    mock_attempt.last_committed_sequence = 1
    mock_attempt.current_text_projection = "Original"
    session.attempts[mock_attempt.id] = mock_attempt

    existing_batch = RankedInputBatch(
        id=uuid.uuid4(),
        attempt_id=mock_attempt.id,
        event_id=mock_attempt.event_id,
        batch_sequence_number=1,
        writer_generation=1,
        raw_events_json={},
        payload_digest_sha256="original_digest_hash_0000000000000000000000000000000000000000000000",
        resulting_text_length=8,
        resulting_projection_digest="digest_orig",
        server_admitted_at=datetime.now(UTC),
        acked_at=datetime.now(UTC),
    )

    async def mock_execute(stmt: object) -> MagicMock:
        res = MagicMock()
        if "ranked_attempts" in str(stmt):
            res.scalar_one_or_none.return_value = mock_attempt
        else:
            res.scalar_one_or_none.return_value = existing_batch
        return res

    session.execute = mock_execute  # type: ignore[method-assign]

    conflicting_ops = [InsertOp(text="ConflictingText")]
    conflicting_batch = InputBatchMsg(
        attempt_id=mock_attempt.id,
        batch_sequence_number=1,
        writer_generation=1,
        operations=conflicting_ops,
        payload_digest_sha256=compute_operations_digest(conflicting_ops),
    )

    service = RankedInputService(session=session)  # type: ignore[arg-type]
    outcome = await service.process_input_batch(
        attempt_id=mock_attempt.id,
        user_id=mock_attempt.user_id,
        batch=conflicting_batch,
    )

    assert isinstance(outcome, InputRejectedMsg)
    assert outcome.rejection_reason == "CONFLICTING_REPLAY_DIGEST"
    assert outcome.recovery_instruction == "RESYNC_PROJECTION_FROM_SERVER"


@pytest.mark.asyncio
async def test_out_of_order_sequence_gap_rejected(mock_attempt: RankedAttempt) -> None:
    """Task 4: Out-of-order sequence returns expected watermark and recovery instruction."""
    session = MockAsyncSession()
    mock_attempt.last_committed_sequence = 2  # Current watermark is 2
    session.attempts[mock_attempt.id] = mock_attempt

    ops = [InsertOp(text="skip")]
    gap_batch = InputBatchMsg(
        attempt_id=mock_attempt.id,
        batch_sequence_number=5,  # Gap: Expected 3!
        writer_generation=1,
        operations=ops,
        payload_digest_sha256=compute_operations_digest(ops),
    )

    service = RankedInputService(session=session)  # type: ignore[arg-type]
    outcome = await service.process_input_batch(
        attempt_id=mock_attempt.id,
        user_id=mock_attempt.user_id,
        batch=gap_batch,
    )

    assert isinstance(outcome, InputRejectedMsg)
    assert outcome.rejection_reason == "OUT_OF_ORDER_SEQUENCE"
    assert outcome.expected_sequence == 3
    assert outcome.recovery_instruction == "REPLAY_FROM_WATERMARK"


@pytest.mark.asyncio
async def test_deadline_exceeded_rejected(mock_attempt: RankedAttempt) -> None:
    """Task 7: Server-observed deadline cutoff rejects overdue batches."""
    session = MockAsyncSession()
    # Set deadline in the past
    mock_attempt.deadline_at = datetime.now(UTC) - timedelta(seconds=10)
    session.attempts[mock_attempt.id] = mock_attempt

    ops = [InsertOp(text="late input")]
    batch = InputBatchMsg(
        attempt_id=mock_attempt.id,
        batch_sequence_number=1,
        writer_generation=1,
        operations=ops,
        payload_digest_sha256=compute_operations_digest(ops),
    )

    service = RankedInputService(session=session)  # type: ignore[arg-type]
    outcome = await service.process_input_batch(
        attempt_id=mock_attempt.id,
        user_id=mock_attempt.user_id,
        batch=batch,
    )

    assert isinstance(outcome, InputRejectedMsg)
    assert outcome.rejection_reason == "DEADLINE_EXCEEDED"
    assert outcome.recovery_instruction == "SUBMIT_FINAL_ATTEMPT"


@pytest.mark.asyncio
async def test_forged_payload_digest_rejected(mock_attempt: RankedAttempt) -> None:
    """Task 9: Forged/mismatched payload digest is rejected with INVALID_PAYLOAD_DIGEST."""
    session = MockAsyncSession()
    session.attempts[mock_attempt.id] = mock_attempt

    ops = [InsertOp(text="legitimate text")]
    batch = InputBatchMsg(
        attempt_id=mock_attempt.id,
        batch_sequence_number=1,
        writer_generation=1,
        operations=ops,
        payload_digest_sha256="forged" * 10 + "1234",  # 64 chars incorrect digest
    )

    service = RankedInputService(session=session)  # type: ignore[arg-type]
    outcome = await service.process_input_batch(
        attempt_id=mock_attempt.id,
        user_id=mock_attempt.user_id,
        batch=batch,
    )

    assert isinstance(outcome, InputRejectedMsg)
    assert outcome.rejection_reason == "INVALID_PAYLOAD_DIGEST"


@pytest.mark.asyncio
async def test_forbidden_attempt_ownership_rejected(mock_attempt: RankedAttempt) -> None:
    """Task 2: Client cannot submit input for another participant's attempt."""
    session = MockAsyncSession()
    session.attempts[mock_attempt.id] = mock_attempt

    different_user_id = uuid.uuid4()
    ops = [InsertOp(text="attack")]
    batch = InputBatchMsg(
        attempt_id=mock_attempt.id,
        batch_sequence_number=1,
        writer_generation=1,
        operations=ops,
        payload_digest_sha256=compute_operations_digest(ops),
    )

    service = RankedInputService(session=session)  # type: ignore[arg-type]
    outcome = await service.process_input_batch(
        attempt_id=mock_attempt.id,
        user_id=different_user_id,
        batch=batch,
    )

    assert isinstance(outcome, InputRejectedMsg)
    assert outcome.rejection_reason == "FORBIDDEN_ATTEMPT_OWNERSHIP"
