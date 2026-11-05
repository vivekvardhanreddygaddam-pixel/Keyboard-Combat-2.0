"""TypeVector Arena — Organization Management and Multi-Tenant RBAC Tests."""

import pytest
from httpx import ASGITransport, AsyncClient

from typevector.main import app

pytestmark = pytest.mark.usefixtures("require_postgres")


@pytest.mark.asyncio
async def test_organization_creation_and_owner_assignment() -> None:
    """Verify organization creation automatically assigns creator as tenant owner."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Register owner user
        email = "org.owner@mit.edu"
        password = "MitOwnerPassword2026!"
        await client.post(
            "/api/v1/identity/register",
            json={"email": email, "password": password, "display_name": "MIT Organizer"},
        )
        res_login = await client.post(
            "/api/v1/identity/login",
            json={"email": email, "password": password},
        )
        csrf = res_login.json()["csrf_token"]

        # 2. Create organization
        res_org = await client.post(
            "/api/v1/organizations",
            headers={"X-CSRF-Token": csrf},
            json={"slug": "mit-typing-club", "name": "MIT Competitive Typing Club"},
        )
        assert res_org.status_code == 201
        org_data = res_org.json()
        org_id = org_data["id"]
        assert org_data["slug"] == "mit-typing-club"

        # 3. Duplicate slug rejected with 409 Conflict
        res_dup = await client.post(
            "/api/v1/organizations",
            headers={"X-CSRF-Token": csrf},
            json={"slug": "mit-typing-club", "name": "MIT Duplicate"},
        )
        assert res_dup.status_code == 409
        assert res_dup.json()["code"] == "ORG_SLUG_TAKEN"

        # 4. Owner can list members
        res_members = await client.get(f"/api/v1/organizations/{org_id}/members")
        assert res_members.status_code == 200
        members = res_members.json()
        assert len(members) == 1
        assert members[0]["role"] == "owner"


@pytest.mark.asyncio
async def test_tenant_isolation_cross_organization_idor() -> None:
    """Verify that users in Organization A cannot access Organization B's members or roster."""
    transport = ASGITransport(app=app)
    async with (
        AsyncClient(transport=transport, base_url="http://test") as client_a,
        AsyncClient(transport=transport, base_url="http://test") as client_b,
    ):
        # Create Org A
        await client_a.post(
            "/api/v1/identity/register",
            json={
                "email": "alice@org-a.com",
                "password": "PasswordOrgA123!",
                "display_name": "Alice A",
            },
        )
        login_a = await client_a.post(
            "/api/v1/identity/login",
            json={"email": "alice@org-a.com", "password": "PasswordOrgA123!"},
        )
        csrf_a = login_a.json()["csrf_token"]
        org_a = (
            await client_a.post(
                "/api/v1/organizations",
                headers={"X-CSRF-Token": csrf_a},
                json={"slug": "tenant-alpha", "name": "Tenant Alpha"},
            )
        ).json()
        assert org_a["slug"] == "tenant-alpha"

        # Create Org B
        await client_b.post(
            "/api/v1/identity/register",
            json={
                "email": "bob@org-b.com",
                "password": "PasswordOrgB123!",
                "display_name": "Bob B",
            },
        )
        login_b = await client_b.post(
            "/api/v1/identity/login",
            json={"email": "bob@org-b.com", "password": "PasswordOrgB123!"},
        )
        csrf_b = login_b.json()["csrf_token"]
        org_b = (
            await client_b.post(
                "/api/v1/organizations",
                headers={"X-CSRF-Token": csrf_b},
                json={"slug": "tenant-beta", "name": "Tenant Beta"},
            )
        ).json()

        # Alice tries to view Bob's Org B members -> 403 Forbidden
        res_cross_view = await client_a.get(f"/api/v1/organizations/{org_b['id']}/members")
        assert res_cross_view.status_code == 403
        assert res_cross_view.json()["code"] == "FORBIDDEN"

        # Alice tries to add a member to Bob's Org B -> 403 Forbidden
        res_cross_add = await client_a.post(
            f"/api/v1/organizations/{org_b['id']}/members",
            headers={"X-CSRF-Token": csrf_a},
            json={"user_id": login_a.json()["user"]["id"], "role": "organizer"},
        )
        assert res_cross_add.status_code == 403
