import redis.asyncio as aioredis
from core.config import settings

# A single shared connection pool for the whole app.
_pool: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    global _pool
    if _pool is None:
        _pool = aioredis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_timeout=settings.REDIS_SOCKET_TIMEOUT,
            socket_connect_timeout=settings.REDIS_CONNECT_TIMEOUT,
            retry_on_timeout=True,
        )
    return _pool


def set_redis(client: aioredis.Redis | None) -> None:
    """Explicitly set or override the Redis client (useful for test fixtures / fakeredis)."""
    global _pool
    _pool = client


async def close_redis():
    global _pool
    if _pool:
        await _pool.aclose()
        _pool = None

