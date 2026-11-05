"""TypeVector Arena — Authentication, Session Lifecycle, and CSRF Protection Tests."""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from typevector.database import async_session_factory
from typevector.domains.audit.models import AuditEvent
from typevector.domains.identity.models import IdentityClaim, User, UserCredential
from typevector.domains.identity.security import verify_password
from typevector.main import app

pytestmark = pytest.mark.usefixtures("require_postgres")


@pytest.mark.asyncio
async def test_user_registration_argon2id_hashing() -> None:
    """Verify registration hashes password with Argon2id and creates audit event."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        email = "alice.typist@example.com"
        password = "SuperSecretPassword123!"
        res = await client.post(
            "/api/v1/identity/register",
            json={"email": email, "password": password, "display_name": "Alice Keypress"},
        )
        assert res.status_code == 201
        data = res.json()
        assert data["email"] == email
        assert data["display_name"] == "Alice Keypress"
        assert data["status"] == "active"
        assert data["role"] == "participant"

        # Duplicate email registration rejected with 409 Conflict
        res_dup = await client.post(
            "/api/v1/identity/register",
            json={"email": email, "password": password, "display_name": "Alice Duplicate"},
        )
        assert res_dup.status_code == 409
        assert res_dup.json()["code"] == "EMAIL_ALREADY_REGISTERED"

        # Verify database state
        async with async_session_factory() as session:
            user_stmt = select(User).where(User.email == email)
            user = (await session.execute(user_stmt)).scalar_one()

            cred_stmt = select(UserCredential).where(UserCredential.user_id == user.id)
            cred = (await session.execute(cred_stmt)).scalar_one()

            # Passwords are NEVER plaintext
            assert cred.password_hash != password
            assert cred.algorithm == "argon2id"
            assert verify_password(password, cred.password_hash) is True

            # Verify audit record does not leak password
            audit_stmt = select(AuditEvent).where(AuditEvent.target_id == str(user.id))
            audit = (await session.execute(audit_stmt)).scalar_one_or_none()
            assert audit is not None
            assert "password" not in str(audit.payload_json).lower()


@pytest.mark.asyncio
async def test_login_session_cookie_and_csrf() -> None:
    """Verify session cookie issuance, CSRF protection, and session revocation."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Register test user
        email = "bob.session@example.com"
        password = "BobPassword2026!#"
        await client.post(
            "/api/v1/identity/register",
            json={"email": email, "password": password, "display_name": "Bob Shift"},
        )

        # 2. Login with wrong password -> 401 Unauthorized
        res_bad = await client.post(
            "/api/v1/identity/login",
            json={"email": email, "password": "WrongPassword999"},
        )
        assert res_bad.status_code == 401
        assert "tv_session" not in res_bad.cookies

        # 3. Login with correct password -> 200 OK + HttpOnly cookie
        res_login = await client.post(
            "/api/v1/identity/login",
            json={"email": email, "password": password},
        )
        assert res_login.status_code == 200
        assert "tv_session" in res_login.cookies
        login_data = res_login.json()
        csrf_token = login_data["csrf_token"]
        assert len(csrf_token) == 64  # SHA-256 hex string

        # 4. Access /identity/me with session cookie
        res_me = await client.get("/api/v1/identity/me")
        assert res_me.status_code == 200
        me_data = res_me.json()
        assert me_data["user"]["email"] == email

        # 5. Mutating request without CSRF token -> 403 Forbidden
        res_no_csrf = await client.post(
            "/api/v1/identity/claims",
            json={"claim_type": "roll_number", "claim_value": "CS-2026-101"},
        )
        assert res_no_csrf.status_code == 403
        assert res_no_csrf.json()["code"] == "FORBIDDEN"

        # 6. Mutating request with valid CSRF token -> 201 Created
        res_claim = await client.post(
            "/api/v1/identity/claims",
            headers={"X-CSRF-Token": csrf_token},
            json={"claim_type": "roll_number", "claim_value": "CS-2026-101"},
        )
        assert res_claim.status_code == 201
        claim_data = res_claim.json()
        assert claim_data["status"] == "unverified"
        assert claim_data["claim_value"] == "CS-2026-101"

        # 7. Logout -> Revokes session
        res_logout = await client.post("/api/v1/identity/logout")
        assert res_logout.status_code == 200

        # Subsequent authenticated requests should fail
        res_after = await client.get("/api/v1/identity/me")
        assert res_after.status_code == 401


@pytest.mark.asyncio
async def test_identity_claim_verification_workflow() -> None:
    """Verify that user claims are separate from verified identity and auditable."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Participant creates account
        p_email = "student.claim@university.edu"
        p_pass = "StudentPass2026!"
        await client.post(
            "/api/v1/identity/register",
            json={"email": p_email, "password": p_pass, "display_name": "Student Typist"},
        )

        res_login = await client.post(
            "/api/v1/identity/login",
            json={"email": p_email, "password": p_pass},
        )
        csrf = res_login.json()["csrf_token"]

        # Submit unverified claim
        res_claim = await client.post(
            "/api/v1/identity/claims",
            headers={"X-CSRF-Token": csrf},
            json={"claim_type": "student_id", "claim_value": "U-992144"},
        )
        assert res_claim.status_code == 201
        claim_id = res_claim.json()["id"]
        assert res_claim.json()["status"] == "unverified"

        # Duplicate claim for same org + type + value rejected with 409
        res_dup_claim = await client.post(
            "/api/v1/identity/claims",
            headers={"X-CSRF-Token": csrf},
            json={"claim_type": "student_id", "claim_value": "U-992144"},
        )
        assert res_dup_claim.status_code == 409

        # Organizer reviews and verifies claim
        res_verify = await client.post(
            f"/api/v1/identity/claims/{claim_id}/verify",
            headers={"X-CSRF-Token": csrf},
            json={
                "status": "verified",
                "verification_method": "roster_csv_match",
                "evidence_notes": "Matched against Dean's List 2026 Roster",
            },
        )
        assert res_verify.status_code == 200
        verified_data = res_verify.json()
        assert verified_data["status"] == "verified"
        assert verified_data["verification_method"] == "roster_csv_match"
        assert verified_data["evidence_notes"] == "Matched against Dean's List 2026 Roster"

        # Check DB reflects verified status and audit trail
        async with async_session_factory() as session:
            claim_rec = await session.get(IdentityClaim, verified_data["id"])
            assert claim_rec is not None
            assert claim_rec.status == "verified"
            assert claim_rec.verified_at is not None
