"""TypeVector Arena — Scoring Domain Models."""

import uuid
from typing import Any

from sqlalchemy import BigInteger, Boolean, ForeignKeyConstraint, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from typevector.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ParticipantScore(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Authoritative server-calculated typing score for a ranked attempt."""

    __tablename__ = "participant_scores"
    __table_args__ = (
        UniqueConstraint("attempt_id", name="uq_scores_attempt"),
        ForeignKeyConstraint(
            ["attempt_id", "event_id"],
            ["ranked_attempts.id", "ranked_attempts.event_id"],
            ondelete="CASCADE",
            name="fk_scores_attempt_event",
        ),
    )

    attempt_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True, nullable=False)
    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True, nullable=False)
    round_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True, nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True, nullable=False)
    gross_wpm: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)
    net_wpm: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)
    accuracy_pct: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    arena_score: Mapped[int] = mapped_column(
        BigInteger, nullable=False
    )  # Integer-gated arena score
    is_complete: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    completion_ratio: Mapped[float] = mapped_column(Numeric(6, 4), default=0.0, nullable=False)
    canonical_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    score_status: Mapped[str] = mapped_column(
        String(50), default="provisional", nullable=False
    )  # provisional, reviewed, official, voided

    # Deterministic replay manifest (Task 6)
    replay_manifest_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, nullable=False
    )
