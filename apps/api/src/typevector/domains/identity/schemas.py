"""TypeVector Arena — Identity Schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserRead(BaseModel):
    """Authenticated user profile schema (includes email for owner/admin)."""

    id: uuid.UUID
    email: EmailStr
    display_name: str
    status: str
    role: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PublicUserRead(BaseModel):
    """Sanitized public profile schema (Zero PII - no email, phone, or roll numbers)."""

    id: uuid.UUID
    display_name: str
    status: str
    role: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserProfileUpdate(BaseModel):
    """User profile rectification request (GDPR Art. 16)."""

    display_name: str = Field(min_length=2, max_length=100)


class UserRegister(BaseModel):
    """Registration request payload."""

    email: EmailStr
    password: str = Field(min_length=8, max_length=128, description="Password (min 8 chars)")
    display_name: str = Field(min_length=2, max_length=100)
    is_age_confirmed_18: bool = Field(
        default=True,
        description="Confirmation of age 18+ or parental consent. Minors require verified parental consent.",
    )


class UserLogin(BaseModel):
    """Login request payload."""

    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class LoginSuccessResponse(BaseModel):
    """Login response returning authenticated user and session-bound CSRF token."""

    user: UserRead
    csrf_token: str
    message: str = "Authenticated successfully."


class SessionInfo(BaseModel):
    """Session details schema."""

    id: uuid.UUID
    user_id: uuid.UUID
    expires_at: datetime
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class IdentityClaimCreate(BaseModel):
    """Request payload to assert an institutional identifier claim."""

    organization_id: uuid.UUID | None = None
    claim_type: str = Field(
        min_length=2,
        max_length=50,
        pattern=r"^[a-z0-9_-]+$",
        description="e.g. roll_number, student_id, institutional_email",
    )
    claim_value: str = Field(min_length=1, max_length=255)


class IdentityClaimVerify(BaseModel):
    """Reviewer payload to verify or reject an identity claim."""

    status: str = Field(pattern=r"^(verified|rejected)$")
    verification_method: str = Field(
        min_length=3,
        max_length=50,
        description="e.g. roster_csv_match, manual_admin_approval",
    )
    evidence_notes: str | None = Field(default=None, max_length=1000)


class IdentityClaimRead(BaseModel):
    """Auditable identity claim representation."""

    id: uuid.UUID
    user_id: uuid.UUID
    organization_id: uuid.UUID | None
    claim_type: str
    claim_value: str
    status: str
    verification_method: str | None
    verified_at: datetime | None
    verified_by_user_id: uuid.UUID | None
    evidence_notes: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CurrentUserRead(BaseModel):
    """Authenticated user profile with active claims."""

    user: UserRead
    csrf_token: str
    claims: list[IdentityClaimRead] = []
