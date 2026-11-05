"""TypeVector Arena — Organizations API Router."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends

from typevector.auth import AuthenticatedUser, enforce_csrf, require_org_role
from typevector.dependencies import DbSession
from typevector.domains.organizations.schemas import (
    OrganizationCreate,
    OrganizationMemberAdd,
    OrganizationMemberDetailRead,
    OrganizationMemberRead,
    OrganizationRead,
)
from typevector.domains.organizations.service import OrganizationService

router = APIRouter(prefix="/organizations", tags=["Organizations"])


@router.post(
    "",
    response_model=OrganizationRead,
    status_code=201,
    dependencies=[Depends(enforce_csrf)],
)
async def create_organization(
    payload: OrganizationCreate,
    current_user: AuthenticatedUser,
    session: DbSession,
) -> OrganizationRead:
    """Create a new multi-tenant organization. The creator is assigned as owner."""
    service = OrganizationService(session)
    org = await service.create_organization(
        slug=payload.slug,
        name=payload.name,
        owner_id=current_user.id,
    )
    return OrganizationRead.model_validate(org)


@router.get("/by-slug/{slug}", response_model=OrganizationRead)
async def get_organization_by_slug(slug: str, session: DbSession) -> OrganizationRead:
    """Fetch public organization profile by slug."""
    service = OrganizationService(session)
    org = await service.get_by_slug(slug)
    return OrganizationRead.model_validate(org)


@router.get("/{organization_id}", response_model=OrganizationRead)
async def get_organization(organization_id: uuid.UUID, session: DbSession) -> OrganizationRead:
    """Fetch public organization profile by UUID."""
    service = OrganizationService(session)
    org = await service.get_by_id(organization_id)
    return OrganizationRead.model_validate(org)


@router.get("/user/me", response_model=list[OrganizationRead])
async def list_my_organizations(
    current_user: AuthenticatedUser,
    session: DbSession,
) -> list[OrganizationRead]:
    """List organizations the authenticated user belongs to."""
    service = OrganizationService(session)
    orgs = await service.list_user_organizations(current_user.id)
    return [OrganizationRead.model_validate(o) for o in orgs]


_org_member_guard = require_org_role(["owner", "organizer", "reviewer", "member"])
_org_admin_guard = require_org_role(["owner", "organizer"])


@router.get(
    "/{organization_id}/members",
    response_model=list[OrganizationMemberRead],
)
async def list_organization_members(
    organization_id: uuid.UUID,
    session: DbSession,
    _auth: Annotated[Any, Depends(_org_member_guard)],
) -> list[OrganizationMemberRead]:
    """List members of an organization. Enforces tenant isolation (members only)."""
    service = OrganizationService(session)
    members = await service.list_members(organization_id)
    return [OrganizationMemberRead.model_validate(m) for m in members]


@router.get(
    "/{organization_id}/members/detail",
    response_model=list[OrganizationMemberDetailRead],
)
async def list_organization_members_detail(
    organization_id: uuid.UUID,
    session: DbSession,
    _auth: Annotated[Any, Depends(_org_admin_guard)],
) -> list[OrganizationMemberDetailRead]:
    """List members of an organization joined with user name and email (admin/organizer restricted)."""
    service = OrganizationService(session)
    members = await service.list_organization_members_detail(organization_id)
    return [OrganizationMemberDetailRead(**m) for m in members]


@router.delete(
    "/{organization_id}/members/{user_id}",
    status_code=204,
    dependencies=[Depends(enforce_csrf)],
)
async def remove_organization_member(
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    current_user: AuthenticatedUser,
    session: DbSession,
    _auth: Annotated[Any, Depends(_org_admin_guard)],
) -> None:
    """Remove a member from an organization (restricted to owner or organizer)."""
    service = OrganizationService(session)
    await service.remove_member(
        organization_id=organization_id,
        user_id=user_id,
        actor_id=current_user.id,
    )
    await session.commit()


@router.post(
    "/{organization_id}/members",
    response_model=OrganizationMemberRead,
    dependencies=[Depends(enforce_csrf)],
)
async def add_organization_member(
    organization_id: uuid.UUID,
    payload: OrganizationMemberAdd,
    current_user: AuthenticatedUser,
    session: DbSession,
    _auth: Annotated[Any, Depends(_org_admin_guard)],
) -> OrganizationMemberRead:
    """Add or update member role in an organization (restricted to owner or organizer)."""
    service = OrganizationService(session)
    member = await service.add_member(
        organization_id=organization_id,
        user_id=payload.user_id,
        role=payload.role,
        actor_id=current_user.id,
    )
    return OrganizationMemberRead.model_validate(member)
