"""TypeVector Arena — Ranked WebSocket Protocol (arena-ws-v1) Definitions & Schemas."""

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

PROTOCOL_VERSION: Literal["arena-ws-v1"] = "arena-ws-v1"
MAX_PAYLOAD_BYTES = 16384  # 16 KB max WebSocket message
MAX_OPS_PER_BATCH = 50
MAX_INSERT_CHARS = 256
MAX_BACKSPACE_COUNT = 100


# ---------------------------------------------------------------------------
# Input Operations (Constrained Ranked V1: Tail Insert and Tail Backspace)
# ---------------------------------------------------------------------------


class InsertOp(BaseModel):
    """Appends committed text to the current end of the projection."""

    type: Literal["insert"] = "insert"
    text: str = Field(min_length=1, max_length=MAX_INSERT_CHARS)

    model_config = ConfigDict(frozen=True)


class BackspaceOp(BaseModel):
    """Deletes scoring units from the current end of the projection."""

    type: Literal["backspace"] = "backspace"
    count: int = Field(ge=1, le=MAX_BACKSPACE_COUNT)

    model_config = ConfigDict(frozen=True)


RankedOperation = Annotated[InsertOp | BackspaceOp, Field(discriminator="type")]


def compute_operations_digest(operations: list[RankedOperation]) -> str:
    """Compute deterministic SHA-256 digest over normalized operations list."""
    normalized: list[dict[str, Any]] = []
    for op in operations:
        if isinstance(op, BackspaceOp) or (isinstance(op, dict) and op.get("type") == "backspace"):
            cnt = op.count if isinstance(op, BackspaceOp) else op["count"]
            normalized.append({"count": cnt, "type": "backspace"})
        else:
            txt = op.text if isinstance(op, InsertOp) else op["text"]
            normalized.append({"text": txt, "type": "insert"})

    canonical_bytes = json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical_bytes).hexdigest()


# ---------------------------------------------------------------------------
# Client -> Server Messages
# ---------------------------------------------------------------------------


class ConnectAttemptMsg(BaseModel):
    """Initiates connection and binds writer generation to attempt."""

    protocol_version: Literal["arena-ws-v1"] = PROTOCOL_VERSION
    type: Literal["CONNECT_ATTEMPT"] = "CONNECT_ATTEMPT"
    attempt_id: uuid.UUID
    client_session_id: str = Field(default="", max_length=128)
    auth_token: str | None = None
    sent_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class InputBatchMsg(BaseModel):
    """Monotonic keystroke batch submitted for server admission and durable ACK."""

    protocol_version: Literal["arena-ws-v1"] = PROTOCOL_VERSION
    type: Literal["INPUT_BATCH"] = "INPUT_BATCH"
    attempt_id: uuid.UUID
    batch_sequence_number: int = Field(ge=1)
    writer_generation: int = Field(ge=1)
    operations: list[RankedOperation] = Field(min_length=1, max_length=MAX_OPS_PER_BATCH)
    payload_digest_sha256: str = Field(min_length=64, max_length=64)
    client_sent_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class HeartbeatMsg(BaseModel):
    """Periodic client ping for connection liveness and clock sampling."""

    protocol_version: Literal["arena-ws-v1"] = PROTOCOL_VERSION
    type: Literal["HEARTBEAT"] = "HEARTBEAT"
    client_time_ms: int = Field(ge=0)


class ResumeRequestMsg(BaseModel):
    """Client reconnect requesting latest server watermark and projection."""

    protocol_version: Literal["arena-ws-v1"] = PROTOCOL_VERSION
    type: Literal["RESUME_REQUEST"] = "RESUME_REQUEST"
    attempt_id: uuid.UUID
    last_received_ack_sequence: int = Field(default=0, ge=0)
    client_session_id: str = Field(default="", max_length=128)


class ClientStatusMsg(BaseModel):
    """Client observational telemetry (non-disqualifying)."""

    protocol_version: Literal["arena-ws-v1"] = PROTOCOL_VERSION
    type: Literal["CLIENT_STATUS"] = "CLIENT_STATUS"
    attempt_id: uuid.UUID
    is_focused: bool = True
    buffer_length: int = Field(default=0, ge=0)
    ime_composing: bool = False


ArenaClientMessage = Annotated[
    ConnectAttemptMsg | InputBatchMsg | HeartbeatMsg | ResumeRequestMsg | ClientStatusMsg,
    Field(discriminator="type"),
]


