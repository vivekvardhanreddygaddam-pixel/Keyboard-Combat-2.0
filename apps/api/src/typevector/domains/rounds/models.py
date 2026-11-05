"""TypeVector Arena — Rounds Domain Models."""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from typevector.db.base import Base, OptimisticLockMixin, TimestampMixin, UUIDPrimaryKeyMixin


class Round(Base, UUIDPrimaryKeyMixin, OptimisticLockMixin, TimestampMixin):
    """Competition round belonging to an event with strictly managed progression."""

    __tablename__ = "rounds"
    __table_args__ = (
        UniqueConstraint("event_id", "sequence_number", name="uq_rounds_event_seq"),
        UniqueConstraint("id", "event_id", name="uq_rounds_id_event"),
    )

    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("events.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), default="scheduled", nullable=False
    )  # scheduled, active, paused, closed, voided
    scheduled_start_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    pause_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    total_pause_duration_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    prompts: Mapped[list["ChallengePrompt"]] = relationship(
        "ChallengePrompt", back_populates="round", cascade="all, delete-orphan"
    )


class ChallengePrompt(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Immutable, versioned typing prompt content pinned to a round."""

    __tablename__ = "challenge_prompts"
    __table_args__ = (
        UniqueConstraint("round_id", "version_number", name="uq_prompts_round_version"),
        ForeignKeyConstraint(
            ["round_id", "event_id"],
            ["rounds.id", "rounds.event_id"],
            ondelete="CASCADE",
            name="fk_prompts_round_event",
        ),
    )

    round_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        index=True,
        nullable=False,
    )
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        index=True,
        nullable=False,
    )
    version_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    round: Mapped["Round"] = relationship("Round", back_populates="prompts")
