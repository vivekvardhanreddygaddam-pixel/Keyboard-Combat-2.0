"""TypeVector Arena — Practice Domain Models."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from typevector.db.base import Base, UUIDPrimaryKeyMixin


class PracticeSession(Base, UUIDPrimaryKeyMixin):
    """Independent practice typing session (authenticated or anonymous)."""

    __tablename__ = "practice_sessions"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=True,
    )
    mode: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # free, timed, words, quote, code, accuracy, burst, drill
    language: Mapped[str] = mapped_column(String(50), default="en", nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    gross_wpm: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    net_wpm: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    accuracy_pct: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    error_diff_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
