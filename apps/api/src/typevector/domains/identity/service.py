"""TypeVector Arena — Identity Domain Service."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from typevector.config import settings
from typevector.domains.audit.models import AuditEvent
from typevector.domains.identity.models import IdentityClaim, User, UserCredential, UserSession
from typevector.domains.identity.security import (
    generate_csrf_token,
    generate_secure_token,
    hash_password,
    hash_session_token,
    verify_password,
)
from typevector.errors import (
    ConflictError,
    EntityNotFoundError,
    InvariantViolationError,
    UnauthorizedError,
)


class IdentityService:
    """Domain service managing user authentication, sessions, and identity claims."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_user_by_id(self, user_id: uuid.UUID) -> User:
        """Fetch active user by UUID."""
        user = await self.session.get(User, user_id)
        if not user or user.status == "deleted":
            raise EntityNotFoundError(entity="User", identifier=user_id)
        return user

    async def register_user(
        self,
        email: str,
        password: str,
        display_name: str,
        is_age_confirmed_18: bool = True,
    ) -> User:
        """Register a new user account with Argon2id hashed credentials."""
        if not is_age_confirmed_18:
            raise InvariantViolationError(
                "Participants under 18 require verified parental consent before registration.",
                code="UNDER_18_BLOCKED",
            )

        normalized_email = email.strip().lower()

        # Check existing email
        existing_stmt = select(User).where(User.email == normalized_email)
        existing = await self.session.execute(existing_stmt)
        if existing.scalar_one_or_none():
            raise ConflictError(
                detail=f"An account with email '{normalized_email}' already exists.",
                code="EMAIL_ALREADY_REGISTERED",
            )

        if len(password) < 8:
            raise InvariantViolationError(
                "Password must be at least 8 characters long.",
                code="PASSWORD_TOO_SHORT",
            )

        now = datetime.now(UTC)
        user = User(
            email=normalized_email,
            display_name=display_name.strip(),
            status="active",
            role="participant",
        )
        self.session.add(user)
        await self.session.flush()

        # Securely hash credential
        pwd_hash = hash_password(password)
        credential = UserCredential(
            user_id=user.id,
            password_hash=pwd_hash,
            algorithm="argon2id",
            password_updated_at=now,
        )
        self.session.add(credential)

        # Audit event (never logging credentials)
        audit = AuditEvent(
            event_type="user.registered",
            target_type="User",
            target_id=str(user.id),
            payload_json={"email": normalized_email, "role": user.role},
        )
        self.session.add(audit)

        return user

    async def update_profile(self, user_id: uuid.UUID, display_name: str) -> User:
        """Update participant display name with validation and audit logging (GDPR Art. 16)."""
        clean_name = display_name.strip()
        if len(clean_name) < 2 or len(clean_name) > 100:
            raise InvariantViolationError(
                "Display name must be between 2 and 100 characters.",
                code="INVALID_DISPLAY_NAME",
            )
        user = await self.get_user_by_id(user_id)
        old_name = user.display_name
        user.display_name = clean_name

        audit = AuditEvent(
            actor_user_id=user_id,
            event_type="user.profile_updated",
            target_type="User",
            target_id=str(user.id),
            payload_json={"old_display_name": old_name, "new_display_name": clean_name},
        )
        self.session.add(audit)
        await self.session.flush()
        return user

    async def deactivate_account(self, user_id: uuid.UUID) -> User:
        """Deactivate account, revoke all active sessions, and record audit trail (GDPR Art. 17)."""
        user = await self.get_user_by_id(user_id)
        user.status = "deactivated"
        await self.revoke_all_sessions(user_id)

        audit = AuditEvent(
            actor_user_id=user_id,
            event_type="user.deactivated",
            target_type="User",
            target_id=str(user.id),
            payload_json={"reason": "User requested account closure"},
        )
        self.session.add(audit)
        await self.session.flush()
        return user

    async def authenticate(
        self,
        email: str,
        password: str,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> tuple[User, str, str]:
        """Authenticate user credentials and issue a stateful server-side session.

        Returns (user, raw_session_token, session_csrf_token).
        """
        normalized_email = email.strip().lower()

        stmt = (
            select(User)
            .options(selectinload(User.credential))
            .where(User.email == normalized_email)
        )
        result = await self.session.execute(stmt)
        user = result.scalar_one_or_none()

        if not user or not user.credential:
            raise UnauthorizedError("Invalid email or password.")

        if user.status != "active":
            raise UnauthorizedError("Account is suspended or deactivated.")

        if not verify_password(password, user.credential.password_hash):
            raise UnauthorizedError("Invalid email or password.")

        # Generate secure token
        raw_token = generate_secure_token()
        token_hash = hash_session_token(raw_token)

        now = datetime.now(UTC)
        expires_at = now + timedelta(seconds=settings.session_max_age_seconds)

        session_record = UserSession(
            user_id=user.id,
            session_token_hash=token_hash,
            expires_at=expires_at,
            last_active_at=now,
            user_agent=user_agent[:500] if user_agent else None,
            ip_address=ip_address[:45] if ip_address else None,
        )
        self.session.add(session_record)
        await self.session.flush()

        # Cryptographically bind CSRF token to this session
        csrf_token = generate_csrf_token(str(session_record.id))

        # Audit login
        audit = AuditEvent(
            actor_user_id=user.id,
            event_type="user.login",
            target_type="UserSession",
            target_id=str(session_record.id),
            payload_json={"ip_address": ip_address, "user_agent": user_agent},
            ip_address=ip_address,
        )
        self.session.add(audit)

        return user, raw_token, csrf_token

    async def validate_session_token(self, raw_token: str) -> tuple[User, UserSession] | None:
        """Validate an incoming raw session token against the database."""
        token_hash = hash_session_token(raw_token)
        now = datetime.now(UTC)

        stmt = (
            select(UserSession)
            .options(selectinload(UserSession.user))
            .where(
                UserSession.session_token_hash == token_hash,
                UserSession.expires_at > now,
            )
        )
        result = await self.session.execute(stmt)
        session_obj = result.scalar_one_or_none()

        if not session_obj or not session_obj.user or session_obj.user.status != "active":
            return None

        # Sliding window update if last_active_at is older than 5 minutes
        if (now - session_obj.last_active_at).total_seconds() > 300:
            session_obj.last_active_at = now

        return session_obj.user, session_obj

    async def logout(self, raw_token: str) -> bool:
        """Revoke a single active session."""
        token_hash = hash_session_token(raw_token)
        stmt = delete(UserSession).where(UserSession.session_token_hash == token_hash)
        result = await self.session.execute(stmt)
        count = getattr(result, "rowcount", 0)
        return bool(count and count > 0)

    async def revoke_all_sessions(self, user_id: uuid.UUID) -> int:
        """Revoke all sessions for a user (e.g., on password reset or security breach)."""
        stmt = delete(UserSession).where(UserSession.user_id == user_id)
        result = await self.session.execute(stmt)
        return int(getattr(result, "rowcount", 0) or 0)

    async def submit_claim(
        self,
        user_id: uuid.UUID,
        claim_type: str,
        claim_value: str,
        organization_id: uuid.UUID | None = None,
    ) -> IdentityClaim:
        """Submit a self-asserted identifier claim. Status remains 'unverified'."""
        normalized_val = claim_value.strip()

        # Check existing claim
        stmt = select(IdentityClaim).where(
            IdentityClaim.organization_id == organization_id,
            IdentityClaim.claim_type == claim_type,
            IdentityClaim.claim_value == normalized_val,
        )
        existing = await self.session.execute(stmt)
        if existing.scalar_one_or_none():
            raise ConflictError(
                f"Claim '{claim_type}: {normalized_val}' has already been submitted for this organization.",
                code="CLAIM_ALREADY_EXISTS",
            )

        claim = IdentityClaim(
            user_id=user_id,
            organization_id=organization_id,
            claim_type=claim_type,
            claim_value=normalized_val,
            status="unverified",
        )
        self.session.add(claim)
        await self.session.flush()

        audit = AuditEvent(
            actor_user_id=user_id,
            organization_id=organization_id,
            event_type="identity_claim.submitted",
            target_type="IdentityClaim",
            target_id=str(claim.id),
            payload_json={"claim_type": claim_type, "status": "unverified"},
        )
        self.session.add(audit)
        return claim

    async def verify_claim(
        self,
        claim_id: uuid.UUID,
        reviewer_id: uuid.UUID,
        status: str,
        method: str,
        evidence_notes: str | None = None,
    ) -> IdentityClaim:
        """Auditable review and verification of an identity claim by an organizer."""
        claim = await self.session.get(IdentityClaim, claim_id)
        if not claim:
            raise EntityNotFoundError(entity="IdentityClaim", identifier=claim_id)

        now = datetime.now(UTC)
        claim.status = status
        claim.verification_method = method
        claim.verified_at = now
        claim.verified_by_user_id = reviewer_id
        claim.evidence_notes = evidence_notes

        audit = AuditEvent(
            actor_user_id=reviewer_id,
            organization_id=claim.organization_id,
            event_type=f"identity_claim.{status}",
            target_type="IdentityClaim",
            target_id=str(claim.id),
            payload_json={
                "claim_type": claim.claim_type,
                "status": status,
                "verification_method": method,
                "evidence_notes": evidence_notes,
            },
        )
        self.session.add(audit)
        return claim

    async def get_user_claims(self, user_id: uuid.UUID) -> list[IdentityClaim]:
        """Fetch all submitted claims for a user."""
        stmt = (
            select(IdentityClaim)
            .where(IdentityClaim.user_id == user_id)
            .order_by(IdentityClaim.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
