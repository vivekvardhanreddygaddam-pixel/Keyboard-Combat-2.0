"""TypeVector Arena — Curriculum Domain Models."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from typevector.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class SkillTrack(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Educational progression track (e.g., Keyboard Fundamentals, Word Accuracy, Code)."""

    __tablename__ = "skill_tracks"

    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    levels: Mapped[list["SkillTrackLevel"]] = relationship(
        "SkillTrackLevel",
        back_populates="track",
        cascade="all, delete-orphan",
        order_by="SkillTrackLevel.level_number",
    )


class SkillTrackLevel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Discrete versioned level within a skill track requiring multi-attempt qualification."""

    __tablename__ = "skill_track_levels"
    __table_args__ = (
        UniqueConstraint("skill_track_id", "level_number", name="uq_track_levels_number"),
    )

    skill_track_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("skill_tracks.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    level_number: Mapped[int] = mapped_column(Integer, nullable=False)  # 1..6
    title: Mapped[str] = mapped_column(String(255), nullable=False)  # Foundation, Beginner, etc.
    min_wpm: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)
    min_accuracy_pct: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    pass_attempts_required: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    prompt_content: Mapped[str] = mapped_column(Text, nullable=False)
    criteria_version: Mapped[str] = mapped_column(
        String(50), default="2026.1-draft", nullable=False
    )

    track: Mapped["SkillTrack"] = relationship("SkillTrack", back_populates="levels")


class UserCurriculumProgress(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Participant qualification state across an educational skill track."""

    __tablename__ = "user_curriculum_progress"
    __table_args__ = (
        UniqueConstraint("user_id", "skill_track_id", name="uq_curriculum_user_track"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    skill_track_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("skill_tracks.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    current_level_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    qualifying_attempts_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    criteria_version: Mapped[str] = mapped_column(
        String(50), default="2026.1-draft", nullable=False
    )
    passed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    track: Mapped["SkillTrack"] = relationship("SkillTrack")


class CurriculumAttempt(Base, UUIDPrimaryKeyMixin):
    """Immutable audit record of an assessment attempt submitted for a track level."""

    __tablename__ = "curriculum_attempts"
    __table_args__ = (
        Index("ix_curriculum_attempts_user_track_lvl", "user_id", "skill_track_id", "level_number"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    skill_track_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("skill_tracks.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    level_number: Mapped[int] = mapped_column(Integer, nullable=False)
    net_wpm: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)
    accuracy_pct: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    completion_pct: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    is_qualifying: Mapped[bool] = mapped_column(Boolean, nullable=False)
    criteria_version: Mapped[str] = mapped_column(String(50), nullable=False)
    evaluation_details_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
