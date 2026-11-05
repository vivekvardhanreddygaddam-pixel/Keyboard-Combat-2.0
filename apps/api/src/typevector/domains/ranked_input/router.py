"""TypeVector Arena — Ranked Input API & WebSocket Router (arena-ws-v1)."""

import json
import time
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    Query,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from pydantic import ValidationError

from typevector.auth import get_current_user
from typevector.config import settings
from typevector.database import async_session_factory
from typevector.dependencies import DbSession
from typevector.domains.events.clock import ServerClockSample, get_server_clock_sample
from typevector.domains.identity.models import User
from typevector.domains.identity.service import IdentityService
from typevector.domains.ranked_input.connection_manager import (
    ranked_connection_manager,
)
from typevector.domains.ranked_input.protocol import (
    MAX_PAYLOAD_BYTES,
    PROTOCOL_VERSION,
    ClockSampleMsg,
    ConnectAttemptMsg,
    ConnectedMsg,
    ErrorMsg,
    HeartbeatMsg,
    InputBatchMsg,
    InputRejectedMsg,
    ResumeRequestMsg,
    ResumeStateMsg,
    RoundStateMsg,
)
from typevector.domains.ranked_input.schemas import AttemptSummaryRead
from typevector.domains.ranked_input.service import RankedInputService
from typevector.domains.rounds.service import RoundService
from typevector.errors import AppError, ForbiddenError
from typevector.logging import get_logger

logger = get_logger("arena.ranked_router")

router = APIRouter(prefix="/arena", tags=["Ranked Input"])


# ---------------------------------------------------------------------------
# REST Endpoints for Ranked Attempt
# ---------------------------------------------------------------------------


@router.get("/clock", response_model=ServerClockSample)
async def get_arena_server_clock() -> ServerClockSample:
    """Return authoritative server clock sample for client drift estimation."""
    return get_server_clock_sample()


