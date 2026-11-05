"""TypeVector Arena — Exports Domain Models."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from typevector.db.base import Base, UUIDPrimaryKeyMixin


class ExportJob(Base, UUIDPrimaryKeyMixin):
    """Background asynchronous export job (CSV, JSON) for event organizers."""

    __tablename__ = "export_jobs"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    requested_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
    )
    export_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # event_standings, full_audit_log, participant_scores
    status: Mapped[str] = mapped_column(
        String(50), default="queued", nullable=False
    )  # queued, processing, ready, failed
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    row_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
