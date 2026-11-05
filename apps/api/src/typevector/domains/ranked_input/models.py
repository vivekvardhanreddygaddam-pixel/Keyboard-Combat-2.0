"""TypeVector Arena — Ranked Input Domain Models."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKeyConstraint, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from typevector.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

EMPTY_TEXT_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


class RankedAttempt(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Ranked attempt tracking synchronized participant keystroke ingestion."""

    __tablename__ = "ranked_attempts"
    __table_args__ = (
        UniqueConstraint(
            "round_id", "user_id", "attempt_number", name="uq_attempts_round_user_att"
        ),
        UniqueConstraint("id", "event_id", name="uq_attempts_id_event"),
        ForeignKeyConstraint(
            ["round_id", "event_id"],
            ["rounds.id", "rounds.event_id"],
            ondelete="CASCADE",
            name="fk_attempts_round_event",
        ),
        ForeignKeyConstraint(
            ["event_id", "user_id"],
            ["event_registrations.event_id", "event_registrations.user_id"],
            ondelete="CASCADE",
            name="fk_attempts_reg_event_user",
        ),
    )

    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True, nullable=False)
    round_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True, nullable=False)
    registration_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True, nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), default="in_progress", nullable=False
    )  # in_progress, submitted, disqualified, completed, voided
    socket_writer_generation: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    client_session_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Sequence watermark, materialized projection, and metrics
    last_committed_sequence: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    current_text_projection: Mapped[str] = mapped_column(Text, default="", nullable=False)
    projection_digest_sha256: Mapped[str] = mapped_column(
        String(64), default=EMPTY_TEXT_SHA256, nullable=False
    )
    keystroke_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    backspace_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    canonical_version: Mapped[str] = mapped_column(
        String(50), default="v1_standard", nullable=False
    )

    batches: Mapped[list["RankedInputBatch"]] = relationship(
        "RankedInputBatch", back_populates="attempt", cascade="all, delete-orphan"
    )


class RankedInputBatch(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Monotonically ordered keystroke batch committed to PostgreSQL before ACK."""

    __tablename__ = "ranked_input_batches"
    __table_args__ = (
        UniqueConstraint("attempt_id", "batch_sequence_number", name="uq_batches_attempt_seq"),
        ForeignKeyConstraint(
            ["attempt_id", "event_id"],
            ["ranked_attempts.id", "ranked_attempts.event_id"],
            ondelete="CASCADE",
            name="fk_batches_attempt_event",
        ),
    )

    attempt_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True, nullable=False)
    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True, nullable=False)
    batch_sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    writer_generation: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_events_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    payload_digest_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    resulting_text_length: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    resulting_projection_digest: Mapped[str] = mapped_column(
        String(64), default=EMPTY_TEXT_SHA256, nullable=False
    )
    server_admitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    acked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    attempt: Mapped["RankedAttempt"] = relationship("RankedAttempt", back_populates="batches")
