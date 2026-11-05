"""TypeVector Arena — Pytest Configuration and Database Fixtures."""

import asyncio

import pytest

from typevector.database import check_database_connection


@pytest.fixture
async def require_postgres() -> None:
    """Fixture requiring live PostgreSQL.

    Per project standards (ADR-004), SQLite substitutions are strictly prohibited
    for constraint or concurrency tests. If PostgreSQL is offline, tests requiring
    a live database are skipped with an explicit explanatory notice.
    """
    try:
        await asyncio.wait_for(check_database_connection(), timeout=1.0)
    except Exception as e:
        pytest.skip(
            f"PostgreSQL service is offline on localhost:5432 ({e}). "
            "Start infrastructure via 'pnpm infra:up' or verify Docker daemon."
        )
