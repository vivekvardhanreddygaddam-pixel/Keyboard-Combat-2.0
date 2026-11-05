"""TypeVector Arena — OpenAPI Specification and Router Inspection Tests."""

import pytest
from httpx import ASGITransport, AsyncClient

from typevector.main import app


@pytest.mark.asyncio
async def test_openapi_schema_generated() -> None:
    """Verify that OpenAPI documentation is available and properly formed."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/openapi.json")
        assert res.status_code == 200
        schema = res.json()

        assert schema["info"]["title"] == "TypeVector Arena API"
        assert schema["openapi"].startswith("3.")

        # Check required domains exist in path routes
        paths = schema["paths"]
        expected_domain_prefixes = [
            "/api/v1/identity",
            "/api/v1/organizations",
            "/api/v1/events",
            "/api/v1/registrations",
            "/api/v1/rounds",
            "/api/v1/arena/attempts",
            "/api/v1/scores",
            "/api/v1/practice",
            "/api/v1/curriculum",
            "/api/v1/results",
            "/api/v1/integrity",
            "/api/v1/broadcast",
            "/api/v1/notifications",
            "/api/v1/exports",
            "/api/v1/audit",
            "/api/v1/operations",
        ]

        for prefix in expected_domain_prefixes:
            matching_paths = [p for p in paths if p.startswith(prefix)]
            assert len(matching_paths) > 0, (
                f"Expected at least one route matching domain prefix '{prefix}'"
            )
