from redis.exceptions import RedisError
from services.redis_client import get_redis
from core.config import settings
from utils.logger import get_logger

logger = get_logger(__name__)

# Atomic Redis Lua script for fixed-window counter with automatic expiration
FIXED_WINDOW_LUA_SCRIPT = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return current
"""


async def check_rate_limit(
    identifier: str,
    tier: str = "free",
    client_ip: str | None = None,
) -> tuple[bool, int, int]:
    """
    Tier-aware fixed-window rate limiter backed by an atomic Redis Lua script.
    
    Returns:
        tuple[allowed (bool), limit (int), remaining (int)]
        
    Fault Tolerance:
        If Redis is unreachable or throws a RedisError, fails open gracefully
        to maintain gateway availability while logging an operational warning.
    """
    # 1. Whitelist Bypass
    ip_to_check = client_ip or identifier.rsplit(":", 1)[0]
    if ip_to_check in settings.RATE_LIMIT_WHITELIST_IPS:
        max_limit = settings.RATE_LIMIT_TIERS.get(tier, 60)
        return True, max_limit, max_limit

    limit = settings.RATE_LIMIT_TIERS.get(tier, settings.RATE_LIMIT_TIERS.get("free", 60))
    window = settings.RATE_LIMIT_WINDOW_SECONDS
    key = f"rate_limit:{tier}:{identifier}"

    try:
        redis = await get_redis()
        count = await redis.eval(FIXED_WINDOW_LUA_SCRIPT, 1, key, window)

        # Update telemetry stats (best effort)
        try:
            async with redis.pipeline(transaction=False) as pipe:
                pipe.incr("global_hits")
                if count > limit:
                    pipe.incr("global_blocks")
                await pipe.execute()
        except RedisError as telem_err:
            logger.warning("Failed to record telemetry stats in Redis", extra={"error": str(telem_err)})

        allowed = count <= limit
        remaining = max(0, limit - count)
        return allowed, limit, remaining

    except (RedisError, ConnectionError, TimeoutError, OSError) as e:
        logger.error(
            "Redis rate-limiter unavailable; failing open gracefully",
            extra={"identifier": identifier, "tier": tier, "error": str(e)},
        )
        # Fail-Open Policy: Allow traffic if Redis is down
        return True, limit, limit

