"""TypeVector Arena — Health and readiness endpoints."""

from typing import Any

from fastapi import APIRouter, Response, status

from typevector.config import settings

router = APIRouter(tags=["Health"])


@router.get("/", summary="Root API index")
async def root() -> dict[str, Any]:
    """Root endpoint providing service information and API entry points."""
    return {
        "service": "TypeVector Arena API",
        "version": "0.1.0",
        "status": "online",
        "app_env": settings.app_env,
        "docs_url": "/docs",
        "health_url": "/healthz",
        "readiness_url": "/readyz",
        "frontend_url": "http://127.0.0.1:5173",
        "message": "TypeVector Arena API is running. Open http://127.0.0.1:5173 for the web application or /docs for API documentation.",
    }


@router.get("/healthz", summary="Liveness probe")
async def healthz() -> dict[str, Any]:
    """Basic liveness check: confirms FastAPI application process is running."""
    return {
        "status": "ok",
        "app_env": settings.app_env,
        "service": "typevector-api",
    }


@router.get("/readyz", summary="Readiness probe")
async def readyz(response: Response) -> dict[str, Any]:
    """Readiness probe: validates live connectivity to PostgreSQL and Redis.

    Returns 200 if all authoritative and coordination services are connected.
    Returns 503 if any mandatory dependency is unavailable.
    """
    import asyncio

    checks: dict[str, Any] = {
        "postgres": "unknown",
        "redis": "unknown",
    }
    is_ready = True

    # Check PostgreSQL
    try:
        from typevector.database import check_database_connection

        await asyncio.wait_for(check_database_connection(), timeout=2.0)
        checks["postgres"] = "ok"
    except Exception as exc:
        checks["postgres"] = f"error: {str(exc)}"
        is_ready = False

    # Check Redis
    try:
        from typevector.redis_client import check_redis_connection

        await asyncio.wait_for(check_redis_connection(), timeout=2.0)
        checks["redis"] = "ok"
    except Exception as exc:
        checks["redis"] = f"error: {str(exc)}"
        is_ready = False

    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            "status": "unavailable",
            "ready": False,
            "checks": checks,
        }

    return {
        "status": "ready",
        "ready": True,
        "checks": checks,
    }
