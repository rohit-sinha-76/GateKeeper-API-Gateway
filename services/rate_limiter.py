from services.redis_client import get_redis
from core.config import settings


async def check_rate_limit(identifier: str) -> tuple[bool, int, int]:
    """
    Fixed-window rate limiter using an atomic Redis Lua script.
    Includes IP whitelist bypass.
    """
    client_ip = identifier.split(":")[0]
    if client_ip in settings.RATE_LIMIT_WHITELIST_IPS:
        return True, settings.RATE_LIMIT_MAX_REQUESTS, settings.RATE_LIMIT_MAX_REQUESTS

    redis = await get_redis()
    key = f"rate_limit:{identifier}"
    limit = settings.RATE_LIMIT_MAX_REQUESTS
    window = settings.RATE_LIMIT_WINDOW_SECONDS

    lua_script = """
    local current = redis.call('INCR', KEYS[1])
    if current == 1 then
        redis.call('EXPIRE', KEYS[1], ARGV[1])
    end
    return current
    """

    count = await redis.eval(lua_script, 1, key, window)

    async with redis.pipeline(transaction=True) as pipe:
        pipe.incr("global_hits")
        if count > limit:
            pipe.incr("global_blocks")
        await pipe.execute()

    allowed = count <= limit
    remaining = max(0, limit - count)
    return allowed, limit, remaining
