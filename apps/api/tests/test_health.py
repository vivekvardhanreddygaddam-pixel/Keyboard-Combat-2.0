"""Unit tests for health and readiness endpoints."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from typevector.main import app


@pytest.mark.asyncio
async def test_healthz_endpoint() -> None:
    """Verify /healthz returns 200 OK and basic liveness information."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/healthz")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "typevector-api"


@pytest.mark.asyncio
async def test_readyz_endpoint_unavailable_when_dependencies_fail() -> None:
    """Verify /readyz returns 503 when PostgreSQL or Redis is unreachable."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Without docker running, connection to localhost:5432 / 6379 fails cleanly
        with (
            patch(
                "typevector.database.check_database_connection",
                side_effect=ConnectionRefusedError("PG down"),
            ),
            patch(
                "typevector.redis_client.check_redis_connection",
                side_effect=ConnectionRefusedError("Redis down"),
            ),
        ):
            response = await client.get("/readyz")
            assert response.status_code == 503
            data = response.json()
            assert data["status"] == "unavailable"
            assert data["ready"] is False
            assert "error" in data["checks"]["postgres"]
            assert "error" in data["checks"]["redis"]


@pytest.mark.asyncio
async def test_readyz_endpoint_ready_when_dependencies_healthy() -> None:
    """Verify /readyz returns 200 when all dependencies report healthy."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with (
            patch(
                "typevector.database.check_database_connection", new_callable=AsyncMock
            ) as mock_pg,
            patch(
                "typevector.redis_client.check_redis_connection", new_callable=AsyncMock
            ) as mock_redis,
        ):
            mock_pg.return_value = None
            mock_redis.return_value = None
            response = await client.get("/readyz")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ready"
            assert data["ready"] is True
            assert data["checks"]["postgres"] == "ok"
            assert data["checks"]["redis"] == "ok"
