"""TypeVector Arena — Organizations Domain Service."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from typevector.domains.audit.models import AuditEvent
from typevector.domains.identity.models import User
from typevector.domains.organizations.models import Organization, OrganizationMember
from typevector.errors import ConflictError, EntityNotFoundError


class OrganizationService:
    """Domain service managing organization tenants, memberships, and role assignments."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, org_id: uuid.UUID) -> Organization:
        """Fetch organization by UUID."""
        org = await self.session.get(Organization, org_id)
        if not org or org.status != "active":
            raise EntityNotFoundError(entity="Organization", identifier=org_id)
        return org

    async def get_by_slug(self, slug: str) -> Organization:
        """Fetch organization by unique URL slug."""
        stmt = select(Organization).where(Organization.slug == slug)
        result = await self.session.execute(stmt)
        org = result.scalar_one_or_none()
        if not org or org.status != "active":
            raise EntityNotFoundError(entity="Organization", identifier=slug)
        return org

    async def create_organization(self, slug: str, name: str, owner_id: uuid.UUID) -> Organization:
        """Create a new organization tenant and assign the creator as 'owner'."""
        normalized_slug = slug.strip().lower()

        existing_stmt = select(Organization).where(Organization.slug == normalized_slug)
        existing = await self.session.execute(existing_stmt)
        if existing.scalar_one_or_none():
            raise ConflictError(
                f"Organization with slug '{normalized_slug}' already exists.",
                code="ORG_SLUG_TAKEN",
            )

        org = Organization(
            slug=normalized_slug,
            name=name.strip(),
            status="active",
        )
        self.session.add(org)
        await self.session.flush()

        # Creator is automatically the initial tenant owner
        membership = OrganizationMember(
            organization_id=org.id,
            user_id=owner_id,
            role="owner",
        )
        self.session.add(membership)

        audit = AuditEvent(
            actor_user_id=owner_id,
            organization_id=org.id,
            event_type="organization.created",
            target_type="Organization",
            target_id=str(org.id),
            payload_json={"slug": normalized_slug, "name": org.name},
        )
        self.session.add(audit)

        return org

    async def add_member(
        self,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        role: str,
        actor_id: uuid.UUID,
    ) -> OrganizationMember:
        """Add or update an organization member."""
        org = await self.get_by_id(organization_id)

        stmt = select(OrganizationMember).where(
            OrganizationMember.organization_id == org.id,
            OrganizationMember.user_id == user_id,
        )
        result = await self.session.execute(stmt)
        member = result.scalar_one_or_none()

        if member:
            member.role = role
        else:
            member = OrganizationMember(
                organization_id=org.id,
                user_id=user_id,
                role=role,
            )
            self.session.add(member)

        audit = AuditEvent(
            actor_user_id=actor_id,
            organization_id=org.id,
            event_type="organization_member.assigned",
            target_type="OrganizationMember",
            target_id=str(user_id),
            payload_json={"role": role},
        )
        self.session.add(audit)
        return member

    async def list_members(self, organization_id: uuid.UUID) -> list[OrganizationMember]:
        """List all members belonging to an organization."""
        stmt = (
            select(OrganizationMember)
            .where(OrganizationMember.organization_id == organization_id)
            .order_by(OrganizationMember.created_at.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_user_organizations(self, user_id: uuid.UUID) -> list[Organization]:
        """List all organizations where the user is an active member."""
        stmt = (
            select(Organization)
            .join(OrganizationMember, Organization.id == OrganizationMember.organization_id)
            .where(OrganizationMember.user_id == user_id, Organization.status == "active")
            .order_by(Organization.name.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def remove_member(
        self,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        actor_id: uuid.UUID,
    ) -> None:
        """Remove a user from an organization."""
        stmt = select(OrganizationMember).where(
            OrganizationMember.organization_id == organization_id,
            OrganizationMember.user_id == user_id,
        )
        res = await self.session.execute(stmt)
        member = res.scalar_one_or_none()
        if not member:
            raise EntityNotFoundError(entity="OrganizationMember", identifier=user_id)

        await self.session.delete(member)

        audit = AuditEvent(
            actor_user_id=actor_id,
            organization_id=organization_id,
            event_type="organization_member.removed",
            target_type="OrganizationMember",
            target_id=str(user_id),
            payload_json={"user_id": str(user_id)},
        )
        self.session.add(audit)

    async def list_organization_members_detail(
        self, organization_id: uuid.UUID
    ) -> list[dict[str, object]]:
        """List all members belonging to an organization joined with user profile info."""
        stmt = (
            select(OrganizationMember, User)
            .join(User, OrganizationMember.user_id == User.id)
            .where(OrganizationMember.organization_id == organization_id)
            .order_by(OrganizationMember.created_at.asc())
        )
        res = await self.session.execute(stmt)
        members = []
        for member, user in res.all():
            members.append(
                {
                    "id": member.id,
                    "organization_id": member.organization_id,
                    "user_id": member.user_id,
                    "display_name": user.display_name,
                    "email": user.email,
                    "role": member.role,
                    "created_at": member.created_at,
                }
            )
        return members