# ---------------------------------------------------------------------------
# Server -> Client Messages
# ---------------------------------------------------------------------------


class ConnectedMsg(BaseModel):
    """Confirms attempt connection and assigns active writer generation."""

    protocol_version: Literal["arena-ws-v1"] = PROTOCOL_VERSION
    type: Literal["CONNECTED"] = "CONNECTED"
    attempt_id: uuid.UUID
    writer_generation: int
    server_time: datetime
    last_committed_sequence: int
    deadline_at: datetime | None


class RoundStateMsg(BaseModel):
    """Published round metadata; prompt content is withheld until round start."""

    protocol_version: Literal["arena-ws-v1"] = PROTOCOL_VERSION
    type: Literal["ROUND_STATE"] = "ROUND_STATE"
    round_id: uuid.UUID
    status: str
    scheduled_start_at: datetime | None
    deadline_at: datetime | None
    challenge_content: str | None = None
    token_count: int = 0
    checksum_sha256: str = ""
    canonical_version: str = "v1_standard"


class InputAckMsg(BaseModel):
    """Server durable ACK dispatched strictly after PostgreSQL transaction commit."""

    protocol_version: Literal["arena-ws-v1"] = PROTOCOL_VERSION
    type: Literal["INPUT_ACK"] = "INPUT_ACK"
    attempt_id: uuid.UUID
    batch_sequence_number: int
    writer_generation: int
    committed_sequence_watermark: int
    resulting_text_length: int
    projection_digest_sha256: str
    server_committed_at: datetime
    status: Literal["COMMITTED"] = "COMMITTED"


class InputRejectedMsg(BaseModel):
    """Rejection notification with recovery instructions."""

    protocol_version: Literal["arena-ws-v1"] = PROTOCOL_VERSION
    type: Literal["INPUT_REJECTED"] = "INPUT_REJECTED"
    attempt_id: uuid.UUID
    batch_sequence_number: int
    rejection_reason: str
    expected_sequence: int
    writer_generation: int
    recovery_instruction: str
    server_time: datetime


class ResumeStateMsg(BaseModel):
    """Resumed attempt projection snapshot for reconnect recovery."""

    protocol_version: Literal["arena-ws-v1"] = PROTOCOL_VERSION
    type: Literal["RESUME_STATE"] = "RESUME_STATE"
    attempt_id: uuid.UUID
    writer_generation: int
    last_committed_sequence: int
    materialized_text_projection: str
    projection_digest_sha256: str
    keystroke_count: int
    backspace_count: int
    deadline_at: datetime | None
    round_status: str


class ClockSampleMsg(BaseModel):
    """Clock sync sample for round-trip latency and clock uncertainty estimation."""

    protocol_version: Literal["arena-ws-v1"] = PROTOCOL_VERSION
    type: Literal["CLOCK_SAMPLE"] = "CLOCK_SAMPLE"
    client_time_ms: int
    server_receive_time_ms: int
    server_transmit_time_ms: int


class ServiceStatusMsg(BaseModel):
    """Non-authoritative service health message."""

    protocol_version: Literal["arena-ws-v1"] = PROTOCOL_VERSION
    type: Literal["SERVICE_STATUS"] = "SERVICE_STATUS"
    status: str
    server_time: datetime
    message: str | None = None


class ErrorMsg(BaseModel):
    """Protocol error envelope."""

    protocol_version: Literal["arena-ws-v1"] = PROTOCOL_VERSION
    type: Literal["ERROR"] = "ERROR"
    error_code: str
    message: str
    fatal: bool = False


class LeaderboardSnapshotMsg(BaseModel):
    """Non-authoritative spectator leaderboard update."""

    protocol_version: Literal["arena-ws-v1"] = PROTOCOL_VERSION
    type: Literal["LEADERBOARD_SNAPSHOT"] = "LEADERBOARD_SNAPSHOT"
    event_id: uuid.UUID
    round_id: uuid.UUID
    snapshot_version: int
    entries: list[dict[str, Any]]
    generated_at: datetime


ArenaServerMessage = Annotated[
    ConnectedMsg
    | RoundStateMsg
    | InputAckMsg
    | InputRejectedMsg
    | ResumeStateMsg
    | ClockSampleMsg
    | ServiceStatusMsg
    | ErrorMsg
    | LeaderboardSnapshotMsg,
    Field(discriminator="type"),
]
