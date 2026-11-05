"""TypeVector Arena — Events Domain Models."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from typevector.db.base import Base, OptimisticLockMixin, TimestampMixin, UUIDPrimaryKeyMixin


class Event(Base, UUIDPrimaryKeyMixin, OptimisticLockMixin, TimestampMixin):
    """Event entity representing a scheduled competition or tournament."""

    __tablename__ = "events"
    __table_args__ = (
        UniqueConstraint("organization_id", "slug", name="uq_events_org_slug"),
        UniqueConstraint("id", "organization_id", name="uq_events_id_org"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    slug: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(50), default="draft", nullable=False
    )  # draft, published, registration_open, check_in_open, ready, live, paused, completed, review, results_published, amended, cancelled, voided, archived
    capacity: Mapped[int] = mapped_column(Integer, default=100, nullable=False)

    # Event-wide pause & incident tracking (Task 6)
    pause_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    total_pause_duration_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    incident_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Prize event & scoring policy approval gate (Phase 10)
    is_prize_event: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    ruleset_approval_status: Mapped[str] = mapped_column(
        String(50), default="draft_awaiting_approval", nullable=False
    )

    rulesets: Mapped[list["EventRuleset"]] = relationship(
        "EventRuleset", back_populates="event", cascade="all, delete-orphan"
    )


class EventRuleset(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Immutable versioned rule specification for an event."""

    __tablename__ = "event_rulesets"
    __table_args__ = (
        UniqueConstraint("event_id", "version_number", name="uq_event_rulesets_version"),
    )

    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("events.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    ruleset_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    min_accuracy_pct: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=90.0)
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    scoring_formula: Mapped[str] = mapped_column(
        String(100), default="arena-score-v1", nullable=False
    )

    event: Mapped["Event"] = relationship("Event", back_populates="rulesets")
