"""TypeVector Arena — Ranked WebSocket Protocol Integration Tests."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from typevector.domains.identity.models import User
from typevector.domains.ranked_input.models import RankedAttempt
from typevector.domains.ranked_input.protocol import (
    MAX_PAYLOAD_BYTES,
    PROTOCOL_VERSION,
    InputAckMsg,
    InsertOp,
    compute_operations_digest,
)
from typevector.domains.rounds.models import ChallengePrompt, Round
from typevector.main import app

client = TestClient(app)


def test_ws_unsupported_protocol_version() -> None:
    """Verify WebSocket rejects unsupported protocol versions with code 4400."""
    with (
        pytest.raises(WebSocketDisconnect) as exc_info,
        client.websocket_connect("/api/v1/arena/ws") as ws,
    ):
        ws.send_json(
            {
                "protocol_version": "invalid-v0",
                "type": "CONNECT_ATTEMPT",
                "attempt_id": str(uuid.uuid4()),
            }
        )
        msg = ws.receive_json()
        assert msg["type"] == "ERROR"
        assert msg["error_code"] == "UNSUPPORTED_PROTOCOL_VERSION"
        ws.receive_json()

    assert exc_info.value.code == 4400


def test_ws_unauthenticated_connection_rejected() -> None:
    """Verify CONNECT_ATTEMPT without valid auth session is rejected with code 4401."""
    with (
        patch(
            "typevector.domains.identity.service.IdentityService.validate_session_token",
            new=AsyncMock(return_value=None),
        ),
        pytest.raises(WebSocketDisconnect) as exc_info,
        client.websocket_connect("/api/v1/arena/ws") as ws,
    ):
        ws.send_json(
            {
                "protocol_version": PROTOCOL_VERSION,
                "type": "CONNECT_ATTEMPT",
                "attempt_id": str(uuid.uuid4()),
                "auth_token": "non_existent_token_123",
            }
        )
        msg = ws.receive_json()
        assert msg["type"] == "ERROR"
        assert msg["error_code"] == "UNAUTHORIZED"
        ws.receive_json()

    assert exc_info.value.code == 4401


def test_ws_heartbeat_returns_clock_sample() -> None:
    """Verify HEARTBEAT message returns CLOCK_SAMPLE with server timestamps."""
    with client.websocket_connect("/api/v1/arena/ws") as ws:
        ws.send_json(
            {
                "protocol_version": PROTOCOL_VERSION,
                "type": "HEARTBEAT",
                "client_time_ms": 1700000000,
            }
        )
        resp = ws.receive_json()
        assert resp["type"] == "CLOCK_SAMPLE"
        assert resp["client_time_ms"] == 1700000000
        assert resp["server_receive_time_ms"] > 0
        assert resp["server_transmit_time_ms"] >= resp["server_receive_time_ms"]


def test_ws_malformed_json_error() -> None:
    """Verify malformed JSON message receives MALFORMED_JSON error."""
    with client.websocket_connect("/api/v1/arena/ws") as ws:
        ws.send_text("not-a-json-object")
        resp = ws.receive_json()
        assert resp["type"] == "ERROR"
        assert resp["error_code"] == "MALFORMED_JSON"


def test_ws_oversized_payload_error() -> None:
    """Verify message exceeding MAX_PAYLOAD_BYTES receives PAYLOAD_TOO_LARGE error."""
    with client.websocket_connect("/api/v1/arena/ws") as ws:
        oversized = "x" * (MAX_PAYLOAD_BYTES + 100)
        ws.send_text(oversized)
        resp = ws.receive_json()
        assert resp["type"] == "ERROR"
        assert resp["error_code"] == "PAYLOAD_TOO_LARGE"


def test_ws_successful_connection_round_state_and_input_ack() -> None:
    """Verify end-to-end WebSocket connection, CONNECTED, ROUND_STATE, and INPUT_ACK flow."""
    user_id = uuid.uuid4()
    attempt_id = uuid.uuid4()
    round_id = uuid.uuid4()

    mock_user = MagicMock(spec=User)
    mock_user.id = user_id

    mock_attempt = MagicMock(spec=RankedAttempt)
    mock_attempt.id = attempt_id
    mock_attempt.user_id = user_id
    mock_attempt.round_id = round_id
    mock_attempt.socket_writer_generation = 1
    mock_attempt.last_committed_sequence = 0
    mock_attempt.deadline_at = None
    mock_attempt.canonical_version = "v1_standard"

    mock_round = MagicMock(spec=Round)
    mock_round.id = round_id
    mock_round.status = "active"
    mock_round.scheduled_start_at = None

    mock_prompt = MagicMock(spec=ChallengePrompt)
    mock_prompt.token_count = 5
    mock_prompt.checksum_sha256 = "sha256_mock"

    now_utc = datetime.now(UTC)
    ack_out = InputAckMsg(
        attempt_id=attempt_id,
        batch_sequence_number=1,
        writer_generation=1,
        committed_sequence_watermark=1,
        resulting_text_length=5,
        projection_digest_sha256="digest1234" * 6 + "abcd",
        server_committed_at=now_utc,
    )

    with (
        patch(
            "typevector.domains.identity.service.IdentityService.validate_session_token",
            new=AsyncMock(return_value=(mock_user, MagicMock())),
        ),
        patch(
            "typevector.domains.ranked_input.service.RankedInputService.register_writer_connection",
            new=AsyncMock(return_value=mock_attempt),
        ),
        patch(
            "typevector.domains.rounds.service.RoundService.get_active_prompt",
            new=AsyncMock(return_value=(mock_prompt, "Hello world")),
        ),
        patch(
            "typevector.domains.rounds.service.RoundService.get_round",
            new=AsyncMock(return_value=mock_round),
        ),
        patch(
            "typevector.domains.ranked_input.service.RankedInputService.process_input_batch",
            new=AsyncMock(return_value=ack_out),
        ),
        client.websocket_connect("/api/v1/arena/ws") as ws,
    ):
        # 1. Connect
        ws.send_json(
            {
                "protocol_version": PROTOCOL_VERSION,
                "type": "CONNECT_ATTEMPT",
                "attempt_id": str(attempt_id),
                "auth_token": "valid_token",
            }
        )

        # Expect CONNECTED
        conn_resp = ws.receive_json()
        assert conn_resp["type"] == "CONNECTED"
        assert conn_resp["writer_generation"] == 1

        # Expect ROUND_STATE
        round_resp = ws.receive_json()
        assert round_resp["type"] == "ROUND_STATE"
        assert round_resp["challenge_content"] == "Hello world"

        # 2. Submit Input Batch
        ops = [InsertOp(text="Hello")]
        ws.send_json(
            {
                "protocol_version": PROTOCOL_VERSION,
                "type": "INPUT_BATCH",
                "attempt_id": str(attempt_id),
                "batch_sequence_number": 1,
                "writer_generation": 1,
                "operations": [op.model_dump() for op in ops],
                "payload_digest_sha256": compute_operations_digest(ops),
            }
        )

        # Expect INPUT_ACK
        ack_resp = ws.receive_json()
        assert ack_resp["type"] == "INPUT_ACK"
        assert ack_resp["batch_sequence_number"] == 1
        assert ack_resp["status"] == "COMMITTED"


def test_ws_stale_writer_eviction_on_newer_connection() -> None:
    """Verify that establishing a newer writer generation actively evicts previous stale connection with code 4409."""
    user_id = uuid.uuid4()
    attempt_id = uuid.uuid4()

    mock_user = MagicMock(spec=User)
    mock_user.id = user_id

    mock_attempt_gen1 = MagicMock(spec=RankedAttempt)
    mock_attempt_gen1.id = attempt_id
    mock_attempt_gen1.user_id = user_id
    mock_attempt_gen1.round_id = uuid.uuid4()
    mock_attempt_gen1.socket_writer_generation = 1
    mock_attempt_gen1.last_committed_sequence = 0
    mock_attempt_gen1.deadline_at = None
    mock_attempt_gen1.canonical_version = "v1_standard"

    mock_attempt_gen2 = MagicMock(spec=RankedAttempt)
    mock_attempt_gen2.id = attempt_id
    mock_attempt_gen2.user_id = user_id
    mock_attempt_gen2.round_id = mock_attempt_gen1.round_id
    mock_attempt_gen2.socket_writer_generation = 2
    mock_attempt_gen2.last_committed_sequence = 0
    mock_attempt_gen2.deadline_at = None
    mock_attempt_gen2.canonical_version = "v1_standard"

    mock_round = MagicMock(spec=Round)
    mock_round.id = mock_attempt_gen1.round_id
    mock_round.status = "active"
    mock_round.scheduled_start_at = None

    mock_prompt = MagicMock(spec=ChallengePrompt)
    mock_prompt.token_count = 5
    mock_prompt.checksum_sha256 = "sha256_mock"

    with (
        patch(
            "typevector.domains.identity.service.IdentityService.validate_session_token",
            new=AsyncMock(return_value=(mock_user, MagicMock())),
        ),
        patch(
            "typevector.domains.ranked_input.service.RankedInputService.register_writer_connection",
            new=AsyncMock(side_effect=[mock_attempt_gen1, mock_attempt_gen2]),
        ),
        patch(
            "typevector.domains.rounds.service.RoundService.get_active_prompt",
            new=AsyncMock(return_value=(mock_prompt, "Hello")),
        ),
        patch(
            "typevector.domains.rounds.service.RoundService.get_round",
            new=AsyncMock(return_value=mock_round),
        ),
        client.websocket_connect("/api/v1/arena/ws") as ws1,
    ):
        ws1.send_json(
            {
                "protocol_version": PROTOCOL_VERSION,
                "type": "CONNECT_ATTEMPT",
                "attempt_id": str(attempt_id),
                "auth_token": "valid_token",
            }
        )
        resp1 = ws1.receive_json()
        assert resp1["type"] == "CONNECTED"
        assert resp1["writer_generation"] == 1
        ws1.receive_json()  # ROUND_STATE

        # Now connect ws2 for the same attempt (simulating new tab or reconnect)
        with client.websocket_connect("/api/v1/arena/ws") as ws2:
            ws2.send_json(
                {
                    "protocol_version": PROTOCOL_VERSION,
                    "type": "CONNECT_ATTEMPT",
                    "attempt_id": str(attempt_id),
                    "auth_token": "valid_token",
                }
            )
            resp2 = ws2.receive_json()
            assert resp2["type"] == "CONNECTED"
            assert resp2["writer_generation"] == 2

            # ws1 should receive eviction error
            eviction = ws1.receive_json()
            assert eviction["type"] == "ERROR"
            assert eviction["error_code"] == "STALE_WRITER_EVICTED"
            assert eviction["fatal"] is True
