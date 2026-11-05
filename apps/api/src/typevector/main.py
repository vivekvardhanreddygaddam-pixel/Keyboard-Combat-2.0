"""TypeVector Arena — FastAPI Application Entrypoint."""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from typevector.config import settings
from typevector.errors import register_error_handlers
from typevector.logging import logger, setup_logging
from typevector.middleware import RequestIDMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: startup and shutdown hooks."""
    setup_logging()
    logger.info("Starting TypeVector Arena API server...")

    startup_errors: list[str] = []

    # Check PostgreSQL with a fast 1.5s timeout on startup probe
    try:
        from typevector.database import check_database_connection

        await asyncio.wait_for(check_database_connection(), timeout=1.5)
        logger.info("PostgreSQL authoritative connection verified.")
    except Exception as e:
        startup_errors.append(f"PostgreSQL unavailable: {e}")

    # Check Redis with a fast 1.5s timeout on startup probe
    try:
        from typevector.redis_client import check_redis_connection

        await asyncio.wait_for(check_redis_connection(), timeout=1.5)
        logger.info("Redis coordination connection verified.")
    except Exception as e:
        startup_errors.append(f"Redis unavailable: {e}")

    if startup_errors:
        for err in startup_errors:
            logger.warning(f"[STARTUP WARNING] {err}")

    yield

    # Graceful teardown
    logger.info("Shutting down TypeVector Arena API server...")
    try:
        from typevector.database import dispose_engine

        await dispose_engine()
    except Exception:
        pass

    try:
        from typevector.redis_client import close_redis

        await close_redis()
    except Exception:
        pass


def create_app() -> FastAPI:
    """Create and configure the FastAPI modular monolith application."""
    app = FastAPI(
        title="TypeVector Arena API",
        description="High-integrity typing practice and competitive tournament platform API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.app_debug else None,
        redoc_url="/redoc" if settings.app_debug else None,
        openapi_url="/openapi.json" if settings.app_debug else None,
    )

    # Middleware: Request ID Context
    app.add_middleware(RequestIDMiddleware)

    # Middleware: CORS
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins_list,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["*"],
            expose_headers=["X-Request-ID"],
        )

    # Exception Handlers: RFC 7807 Problem Details
    register_error_handlers(app)

    # Core Health & Readiness Probes (Root level)
    from typevector.health import router as health_router

    app.include_router(health_router)

    # Modular Domain Routers under /api/v1/
    from typevector.domains.audit.router import router as audit_router
    from typevector.domains.broadcast.router import router as broadcast_router
    from typevector.domains.curriculum.router import router as curriculum_router
    from typevector.domains.events.router import router as events_router
    from typevector.domains.exports.router import router as exports_router
    from typevector.domains.identity.router import router as identity_router
    from typevector.domains.integrity_review.router import router as integrity_router
    from typevector.domains.notifications.router import router as notifications_router
    from typevector.domains.operations.router import router as operations_router
    from typevector.domains.organizations.router import router as organizations_router
    from typevector.domains.practice.router import router as practice_router
    from typevector.domains.ranked_input.router import router as ranked_input_router
    from typevector.domains.registrations.router import router as registrations_router
    from typevector.domains.results.router import router as results_router
    from typevector.domains.rounds.router import router as rounds_router
    from typevector.domains.scoring.router import router as scoring_router

    api_v1_prefix = "/api/v1"
    app.include_router(identity_router, prefix=api_v1_prefix)
    app.include_router(organizations_router, prefix=api_v1_prefix)
    app.include_router(events_router, prefix=api_v1_prefix)
    app.include_router(registrations_router, prefix=api_v1_prefix)
    app.include_router(rounds_router, prefix=api_v1_prefix)
    app.include_router(ranked_input_router, prefix=api_v1_prefix)
    app.include_router(scoring_router, prefix=api_v1_prefix)
    app.include_router(practice_router, prefix=api_v1_prefix)
    app.include_router(curriculum_router, prefix=api_v1_prefix)
    app.include_router(results_router, prefix=api_v1_prefix)
    app.include_router(integrity_router, prefix=api_v1_prefix)
    app.include_router(broadcast_router, prefix=api_v1_prefix)
    app.include_router(notifications_router, prefix=api_v1_prefix)
    app.include_router(exports_router, prefix=api_v1_prefix)
    app.include_router(audit_router, prefix=api_v1_prefix)
    app.include_router(operations_router, prefix=api_v1_prefix)

    return app


app = create_app()
