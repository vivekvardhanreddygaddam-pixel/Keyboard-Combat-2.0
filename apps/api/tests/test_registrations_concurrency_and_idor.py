"""TypeVector Arena — Registration Atomic Capacity, Idempotency, and IDOR Tests."""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from typevector.database import async_session_factory
from typevector.domains.events.models import Event
from typevector.domains.organizations.models import Organization
from typevector.main import app

pytestmark = pytest.mark.usefixtures("require_postgres")


async def create_test_event(status: str = "registration_open", capacity: int = 2) -> Event:
    """Helper to persist a test event with specified capacity and status."""
    async with async_session_factory() as session:
        org = Organization(slug=f"org-{uuid.uuid4().hex[:8]}", name="Test Org", status="active")
        session.add(org)
        await session.flush()

        event = Event(
            organization_id=org.id,
            slug=f"speed-cup-{uuid.uuid4().hex[:8]}",
            title="Speed Cup 2026",
            status=status,
            capacity=capacity,
        )
        session.add(event)
        await session.commit()
        await session.refresh(event)
        return event


@pytest.mark.asyncio
async def test_registration_idempotency_and_capacity_boundary() -> None:
    """Verify natural idempotency and atomic capacity limits."""
    transport = ASGITransport(app=app)
    async with (
        AsyncClient(transport=transport, base_url="http://test") as client1,
        AsyncClient(transport=transport, base_url="http://test") as client2,
        AsyncClient(transport=transport, base_url="http://test") as client3,
    ):
        # Create event with capacity = 2
        event = await create_test_event(status="registration_open", capacity=2)

        # 1. Register User 1
        await client1.post(
            "/api/v1/identity/register",
            json={"email": "u1@test.com", "password": "Pass12345678!", "display_name": "User 1"},
        )
        login1 = await client1.post(
            "/api/v1/identity/login",
            json={"email": "u1@test.com", "password": "Pass12345678!"},
        )
        csrf1 = login1.json()["csrf_token"]

        # Register User 1 for Event
        res_reg1 = await client1.post(
            f"/api/v1/registrations/{event.id}",
            headers={"X-CSRF-Token": csrf1},
        )
        assert res_reg1.status_code == 200
        reg1_data = res_reg1.json()
        assert reg1_data["status"] == "confirmed"

        # Idempotency Check: Repeating exact same request returns existing registration without error
        res_reg1_repeat = await client1.post(
            f"/api/v1/registrations/{event.id}",
            headers={"X-CSRF-Token": csrf1},
        )
        assert res_reg1_repeat.status_code == 200
        assert res_reg1_repeat.json()["id"] == reg1_data["id"]

        # 2. Register User 2 for Event (fills remaining capacity)
        await client2.post(
            "/api/v1/identity/register",
            json={"email": "u2@test.com", "password": "Pass12345678!", "display_name": "User 2"},
        )
        login2 = await client2.post(
            "/api/v1/identity/login",
            json={"email": "u2@test.com", "password": "Pass12345678!"},
        )
        csrf2 = login2.json()["csrf_token"]

        res_reg2 = await client2.post(
            f"/api/v1/registrations/{event.id}",
            headers={"X-CSRF-Token": csrf2},
        )
        assert res_reg2.status_code == 200
        assert res_reg2.json()["status"] == "confirmed"

        # Check capacity summary reflects full
        res_cap = await client1.get(f"/api/v1/registrations/{event.id}/capacity")
        assert res_cap.status_code == 200
        assert res_cap.json()["confirmed_count"] == 2
        assert res_cap.json()["is_full"] is True

        # 3. User 3 attempts to register -> 409 Conflict (Capacity Exceeded)
        await client3.post(
            "/api/v1/identity/register",
            json={"email": "u3@test.com", "password": "Pass12345678!", "display_name": "User 3"},
        )
        login3 = await client3.post(
            "/api/v1/identity/login",
            json={"email": "u3@test.com", "password": "Pass12345678!"},
        )
        csrf3 = login3.json()["csrf_token"]

        res_reg3 = await client3.post(
            f"/api/v1/registrations/{event.id}",
            headers={"X-CSRF-Token": csrf3},
        )
        assert res_reg3.status_code == 409
        assert res_reg3.json()["code"] == "CAPACITY_EXCEEDED"

        # 4. User 1 cancels registration -> capacity freed
        res_cancel = await client1.delete(
            f"/api/v1/registrations/{event.id}",
            headers={"X-CSRF-Token": csrf1},
        )
        assert res_cancel.status_code == 200
        assert res_cancel.json()["status"] == "cancelled"

        # User 3 can now claim the vacated slot
        res_reg3_retry = await client3.post(
            f"/api/v1/registrations/{event.id}",
            headers={"X-CSRF-Token": csrf3},
        )
        assert res_reg3_retry.status_code == 200
        assert res_reg3_retry.json()["status"] == "confirmed"


@pytest.mark.asyncio
async def test_registration_lifecycle_gate_and_idor() -> None:
    """Verify registration rejects closed events and enforces IDOR permissions."""
    transport = ASGITransport(app=app)
    async with (
        AsyncClient(transport=transport, base_url="http://test") as client_a,
        AsyncClient(transport=transport, base_url="http://test") as client_b,
    ):
        # Create closed event
        event_closed = await create_test_event(status="draft", capacity=10)

        # Register User A
        await client_a.post(
            "/api/v1/identity/register",
            json={
                "email": "idor.a@test.com",
                "password": "Pass12345678!",
                "display_name": "User A",
            },
        )
        login_a = await client_a.post(
            "/api/v1/identity/login",
            json={"email": "idor.a@test.com", "password": "Pass12345678!"},
        )
        csrf_a = login_a.json()["csrf_token"]
        user_a_id = login_a.json()["user"]["id"]

        # Attempt to register for closed event -> 422 Invariant Violation
        res_closed = await client_a.post(
            f"/api/v1/registrations/{event_closed.id}",
            headers={"X-CSRF-Token": csrf_a},
        )
        assert res_closed.status_code == 422
        assert res_closed.json()["code"] == "REGISTRATION_CLOSED"

        # Now test with open event
        event_open = await create_test_event(status="registration_open", capacity=10)
        await client_a.post(
            f"/api/v1/registrations/{event_open.id}",
            headers={"X-CSRF-Token": csrf_a},
        )

        # Register User B
        await client_b.post(
            "/api/v1/identity/register",
            json={
                "email": "idor.b@test.com",
                "password": "Pass12345678!",
                "display_name": "User B",
            },
        )
        res_login_b = await client_b.post(
            "/api/v1/identity/login",
            json={"email": "idor.b@test.com", "password": "Pass12345678!"},
        )
        assert res_login_b.status_code == 200

        # User B attempts to inspect User A's registration -> 403 Forbidden
        res_idor = await client_b.get(f"/api/v1/registrations/{event_open.id}/{user_a_id}")
        assert res_idor.status_code == 403
        assert res_idor.json()["code"] == "FORBIDDEN"
