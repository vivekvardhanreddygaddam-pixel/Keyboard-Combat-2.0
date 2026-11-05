"""TypeVector Arena — RFC 7807 Problem Details and Middleware Tests."""

import pytest
from fastapi import APIRouter
from httpx import ASGITransport, AsyncClient

from typevector.errors import ConflictError, EntityNotFoundError, ForbiddenError, UnauthorizedError
from typevector.main import app

router_for_error_tests = APIRouter(prefix="/test-errors", tags=["Test Errors"])


@router_for_error_tests.get("/not-found")
async def trigger_not_found() -> None:
    raise EntityNotFoundError(entity="Tournament", identifier="alpha-2026")


@router_for_error_tests.get("/conflict")
async def trigger_conflict() -> None:
    raise ConflictError(detail="Capacity limit of 100 reached.", code="CAPACITY_EXCEEDED")


@router_for_error_tests.get("/unauthorized")
async def trigger_unauthorized() -> None:
    raise UnauthorizedError()


@router_for_error_tests.get("/forbidden")
async def trigger_forbidden() -> None:
    raise ForbiddenError()


app.include_router(router_for_error_tests)


@pytest.mark.asyncio
async def test_request_id_header_generated_and_propagated() -> None:
    """Verify X-Request-ID is generated and returned on all responses."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. No incoming header -> server generates UUID
        res = await client.get("/healthz")
        assert res.status_code == 200
        assert "x-request-id" in res.headers
        generated_id = res.headers["x-request-id"]
        assert len(generated_id) > 10

        # 2. Incoming header -> server preserves and propagates
        custom_id = "req-custom-client-12345"
        res_custom = await client.get("/healthz", headers={"X-Request-ID": custom_id})
        assert res_custom.status_code == 200
        assert res_custom.headers["x-request-id"] == custom_id


@pytest.mark.asyncio
async def test_entity_not_found_rfc7807_format() -> None:
    """Verify EntityNotFoundError returns compliant application/problem+json."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/test-errors/not-found")
        assert res.status_code == 404
        assert res.headers["content-type"] == "application/problem+json"

        body = res.json()
        assert body["type"] == "https://typevector.arena/errors/not-found"
        assert body["title"] == "Entity Not Found"
        assert body["status"] == 404
        assert "alpha-2026" in body["detail"]
        assert body["instance"] == "/test-errors/not-found"
        assert body["code"] == "ENTITY_NOT_FOUND"
        assert "request_id" in body


@pytest.mark.asyncio
async def test_conflict_error_rfc7807_format() -> None:
    """Verify ConflictError returns 409 application/problem+json."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/test-errors/conflict")
        assert res.status_code == 409
        assert res.headers["content-type"] == "application/problem+json"

        body = res.json()
        assert body["code"] == "CAPACITY_EXCEEDED"
        assert body["status"] == 409
        assert "Capacity limit of 100 reached." in body["detail"]


@pytest.mark.asyncio
async def test_validation_error_rfc7807_format() -> None:
    """Verify invalid payloads return 422 with structured errors array."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Route expects UUID parameter
        res = await client.get("/api/v1/identity/users/not-a-valid-uuid")
        assert res.status_code == 422
        assert res.headers["content-type"] == "application/problem+json"

        body = res.json()
        assert body["code"] == "VALIDATION_FAILED"
        assert "errors" in body
        assert len(body["errors"]) > 0
        assert "user_id" in body["errors"][0]["field"]
