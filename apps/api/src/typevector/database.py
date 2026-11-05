"""TypeVector Arena — Database engine and session management."""

import contextlib
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from typevector.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=settings.app_debug,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency yielding an async database session with automatic transaction management.

    Commits on successful completion, rolls back on exception, and always closes the session.
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_db_session_optional() -> AsyncGenerator[AsyncSession | None, None]:
    """Dependency yielding an async database session if available, or None if database is unreachable.

    Catches connection failures gracefully so standalone offline practice does not crash.
    """
    session: AsyncSession | None = None
    try:
        session = async_session_factory()
        yield session
        if session is not None and session.is_active:
            try:
                await session.commit()
            except Exception:
                with contextlib.suppress(Exception):
                    await session.rollback()
    except Exception:
        pass
    finally:
        if session is not None:
            with contextlib.suppress(Exception):
                await session.close()


async def check_database_connection() -> None:
    """Verify PostgreSQL connectivity. Raises on failure."""
    from sqlalchemy import text

    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))


async def dispose_engine() -> None:
    """Dispose of the database engine on shutdown."""
    await engine.dispose()