@router.get("/attempts/{attempt_id}", response_model=AttemptSummaryRead)
async def get_attempt_status(
    attempt_id: uuid.UUID,
    session: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> AttemptSummaryRead:
    """Fetch status and generation of an ongoing or completed attempt (owner or organizer)."""
    service = RankedInputService(session)
    attempt = await service.get_attempt(attempt_id)
    if attempt.user_id != user.id and getattr(user, "role", None) != "platform_admin":
        from sqlalchemy import select

        from typevector.domains.events.models import Event
        from typevector.domains.organizations.models import OrganizationMember
        from typevector.domains.rounds.models import Round

        round_obj = await session.get(Round, attempt.round_id)
        if round_obj:
            event = await session.get(Event, round_obj.event_id)
            if event:
                stmt = select(OrganizationMember).where(
                    OrganizationMember.organization_id == event.organization_id,
                    OrganizationMember.user_id == user.id,
                )
                membership = (await session.execute(stmt)).scalar_one_or_none()
                if membership and membership.role in ("owner", "organizer", "admin", "reviewer"):
                    return AttemptSummaryRead.model_validate(attempt)
        raise ForbiddenError("Actor is not authorized to inspect another participant's attempt.")
    return AttemptSummaryRead.model_validate(attempt)


@router.get("/attempts/{attempt_id}/resume", response_model=ResumeStateMsg)
async def get_attempt_resume_state(
    attempt_id: uuid.UUID,
    session: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> ResumeStateMsg:
    """REST endpoint for recovering attempt projection watermark and state."""
    service = RankedInputService(session)
    return await service.get_resume_state(attempt_id, user.id)


# ---------------------------------------------------------------------------
# WebSocket Protocol Endpoint (arena-ws-v1)
# ---------------------------------------------------------------------------


@router.websocket("/ws")
async def ranked_arena_websocket(
    websocket: WebSocket,
    token: str | None = Query(default=None),
) -> None:
    """Server-authoritative WebSocket endpoint for ranked typing competition (arena-ws-v1)."""
    # Origin verification
    origin = websocket.headers.get("origin")
    if origin and settings.app_env == "production":
        allowed = settings.cors_origins_list
        if origin not in allowed:
            logger.warning(f"WebSocket rejected due to untrusted origin: {origin}")
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Untrusted origin")
            return

    await websocket.accept()

    # Extract session token from query param or session cookie
    raw_token = token or websocket.cookies.get(settings.session_cookie_name)
    current_user: User | None = None
    bound_attempt_id: uuid.UUID | None = None

    if raw_token:
        async with async_session_factory() as auth_session:
            identity_svc = IdentityService(auth_session)
            auth_res = await identity_svc.validate_session_token(raw_token)
            if auth_res:
                current_user = auth_res[0]

    try:
        while True:
            raw_text = await websocket.receive_text()

            # Message payload size cap check
            if len(raw_text.encode("utf-8")) > MAX_PAYLOAD_BYTES:
                logger.warning("WebSocket message exceeded MAX_PAYLOAD_BYTES cap.")
                err = ErrorMsg(
                    error_code="PAYLOAD_TOO_LARGE",
                    message=f"Message size exceeds maximum allowed of {MAX_PAYLOAD_BYTES} bytes.",
                    fatal=False,
                )
                await websocket.send_json(err.model_dump(mode="json"))
                continue

            try:
                data = json.loads(raw_text)
            except json.JSONDecodeError:
                err = ErrorMsg(
                    error_code="MALFORMED_JSON",
                    message="Invalid JSON payload.",
                    fatal=False,
                )
                await websocket.send_json(err.model_dump(mode="json"))
                continue

            msg_version = data.get("protocol_version")
            msg_type = data.get("type")

            if msg_version != PROTOCOL_VERSION:
                err = ErrorMsg(
                    error_code="UNSUPPORTED_PROTOCOL_VERSION",
                    message=f"Protocol '{msg_version}' unsupported. Must use '{PROTOCOL_VERSION}'.",
                    fatal=True,
                )
                await websocket.send_json(err.model_dump(mode="json"))
                await websocket.close(code=4400, reason="Unsupported protocol version")
                break

            # ---------------------------------------------------------------
            # 1. CONNECT_ATTEMPT
            # ---------------------------------------------------------------
            if msg_type == "CONNECT_ATTEMPT":
                try:
                    conn_msg = ConnectAttemptMsg.model_validate(data)
                except ValidationError as ve:
                    err = ErrorMsg(error_code="INVALID_MESSAGE_SCHEMA", message=str(ve))
                    await websocket.send_json(err.model_dump(mode="json"))
                    continue

                # Late token auth from message if not provided in headers/query
                if not current_user and conn_msg.auth_token:
                    async with async_session_factory() as auth_session:
                        identity_svc = IdentityService(auth_session)
                        auth_res = await identity_svc.validate_session_token(conn_msg.auth_token)
                        if auth_res:
                            current_user = auth_res[0]

                if not current_user:
                    err = ErrorMsg(
                        error_code="UNAUTHORIZED",
                        message="Valid participant session required to connect to attempt.",
                        fatal=True,
                    )
                    await websocket.send_json(err.model_dump(mode="json"))
                    await websocket.close(code=4401, reason="Unauthorized")
                    break

                bound_attempt_id = conn_msg.attempt_id
                server_now = datetime.now(UTC)

                try:
                    async with async_session_factory() as sess:
                        ranked_svc = RankedInputService(sess)
                        round_svc = RoundService(sess)

                        attempt = await ranked_svc.register_writer_connection(
                            attempt_id=conn_msg.attempt_id,
                            user_id=current_user.id,
                            client_session_id=conn_msg.client_session_id,
                        )

                        # Enforce writer fencing in connection manager
                        await ranked_connection_manager.register_writer(
                            attempt_id=attempt.id,
                            generation=attempt.socket_writer_generation,
                            websocket=websocket,
                        )

                        # Dispatch CONNECTED confirmation
                        connected_out = ConnectedMsg(
                            attempt_id=attempt.id,
                            writer_generation=attempt.socket_writer_generation,
                            server_time=server_now,
                            last_committed_sequence=attempt.last_committed_sequence,
                            deadline_at=attempt.deadline_at,
                        )
                        await websocket.send_json(connected_out.model_dump(mode="json"))

                        # Dispatch ROUND_STATE (Task 1: withheld prompt if round unstarted)
                        try:
                            prompt, prompt_content = await round_svc.get_active_prompt(
                                attempt.round_id
                            )
                            round_obj = await round_svc.get_round(attempt.round_id)

                            round_state_out = RoundStateMsg(
                                round_id=round_obj.id,
                                status=round_obj.status,
                                scheduled_start_at=round_obj.scheduled_start_at,
                                deadline_at=attempt.deadline_at,
                                challenge_content=prompt_content,
                                token_count=prompt.token_count,
                                checksum_sha256=prompt.checksum_sha256,
                                canonical_version=attempt.canonical_version,
                            )
                            await websocket.send_json(round_state_out.model_dump(mode="json"))
                        except Exception as e:
                            logger.warning(f"Could not load round prompt state: {e}")

                except AppError as ae:
                    err = ErrorMsg(error_code=ae.code, message=ae.detail, fatal=True)
                    await websocket.send_json(err.model_dump(mode="json"))
                    await websocket.close(code=4403, reason=ae.detail)
                    break
                except Exception as ex:
                    logger.error(f"Error establishing ranked connection: {ex}", exc_info=True)
                    err = ErrorMsg(error_code="INTERNAL_ERROR", message=str(ex), fatal=True)
                    await websocket.send_json(err.model_dump(mode="json"))
                    await websocket.close(code=1011, reason="Internal error")
                    break

            # ---------------------------------------------------------------
            # 2. INPUT_BATCH
            # ---------------------------------------------------------------
            elif msg_type == "INPUT_BATCH":
                if not current_user or not bound_attempt_id:
                    err = ErrorMsg(
                        error_code="NOT_CONNECTED",
                        message="Must issue valid CONNECT_ATTEMPT before sending input batches.",
                        fatal=True,
                    )
                    await websocket.send_json(err.model_dump(mode="json"))
                    continue

                try:
                    batch_msg = InputBatchMsg.model_validate(data)
                except ValidationError as ve:
                    err = ErrorMsg(error_code="INVALID_BATCH_SCHEMA", message=str(ve))
                    await websocket.send_json(err.model_dump(mode="json"))
                    continue

                if batch_msg.attempt_id != bound_attempt_id:
                    rej = InputRejectedMsg(
                        attempt_id=batch_msg.attempt_id,
                        batch_sequence_number=batch_msg.batch_sequence_number,
                        rejection_reason="ATTEMPT_MISMATCH",
                        expected_sequence=1,
                        writer_generation=batch_msg.writer_generation,
                        recovery_instruction="USE_BOUND_ATTEMPT",
                        server_time=datetime.now(UTC),
                    )
                    await websocket.send_json(rej.model_dump(mode="json"))
                    continue

                # Per-connection rate limit check
                if not ranked_connection_manager.check_rate_limit(bound_attempt_id):
                    rej = InputRejectedMsg(
                        attempt_id=bound_attempt_id,
                        batch_sequence_number=batch_msg.batch_sequence_number,
                        rejection_reason="RATE_LIMIT_EXCEEDED",
                        expected_sequence=batch_msg.batch_sequence_number,
                        writer_generation=batch_msg.writer_generation,
                        recovery_instruction="THROTTLE_SUBMISSION",
                        server_time=datetime.now(UTC),
                    )
                    await websocket.send_json(rej.model_dump(mode="json"))
                    continue

                # Process batch in dedicated atomic transaction
                async with async_session_factory() as sess:
                    ranked_svc = RankedInputService(sess)
                    outcome = await ranked_svc.process_input_batch(
                        attempt_id=bound_attempt_id,
                        user_id=current_user.id,
                        batch=batch_msg,
                    )
                    # Task 6: ACK or rejection dispatched strictly after commit!
                    await websocket.send_json(outcome.model_dump(mode="json"))

            # ---------------------------------------------------------------
            # 3. HEARTBEAT
            # ---------------------------------------------------------------
            elif msg_type == "HEARTBEAT":
                try:
                    hb_msg = HeartbeatMsg.model_validate(data)
                except ValidationError as ve:
                    err = ErrorMsg(error_code="INVALID_HEARTBEAT_SCHEMA", message=str(ve))
                    await websocket.send_json(err.model_dump(mode="json"))
                    continue

                recv_ms = int(time.time() * 1000)
                clock_sample = ClockSampleMsg(
                    client_time_ms=hb_msg.client_time_ms,
                    server_receive_time_ms=recv_ms,
                    server_transmit_time_ms=int(time.time() * 1000),
                )
                await websocket.send_json(clock_sample.model_dump(mode="json"))

            # ---------------------------------------------------------------
            # 4. RESUME_REQUEST
            # ---------------------------------------------------------------
            elif msg_type == "RESUME_REQUEST":
                if not current_user:
                    err = ErrorMsg(error_code="UNAUTHORIZED", message="Authentication required.")
                    await websocket.send_json(err.model_dump(mode="json"))
                    continue

                try:
                    resume_req = ResumeRequestMsg.model_validate(data)
                except ValidationError as ve:
                    err = ErrorMsg(error_code="INVALID_RESUME_SCHEMA", message=str(ve))
                    await websocket.send_json(err.model_dump(mode="json"))
                    continue

                async with async_session_factory() as sess:
                    ranked_svc = RankedInputService(sess)
                    try:
                        resume_state = await ranked_svc.get_resume_state(
                            attempt_id=resume_req.attempt_id,
                            user_id=current_user.id,
                        )
                        await websocket.send_json(resume_state.model_dump(mode="json"))
                    except ForbiddenError as fe:
                        err = ErrorMsg(error_code="FORBIDDEN", message=fe.detail)
                        await websocket.send_json(err.model_dump(mode="json"))
                    except Exception as ex:
                        err = ErrorMsg(error_code="RESUME_ERROR", message=str(ex))
                        await websocket.send_json(err.model_dump(mode="json"))

            # ---------------------------------------------------------------
            # 5. CLIENT_STATUS
            # ---------------------------------------------------------------
            elif msg_type == "CLIENT_STATUS":
                # Observational telemetry (purely logged for audit review signals)
                logger.debug(
                    "arena.client_status_received",
                    extra={"data": data},
                )

            else:
                err = ErrorMsg(
                    error_code="UNKNOWN_MESSAGE_TYPE",
                    message=f"Message type '{msg_type}' is not recognized.",
                    fatal=False,
                )
                await websocket.send_json(err.model_dump(mode="json"))

    except WebSocketDisconnect:
        logger.info(f"WebSocket client disconnected cleanly for attempt {bound_attempt_id}")
    except Exception as exc:
        logger.error(f"WebSocket unhandled error: {exc}", exc_info=True)
    finally:
        if bound_attempt_id:
            ranked_connection_manager.disconnect(bound_attempt_id, websocket)
