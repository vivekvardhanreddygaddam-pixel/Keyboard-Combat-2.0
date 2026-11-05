"""TypeVector Arena — Redis client and connection management."""

from redis.asyncio import Redis

from typevector.config import settings

_redis_client: Redis | None = None


def get_redis_client() -> Redis:
    """Return the global async Redis client instance."""
    global _redis_client
    if _redis_client is None:
        _redis_client = Redis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis_client


async def check_redis_connection() -> None:
    """Verify Redis connectivity. Raises on failure."""
    client = get_redis_client()
    await client.ping()


async def close_redis() -> None:
    """Close the Redis client connection pool."""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None
