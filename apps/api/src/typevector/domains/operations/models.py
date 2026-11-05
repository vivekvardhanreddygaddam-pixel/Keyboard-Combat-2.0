"""TypeVector Arena — Operations Domain Models."""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from typevector.db.base import Base, UUIDPrimaryKeyMixin


class RetentionJob(Base, UUIDPrimaryKeyMixin):
    """Periodic data retention and compliance purge execution record."""

    __tablename__ = "retention_jobs"

    job_type: Mapped[str] = mapped_column(
        String(100), nullable=False
    )  # purge_expired_sessions, prune_unverified_attempts
    records_affected: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), default="running", nullable=False
    )  # running, completed, failed
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
