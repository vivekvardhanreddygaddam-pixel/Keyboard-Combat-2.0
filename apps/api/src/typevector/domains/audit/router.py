"""TypeVector Arena — Audit API Router."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from typevector.auth import AuthenticatedUser
from typevector.common.schemas import PaginationParams
from typevector.dependencies import DbSession
from typevector.domains.audit.schemas import AuditEventRead
from typevector.domains.audit.service import AuditService
from typevector.domains.organizations.models import OrganizationMember
from typevector.errors import ForbiddenError

router = APIRouter(prefix="/audit", tags=["Audit"])


@router.get("/events", response_model=list[AuditEventRead])
async def list_audit_events(
    current_user: AuthenticatedUser,
    session: DbSession,
    pagination: Annotated[PaginationParams, Depends()],
    organization_id: Annotated[
        uuid.UUID | None, Query(description="Filter by organization")
    ] = None,
    event_type: Annotated[str | None, Query(description="Filter by action type")] = None,
    target_type: Annotated[str | None, Query(description="Filter by target type")] = None,
    target_id: Annotated[str | None, Query(description="Filter by target ID")] = None,
    search: Annotated[str | None, Query(description="Search keyword in event type/target")] = None,
) -> list[AuditEventRead]:
    """Search and filter privileged platform audit logs with automatic secret redaction."""
    is_platform_admin = getattr(current_user, "role", None) == "platform_admin"

    if organization_id and not is_platform_admin:
        stmt = select(OrganizationMember).where(
            OrganizationMember.organization_id == organization_id,
            OrganizationMember.user_id == current_user.id,
        )
        membership = (await session.execute(stmt)).scalar_one_or_none()
        if not membership or membership.role not in ("owner", "organizer", "admin"):
            raise ForbiddenError(
                "Actor is not authorized to inspect audit logs for this organization."
            )
    elif not organization_id and not is_platform_admin:
        raise ForbiddenError("Non-platform admins must specify an organization_id they administer.")

    service = AuditService(session)
    events = await service.search_events(
        organization_id=organization_id,
        event_type=event_type,
        target_type=target_type,
        target_id=target_id,
        query=search,
        limit=pagination.limit,
        offset=pagination.offset,
    )
    return [AuditEventRead.model_validate(e) for e in events]
