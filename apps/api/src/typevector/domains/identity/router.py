"""TypeVector Arena — Identity API Router."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from typevector.auth import (
    AuthenticatedUser,
    enforce_csrf,
    get_current_user_and_session,
    get_current_user_optional,
)
from typevector.common.schemas import MessageResponse
from typevector.config import settings
from typevector.dependencies import DbSession
from typevector.domains.identity.models import User, UserSession
from typevector.domains.identity.schemas import (
    CurrentUserRead,
    IdentityClaimCreate,
    IdentityClaimRead,
    IdentityClaimVerify,
    LoginSuccessResponse,
    PublicUserRead,
    UserLogin,
    UserProfileUpdate,
    UserRead,
    UserRegister,
)
from typevector.domains.identity.security import generate_csrf_token
from typevector.domains.identity.service import IdentityService
from typevector.errors import UnauthorizedError

router = APIRouter(prefix="/identity", tags=["Identity"])


@router.post("/register", response_model=UserRead, status_code=201)
async def register_account(payload: UserRegister, session: DbSession) -> UserRead:
    """Register a new user account with Argon2id password hashing."""
    service = IdentityService(session)
    user = await service.register_user(
        email=str(payload.email),
        password=payload.password,
        display_name=payload.display_name,
        is_age_confirmed_18=payload.is_age_confirmed_18,
    )
    return UserRead.model_validate(user)


@router.post("/login", response_model=LoginSuccessResponse)
async def login(
    payload: UserLogin,
    request: Request,
    response: Response,
    session: DbSession,
) -> LoginSuccessResponse:
    """Authenticate with email and password, issuing an HTTP-only secure session cookie."""
    service = IdentityService(session)
    user, raw_token, csrf_token = await service.authenticate(
        email=str(payload.email),
        password=payload.password,
        user_agent=request.headers.get("User-Agent"),
        ip_address=request.client.host if request.client else None,
    )

    # Set secure HttpOnly cookie
    response.set_cookie(
        key=settings.session_cookie_name,
        value=raw_token,
        max_age=settings.session_max_age_seconds,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
        path="/",
    )

    return LoginSuccessResponse(
        user=UserRead.model_validate(user),
        csrf_token=csrf_token,
    )


@router.post("/logout", response_model=MessageResponse)
async def logout(
    request: Request,
    response: Response,
    session: DbSession,
) -> MessageResponse:
    """Revoke active session and delete the session cookie."""
    raw_token = request.cookies.get(settings.session_cookie_name)
    if raw_token:
        service = IdentityService(session)
        await service.logout(raw_token)

    response.delete_cookie(
        key=settings.session_cookie_name,
        path="/",
        httponly=True,
        samesite="lax",
    )
    return MessageResponse(message="Logged out successfully.")


@router.get("/me", response_model=CurrentUserRead)
async def get_current_user_profile(
    auth_ctx: Annotated[tuple[User, UserSession] | None, Depends(get_current_user_and_session)],
    session: DbSession,
) -> CurrentUserRead:
    """Fetch profile, CSRF token, and claims for the currently authenticated user."""
    if not auth_ctx:
        raise UnauthorizedError("Not authenticated.")
    user, session_rec = auth_ctx
    service = IdentityService(session)
    claims = await service.get_user_claims(user.id)
    csrf_token = generate_csrf_token(str(session_rec.id))

    return CurrentUserRead(
        user=UserRead.model_validate(user),
        csrf_token=csrf_token,
        claims=[IdentityClaimRead.model_validate(c) for c in claims],
    )


@router.post(
    "/claims",
    response_model=IdentityClaimRead,
    status_code=201,
    dependencies=[Depends(enforce_csrf)],
)
async def submit_identity_claim(
    payload: IdentityClaimCreate,
    current_user: AuthenticatedUser,
    session: DbSession,
) -> IdentityClaimRead:
    """Submit a self-asserted identifier claim (e.g. roll number, student ID).

    Status is 'unverified' until reviewed by an organizer.
    """
    service = IdentityService(session)
    claim = await service.submit_claim(
        user_id=current_user.id,
        claim_type=payload.claim_type,
        claim_value=payload.claim_value,
        organization_id=payload.organization_id,
    )
    return IdentityClaimRead.model_validate(claim)


@router.post(
    "/claims/{claim_id}/verify",
    response_model=IdentityClaimRead,
    dependencies=[Depends(enforce_csrf)],
)
async def review_identity_claim(
    claim_id: uuid.UUID,
    payload: IdentityClaimVerify,
    current_user: AuthenticatedUser,
    session: DbSession,
) -> IdentityClaimRead:
    """Review and verify or reject a participant's identity claim (reviewer role required)."""
    service = IdentityService(session)
    claim = await service.verify_claim(
        claim_id=claim_id,
        reviewer_id=current_user.id,
        status=payload.status,
        method=payload.verification_method,
        evidence_notes=payload.evidence_notes,
    )
    return IdentityClaimRead.model_validate(claim)


@router.get("/claims/my", response_model=list[IdentityClaimRead])
async def list_my_claims(
    current_user: AuthenticatedUser,
    session: DbSession,
) -> list[IdentityClaimRead]:
    """List all identity claims submitted by the authenticated participant."""
    service = IdentityService(session)
    claims = await service.get_user_claims(current_user.id)
    return [IdentityClaimRead.model_validate(c) for c in claims]


@router.patch("/me", response_model=UserRead, dependencies=[Depends(enforce_csrf)])
async def update_my_profile(
    payload: UserProfileUpdate,
    current_user: AuthenticatedUser,
    session: DbSession,
) -> UserRead:
    """Update display name/handle with validation and audit trail (GDPR Art. 16)."""
    service = IdentityService(session)
    user = await service.update_profile(current_user.id, payload.display_name)
    await session.commit()
    return UserRead.model_validate(user)


@router.post("/deactivate", response_model=MessageResponse, dependencies=[Depends(enforce_csrf)])
async def deactivate_my_account(
    response: Response,
    current_user: AuthenticatedUser,
    session: DbSession,
) -> MessageResponse:
    """Deactivate user account, terminate all sessions, and clear cookie (GDPR Art. 17)."""
    service = IdentityService(session)
    await service.deactivate_account(current_user.id)
    await session.commit()

    response.delete_cookie(
        key=settings.session_cookie_name,
        path="/",
        httponly=True,
        samesite="lax",
    )
    return MessageResponse(message="Account successfully deactivated. All sessions revoked.")


@router.get("/users/{user_id}", response_model=PublicUserRead)
async def get_user_profile(
    user_id: uuid.UUID,
    session: DbSession,
    current_user: Annotated[User | None, Depends(get_current_user_optional)] = None,
) -> PublicUserRead:
    """Fetch public profile for a user with zero PII leakage (no email or roll numbers)."""
    service = IdentityService(session)
    user = await service.get_user_by_id(user_id)
    return PublicUserRead.model_validate(user)
