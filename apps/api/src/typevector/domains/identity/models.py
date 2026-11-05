"""TypeVector Arena — Identity Domain Models."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from typevector.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """User account entity representing a registered individual."""

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), default="active", nullable=False
    )  # active, suspended, deleted
    role: Mapped[str] = mapped_column(
        String(30), default="participant", nullable=False
    )  # participant, organizer, platform_admin

    credential: Mapped["UserCredential"] = relationship(
        "UserCredential", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    sessions: Mapped[list["UserSession"]] = relationship(
        "UserSession", back_populates="user", cascade="all, delete-orphan"
    )
    claims: Mapped[list["IdentityClaim"]] = relationship(
        "IdentityClaim",
        back_populates="user",
        foreign_keys="IdentityClaim.user_id",
        cascade="all, delete-orphan",
    )


class UserCredential(Base):
    """Secure credential storage for user authentication."""

    __tablename__ = "user_credentials"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    algorithm: Mapped[str] = mapped_column(String(50), default="argon2id", nullable=False)
    password_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="credential")


class UserSession(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Active user session tracking for secure cookie authentication."""

    __tablename__ = "user_sessions"

    session_token_hash: Mapped[str] = mapped_column(
        String(128), unique=True, index=True, nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_active_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="sessions")


class IdentityClaim(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Participant-asserted institutional identifier claim awaiting verification.

    A self-entered roll number, employee code, or institutional email is strictly a
    claim until verified by an organization reviewer or verified domain match.
    """

    __tablename__ = "identity_claims"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "claim_type", "claim_value", name="uq_claims_org_type_val"
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        index=True,
        nullable=True,
    )
    claim_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # roll_number, student_id, institutional_email, government_id
    claim_value: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), default="unverified", nullable=False
    )  # unverified, pending_review, verified, rejected, revoked
    verification_method: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )  # email_domain_match, roster_csv_match, manual_admin_approval
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
    )
    evidence_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="claims", foreign_keys=[user_id])
