"""TypeVector Arena — Ranked Input Protocol (arena-ws-v1) Unit Tests."""

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from typevector.domains.ranked_input.protocol import (
    MAX_BACKSPACE_COUNT,
    MAX_INSERT_CHARS,
    MAX_OPS_PER_BATCH,
    PROTOCOL_VERSION,
    BackspaceOp,
    ClockSampleMsg,
    ConnectAttemptMsg,
    ConnectedMsg,
    ErrorMsg,
    HeartbeatMsg,
    InputAckMsg,
    InputBatchMsg,
    InputRejectedMsg,
    InsertOp,
    ResumeRequestMsg,
    ResumeStateMsg,
    RoundStateMsg,
    compute_operations_digest,
)


def test_protocol_version_constant() -> None:
    """Verify official protocol version string is arena-ws-v1."""
    assert PROTOCOL_VERSION == "arena-ws-v1"


def test_operation_schemas_and_bounds() -> None:
    """Verify InsertOp and BackspaceOp validation and limit bounds."""
    # Valid operations
    ins = InsertOp(text="hello world")
    assert ins.type == "insert"
    assert ins.text == "hello world"

    bs = BackspaceOp(count=5)
    assert bs.type == "backspace"
    assert bs.count == 5

    # Bounds: Empty insert rejected
    with pytest.raises(ValidationError):
        InsertOp(text="")

    # Bounds: Oversized insert (> 256 chars) rejected
    with pytest.raises(ValidationError):
        InsertOp(text="x" * (MAX_INSERT_CHARS + 1))

    # Bounds: Zero or negative backspace rejected
    with pytest.raises(ValidationError):
        BackspaceOp(count=0)

    # Bounds: Oversized backspace (> 100) rejected
    with pytest.raises(ValidationError):
        BackspaceOp(count=MAX_BACKSPACE_COUNT + 1)


def test_operations_digest_deterministic() -> None:
    """Verify compute_operations_digest produces identical SHA-256 for identical operations."""
    ops1 = [InsertOp(text="alpha"), BackspaceOp(count=2), InsertOp(text="beta")]
    ops2 = [InsertOp(text="alpha"), BackspaceOp(count=2), InsertOp(text="beta")]
    ops3 = [InsertOp(text="alpha"), BackspaceOp(count=3), InsertOp(text="beta")]

    d1 = compute_operations_digest(ops1)
    d2 = compute_operations_digest(ops2)
    d3 = compute_operations_digest(ops3)

    assert len(d1) == 64
    assert d1 == d2, "Identical operations must produce identical SHA-256 digests"
    assert d1 != d3, "Different operations must produce distinct digests"


def test_input_batch_msg_validation() -> None:
    """Verify InputBatchMsg validation, operation limits, and sequence rules."""
    attempt_id = uuid.uuid4()
    ops = [InsertOp(text="TypeVector")]
    digest = compute_operations_digest(ops)

    valid_batch = InputBatchMsg(
        attempt_id=attempt_id,
        batch_sequence_number=1,
        writer_generation=1,
        operations=ops,
        payload_digest_sha256=digest,
    )
    assert valid_batch.protocol_version == PROTOCOL_VERSION
    assert valid_batch.batch_sequence_number == 1

    # Empty operations rejected
    with pytest.raises(ValidationError):
        InputBatchMsg(
            attempt_id=attempt_id,
            batch_sequence_number=1,
            writer_generation=1,
            operations=[],
            payload_digest_sha256=digest,
        )

    # Sequence number < 1 rejected
    with pytest.raises(ValidationError):
        InputBatchMsg(
            attempt_id=attempt_id,
            batch_sequence_number=0,
            writer_generation=1,
            operations=ops,
            payload_digest_sha256=digest,
        )

    # Exceeding MAX_OPS_PER_BATCH rejected
    too_many_ops = [InsertOp(text="a") for _ in range(MAX_OPS_PER_BATCH + 1)]
    with pytest.raises(ValidationError):
        InputBatchMsg(
            attempt_id=attempt_id,
            batch_sequence_number=1,
            writer_generation=1,
            operations=too_many_ops,
            payload_digest_sha256=digest,
        )


def test_client_messages_serialization() -> None:
    """Verify serialization of all client -> server messages."""
    attempt_id = uuid.uuid4()

    # CONNECT_ATTEMPT
    connect_msg = ConnectAttemptMsg(
        attempt_id=attempt_id,
        client_session_id="tab-123",
        auth_token="tok_abc",
    )
    data = connect_msg.model_dump(mode="json")
    assert data["type"] == "CONNECT_ATTEMPT"
    assert data["attempt_id"] == str(attempt_id)

    # HEARTBEAT
    hb = HeartbeatMsg(client_time_ms=1700000000)
    assert hb.type == "HEARTBEAT"

    # RESUME_REQUEST
    resume = ResumeRequestMsg(
        attempt_id=attempt_id,
        last_received_ack_sequence=5,
    )
    assert resume.type == "RESUME_REQUEST"
    assert resume.last_received_ack_sequence == 5


def test_server_messages_serialization() -> None:
    """Verify serialization of all server -> client messages."""
    attempt_id = uuid.uuid4()
    now = datetime.now(UTC)

    # CONNECTED
    connected = ConnectedMsg(
        attempt_id=attempt_id,
        writer_generation=2,
        server_time=now,
        last_committed_sequence=10,
        deadline_at=now,
    )
    assert connected.type == "CONNECTED"
    assert connected.writer_generation == 2

    # ROUND_STATE
    round_state = RoundStateMsg(
        round_id=uuid.uuid4(),
        status="active",
        scheduled_start_at=now,
        deadline_at=now,
        challenge_content="Quick brown fox",
        token_count=3,
        checksum_sha256="abc123",
        canonical_version="v1_standard",
    )
    assert round_state.type == "ROUND_STATE"
    assert round_state.challenge_content == "Quick brown fox"

    # INPUT_ACK
    ack = InputAckMsg(
        attempt_id=attempt_id,
        batch_sequence_number=11,
        writer_generation=2,
        committed_sequence_watermark=11,
        resulting_text_length=15,
        projection_digest_sha256="deadbeef" * 8,
        server_committed_at=now,
    )
    assert ack.type == "INPUT_ACK"
    assert ack.status == "COMMITTED"

    # INPUT_REJECTED
    rejected = InputRejectedMsg(
        attempt_id=attempt_id,
        batch_sequence_number=12,
        rejection_reason="STALE_GENERATION",
        expected_sequence=11,
        writer_generation=3,
        recovery_instruction="UPGRADE_WRITER_GENERATION",
        server_time=now,
    )
    assert rejected.type == "INPUT_REJECTED"
    assert rejected.rejection_reason == "STALE_GENERATION"

    # RESUME_STATE
    resume_state = ResumeStateMsg(
        attempt_id=attempt_id,
        writer_generation=2,
        last_committed_sequence=11,
        materialized_text_projection="Quick brown",
        projection_digest_sha256="cafe" * 16,
        keystroke_count=11,
        backspace_count=0,
        deadline_at=now,
        round_status="active",
    )
    assert resume_state.materialized_text_projection == "Quick brown"

    # CLOCK_SAMPLE
    clock = ClockSampleMsg(
        client_time_ms=1000,
        server_receive_time_ms=1050,
        server_transmit_time_ms=1052,
    )
    assert clock.server_receive_time_ms == 1050

    # ERROR
    err = ErrorMsg(error_code="TEST_ERR", message="Failed cleanly", fatal=True)
    assert err.fatal is True
