"""TypeVector Arena — Ranked Input Domain Service."""

import time
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from typevector.domains.notifications.models import TransactionalOutbox
from typevector.domains.ranked_input.engine import (
    apply_ranked_operations,
    compute_projection_digest,
)
from typevector.domains.ranked_input.models import RankedAttempt, RankedInputBatch
from typevector.domains.ranked_input.protocol import (
    InputAckMsg,
    InputBatchMsg,
    InputRejectedMsg,
    ResumeStateMsg,
    compute_operations_digest,
)
from typevector.domains.rounds.models import Round
from typevector.errors import EntityNotFoundError, ForbiddenError, InvariantViolationError
from typevector.logging import get_logger

logger = get_logger("arena.ranked_input")


class RankedInputService:
    """Domain service managing WebSocket attempt lifecycles, atomic batch persistence, and fencing."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_attempt(self, attempt_id: uuid.UUID) -> RankedAttempt:
        """Fetch ranked attempt by UUID."""
        attempt = await self.session.get(RankedAttempt, attempt_id)
        if not attempt:
            raise EntityNotFoundError(entity="RankedAttempt", identifier=attempt_id)
        return attempt

    async def validate_attempt_ownership(
        self, attempt_id: uuid.UUID, user_id: uuid.UUID
    ) -> RankedAttempt:
        """Verify that an attempt exists and is owned by the authenticating participant."""
        attempt = await self.get_attempt(attempt_id)
        if attempt.user_id != user_id:
            raise ForbiddenError(f"Participant {user_id} does not own attempt {attempt_id}")
        return attempt

    async def register_writer_connection(
        self,
        attempt_id: uuid.UUID,
        user_id: uuid.UUID,
        client_session_id: str | None = None,
    ) -> RankedAttempt:
        """Register a new active writer connection, incrementing writer generation to fence stale tabs."""
        # Row-level pessimistic lock to serialize connection admissions
        stmt = select(RankedAttempt).where(RankedAttempt.id == attempt_id).with_for_update()
        res = await self.session.execute(stmt)
        attempt = res.scalar_one_or_none()
        if not attempt:
            raise EntityNotFoundError(entity="RankedAttempt", identifier=attempt_id)

        if attempt.user_id != user_id:
            raise ForbiddenError(f"Participant {user_id} does not own attempt {attempt_id}")

        if attempt.status != "in_progress":
            raise InvariantViolationError(
                f"Attempt {attempt_id} is in status '{attempt.status}', not 'in_progress'"
            )

        # Monotonically increment writer generation (Task 3: writer-generation fencing)
        attempt.socket_writer_generation += 1
        attempt.client_session_id = client_session_id

        # Insert outbox event for connection telemetry
        outbox = TransactionalOutbox(
            id=uuid.uuid4(),
            event_type="ranked.writer_connected",
            payload_json={
                "attempt_id": str(attempt.id),
                "user_id": str(user_id),
                "writer_generation": attempt.socket_writer_generation,
                "client_session_id": client_session_id,
            },
        )
        self.session.add(outbox)
        await self.session.commit()

        logger.info(
            "ranked_input.writer_registered",
            extra={
                "attempt_id": str(attempt.id),
                "writer_generation": attempt.socket_writer_generation,
            },
        )
        return attempt

    async def get_resume_state(self, attempt_id: uuid.UUID, user_id: uuid.UUID) -> ResumeStateMsg:
        """Fetch current projected state and watermark for reconnection resynchronization."""
        attempt = await self.validate_attempt_ownership(attempt_id, user_id)

        round_stmt = select(Round).where(Round.id == attempt.round_id)
        round_res = await self.session.execute(round_stmt)
        round_obj = round_res.scalar_one_or_none()
        round_status = round_obj.status if round_obj else "unknown"

        return ResumeStateMsg(
            attempt_id=attempt.id,
            writer_generation=attempt.socket_writer_generation,
            last_committed_sequence=attempt.last_committed_sequence,
            materialized_text_projection=attempt.current_text_projection,
            projection_digest_sha256=attempt.projection_digest_sha256,
            keystroke_count=attempt.keystroke_count,
            backspace_count=attempt.backspace_count,
            deadline_at=attempt.deadline_at,
            round_status=round_status,
        )

    async def process_input_batch(
        self,
        attempt_id: uuid.UUID,
        user_id: uuid.UUID,
        batch: InputBatchMsg,
    ) -> InputAckMsg | InputRejectedMsg:
        """Process input batch with atomic validation, projection update, and durable persistence.

        Task 5: In ONE PostgreSQL transaction validate state/deadline/generation/sequence/limits;
        append immutable batch evidence; update materialized text projection, digest, sequence
        watermark, and counters; and insert an outbox event.
        Task 6: Send INPUT_ACK only after transaction commit.
        """
        start_time = time.monotonic()
        server_admitted_at = datetime.now(UTC)

        # 1. Pessimistic row-level lock on attempt to serialize incoming batches
        stmt = select(RankedAttempt).where(RankedAttempt.id == attempt_id).with_for_update()
        res = await self.session.execute(stmt)
        attempt = res.scalar_one_or_none()

        if not attempt:
            return InputRejectedMsg(
                attempt_id=attempt_id,
                batch_sequence_number=batch.batch_sequence_number,
                rejection_reason="ATTEMPT_NOT_FOUND",
                expected_sequence=1,
                writer_generation=batch.writer_generation,
                recovery_instruction="ABORT_ATTEMPT",
                server_time=server_admitted_at,
            )

        # 2. Authorization check
        if attempt.user_id != user_id:
            logger.warning(
                "ranked_input.unauthorized_attempt_access",
                extra={"attempt_id": str(attempt_id), "user_id": str(user_id)},
            )
            return InputRejectedMsg(
                attempt_id=attempt.id,
                batch_sequence_number=batch.batch_sequence_number,
                rejection_reason="FORBIDDEN_ATTEMPT_OWNERSHIP",
                expected_sequence=attempt.last_committed_sequence + 1,
                writer_generation=attempt.socket_writer_generation,
                recovery_instruction="ABORT_ATTEMPT",
                server_time=server_admitted_at,
            )

        # 3. Status check
        if attempt.status != "in_progress":
            return InputRejectedMsg(
                attempt_id=attempt.id,
                batch_sequence_number=batch.batch_sequence_number,
                rejection_reason=f"ATTEMPT_NOT_ACTIVE_{attempt.status.upper()}",
                expected_sequence=attempt.last_committed_sequence + 1,
                writer_generation=attempt.socket_writer_generation,
                recovery_instruction="STOP_INPUT",
                server_time=server_admitted_at,
            )

        # 4. Deadline admission check (Task 7: Server-observed time cutoff)
        if attempt.deadline_at is not None and server_admitted_at > attempt.deadline_at:
            logger.info(
                "ranked_input.deadline_exceeded",
                extra={
                    "attempt_id": str(attempt.id),
                    "deadline_at": attempt.deadline_at.isoformat(),
                    "admitted_at": server_admitted_at.isoformat(),
                },
            )
            return InputRejectedMsg(
                attempt_id=attempt.id,
                batch_sequence_number=batch.batch_sequence_number,
                rejection_reason="DEADLINE_EXCEEDED",
                expected_sequence=attempt.last_committed_sequence + 1,
                writer_generation=attempt.socket_writer_generation,
                recovery_instruction="SUBMIT_FINAL_ATTEMPT",
                server_time=server_admitted_at,
            )

        # 5. Writer generation check (Task 3: Stale writer fencing)
        if batch.writer_generation < attempt.socket_writer_generation:
            logger.warning(
                "ranked_input.stale_generation_rejected",
                extra={
                    "attempt_id": str(attempt.id),
                    "batch_generation": batch.writer_generation,
                    "active_generation": attempt.socket_writer_generation,
                },
            )
            return InputRejectedMsg(
                attempt_id=attempt.id,
                batch_sequence_number=batch.batch_sequence_number,
                rejection_reason="STALE_GENERATION",
                expected_sequence=attempt.last_committed_sequence + 1,
                writer_generation=attempt.socket_writer_generation,
                recovery_instruction="UPGRADE_WRITER_GENERATION",
                server_time=server_admitted_at,
            )

        if batch.writer_generation > attempt.socket_writer_generation:
            return InputRejectedMsg(
                attempt_id=attempt.id,
                batch_sequence_number=batch.batch_sequence_number,
                rejection_reason="INVALID_FUTURE_GENERATION",
                expected_sequence=attempt.last_committed_sequence + 1,
                writer_generation=attempt.socket_writer_generation,
                recovery_instruction="RECONNECT_WRITER",
                server_time=server_admitted_at,
            )

        # 6. Payload digest integrity validation
        computed_digest = compute_operations_digest(batch.operations)
        if computed_digest != batch.payload_digest_sha256:
            logger.warning(
                "ranked_input.digest_mismatch",
                extra={"attempt_id": str(attempt.id), "sequence": batch.batch_sequence_number},
            )
            return InputRejectedMsg(
                attempt_id=attempt.id,
                batch_sequence_number=batch.batch_sequence_number,
                rejection_reason="INVALID_PAYLOAD_DIGEST",
                expected_sequence=attempt.last_committed_sequence + 1,
                writer_generation=attempt.socket_writer_generation,
                recovery_instruction="RECALCULATE_DIGEST",
                server_time=server_admitted_at,
            )

        # 7. Monotonic sequence admission (Task 4)
        current_watermark = attempt.last_committed_sequence

        # Case A: Sequence already committed or duplicate replay (S <= W)
        if batch.batch_sequence_number <= current_watermark:
            batch_stmt = select(RankedInputBatch).where(
                RankedInputBatch.attempt_id == attempt.id,
                RankedInputBatch.batch_sequence_number == batch.batch_sequence_number,
            )
            existing_batch = (await self.session.execute(batch_stmt)).scalar_one_or_none()

            if (
                existing_batch
                and existing_batch.payload_digest_sha256 == batch.payload_digest_sha256
            ):
                # Idempotent replay: return identical committed outcome without modifying state
                logger.info(
                    "ranked_input.idempotent_replay_acked",
                    extra={"attempt_id": str(attempt.id), "sequence": batch.batch_sequence_number},
                )
                return InputAckMsg(
                    attempt_id=attempt.id,
                    batch_sequence_number=batch.batch_sequence_number,
                    writer_generation=attempt.socket_writer_generation,
                    committed_sequence_watermark=current_watermark,
                    resulting_text_length=existing_batch.resulting_text_length,
                    projection_digest_sha256=existing_batch.resulting_projection_digest,
                    server_committed_at=existing_batch.server_admitted_at,
                    status="COMMITTED",
                )

            # Different digest on already committed sequence: Conflicting payload!
            logger.warning(
                "ranked_input.conflicting_replay_digest",
                extra={"attempt_id": str(attempt.id), "sequence": batch.batch_sequence_number},
            )
            return InputRejectedMsg(
                attempt_id=attempt.id,
                batch_sequence_number=batch.batch_sequence_number,
                rejection_reason="CONFLICTING_REPLAY_DIGEST",
                expected_sequence=current_watermark + 1,
                writer_generation=attempt.socket_writer_generation,
                recovery_instruction="RESYNC_PROJECTION_FROM_SERVER",
                server_time=server_admitted_at,
            )

        # Case B: Gap in sequence (S > W + 1)
        if batch.batch_sequence_number > current_watermark + 1:
            logger.warning(
                "ranked_input.sequence_gap_detected",
                extra={
                    "attempt_id": str(attempt.id),
                    "received_seq": batch.batch_sequence_number,
                    "expected_seq": current_watermark + 1,
                },
            )
            return InputRejectedMsg(
                attempt_id=attempt.id,
                batch_sequence_number=batch.batch_sequence_number,
                rejection_reason="OUT_OF_ORDER_SEQUENCE",
                expected_sequence=current_watermark + 1,
                writer_generation=attempt.socket_writer_generation,
                recovery_instruction="REPLAY_FROM_WATERMARK",
                server_time=server_admitted_at,
            )

        # Case C: Exact next monotonic sequence (S == W + 1)
        # Apply operations incrementally to projection (Task 8: O(ops) without full-history replay)
        new_text, added_keys, actual_backspaces = apply_ranked_operations(
            attempt.current_text_projection,
            batch.operations,
            canonical_version=attempt.canonical_version,
        )
        new_digest = compute_projection_digest(new_text)

        # Mutate attempt projection
        attempt.current_text_projection = new_text
        attempt.projection_digest_sha256 = new_digest
        attempt.last_committed_sequence = batch.batch_sequence_number
        attempt.keystroke_count += added_keys
        attempt.backspace_count += actual_backspaces

        # Append immutable batch evidence
        batch_record = RankedInputBatch(
            id=uuid.uuid4(),
            attempt_id=attempt.id,
            event_id=attempt.event_id,
            batch_sequence_number=batch.batch_sequence_number,
            writer_generation=batch.writer_generation,
            raw_events_json=batch.model_dump(mode="json"),
            payload_digest_sha256=batch.payload_digest_sha256,
            resulting_text_length=len(new_text),
            resulting_projection_digest=new_digest,
            server_admitted_at=server_admitted_at,
            acked_at=server_admitted_at,
        )
        self.session.add(batch_record)

        # Insert Transactional Outbox event
        outbox_event = TransactionalOutbox(
            id=uuid.uuid4(),
            event_type="ranked.input_admitted",
            payload_json={
                "attempt_id": str(attempt.id),
                "event_id": str(attempt.event_id),
                "round_id": str(attempt.round_id),
                "sequence": batch.batch_sequence_number,
                "writer_generation": batch.writer_generation,
                "text_length": len(new_text),
                "keystroke_count": attempt.keystroke_count,
                "backspace_count": attempt.backspace_count,
            },
        )
        self.session.add(outbox_event)

        # Commit PostgreSQL transaction
        await self.session.commit()

        commit_elapsed_ms = round((time.monotonic() - start_time) * 1000, 2)
        logger.info(
            "ranked_input.batch_committed",
            extra={
                "attempt_id": str(attempt.id),
                "sequence": batch.batch_sequence_number,
                "text_length": len(new_text),
                "commit_ms": commit_elapsed_ms,
            },
        )

        # Return durable ACK strictly after commit
        return InputAckMsg(
            attempt_id=attempt.id,
            batch_sequence_number=batch.batch_sequence_number,
            writer_generation=attempt.socket_writer_generation,
            committed_sequence_watermark=attempt.last_committed_sequence,
            resulting_text_length=len(new_text),
            projection_digest_sha256=new_digest,
            server_committed_at=server_admitted_at,
            status="COMMITTED",
        )
