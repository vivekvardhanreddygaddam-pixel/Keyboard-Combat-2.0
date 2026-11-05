"""TypeVector Arena — Authentication, Authorization, and CSRF Protection."""

import uuid
from collections.abc import Callable
from typing import Annotated, Any

from fastapi import Depends, Request
from sqlalchemy import select

from typevector.config import settings
from typevector.dependencies import DbSession
from typevector.domains.identity.models import User, UserSession
from typevector.domains.identity.security import verify_csrf_token
from typevector.domains.identity.service import IdentityService
from typevector.domains.organizations.models import OrganizationMember
from typevector.errors import ForbiddenError, UnauthorizedError


async def get_current_user_and_session(
    request: Request, db_session: DbSession
) -> tuple[User, UserSession] | None:
    """Extract and validate the active session token from HTTP-only cookie."""
    raw_token = request.cookies.get(settings.session_cookie_name)
    if not raw_token:
        # Fallback to Authorization: Bearer <token> for API/testing clients
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            raw_token = auth_header[7:].strip()

    if not raw_token:
        return None

    service = IdentityService(db_session)
    return await service.validate_session_token(raw_token)


async def get_current_user_optional(
    auth_ctx: Annotated[tuple[User, UserSession] | None, Depends(get_current_user_and_session)],
) -> User | None:
    """Return the authenticated user if present, else None."""
    if not auth_ctx:
        return None
    return auth_ctx[0]


async def get_current_user(
    auth_ctx: Annotated[tuple[User, UserSession] | None, Depends(get_current_user_and_session)],
) -> User:
    """Require an authenticated user session. Raises 401 Unauthorized if missing."""
    if not auth_ctx:
        raise UnauthorizedError("Authentication session required.")
    return auth_ctx[0]


async def get_current_session_record(
    auth_ctx: Annotated[tuple[User, UserSession] | None, Depends(get_current_user_and_session)],
) -> UserSession:
    """Require active session record."""
    if not auth_ctx:
        raise UnauthorizedError("Active session required.")
    return auth_ctx[1]


async def enforce_csrf(
    request: Request,
    session_record: Annotated[UserSession, Depends(get_current_session_record)],
) -> None:
    """Enforce CSRF protection on state-mutating HTTP methods using cookie auth.

    Requires the X-CSRF-Token header matching the HMAC-SHA256 signature for this session.
    """
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        csrf_header = request.headers.get("X-CSRF-Token")
        if not csrf_header or not verify_csrf_token(csrf_header, str(session_record.id)):
            raise ForbiddenError("Invalid or missing CSRF token.")


async def require_platform_admin(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Deny-by-default platform admin guard."""
    if user.role != "platform_admin":
        raise ForbiddenError("Platform administrator privilege required.")
    return user


def require_org_role(allowed_roles: list[str]) -> Callable[..., Any]:
    """Factory creating an organization-scoped role check dependency.

    Enforces strict tenant isolation: users without explicit membership in the target
    organization are denied with 403 Forbidden.
    """

    async def _dependency(
        organization_id: uuid.UUID,
        user: Annotated[User, Depends(get_current_user)],
        db_session: DbSession,
    ) -> OrganizationMember:
        # Platform admins bypass tenant membership checks
        if user.role == "platform_admin":
            return OrganizationMember(
                organization_id=organization_id,
                user_id=user.id,
                role="owner",
            )

        stmt = select(OrganizationMember).where(
            OrganizationMember.organization_id == organization_id,
            OrganizationMember.user_id == user.id,
        )
        result = await db_session.execute(stmt)
        member = result.scalar_one_or_none()

        if not member:
            raise ForbiddenError(f"You do not belong to organization {organization_id}.")

        if member.role not in allowed_roles:
            raise ForbiddenError(
                f"Role '{member.role}' is not authorized. Required: {allowed_roles}."
            )

        return member

    return _dependency


# Standard dependency annotations for route handlers
AuthenticatedUser = Annotated[User, Depends(get_current_user)]
OptionalUser = Annotated[User | None, Depends(get_current_user_optional)]
ActiveSession = Annotated[UserSession, Depends(get_current_session_record)]
PlatformAdminUser = Annotated[User, Depends(require_platform_admin)]
