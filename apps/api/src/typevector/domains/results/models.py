"""TypeVector Arena — Results Domain Models."""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from typevector.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class PublishedResult(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Immutable, versioned published standings for an event."""

    __tablename__ = "published_results"
    __table_args__ = (
        UniqueConstraint("event_id", "version_number", name="uq_results_event_version"),
    )

    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("events.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    version_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    published_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
    )
    signed_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Amendment relationship and policy approval (Phase 10)
    previous_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("published_results.id"),
        nullable=True,
    )
    amendment_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    ruleset_approval_status: Mapped[str] = mapped_column(
        String(50), default="draft_awaiting_approval", nullable=False
    )

    rows: Mapped[list["PublishedRankRow"]] = relationship(
        "PublishedRankRow", back_populates="result", cascade="all, delete-orphan"
    )


class PublishedRankRow(Base, UUIDPrimaryKeyMixin):
    """Immutable standing entry for a single participant within a published result."""

    __tablename__ = "published_rank_rows"
    __table_args__ = (
        UniqueConstraint("published_result_id", "rank_order", name="uq_published_ranks_order"),
    )

    published_result_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("published_results.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    rank_order: Mapped[int] = mapped_column(Integer, nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        index=True,
        nullable=False,
    )
    score_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("participant_scores.id"),
        nullable=False,
    )
    gross_wpm: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)
    net_wpm: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)
    accuracy_pct: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    arena_score: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tier: Mapped[str] = mapped_column(String(50), default="standard", nullable=False)

    result: Mapped["PublishedResult"] = relationship("PublishedResult", back_populates="rows")
