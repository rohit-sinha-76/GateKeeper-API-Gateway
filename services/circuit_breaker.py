from services.redis_client import get_redis


async def record_failure(service_name: str = "upstream") -> int:
    redis = await get_redis()
    key = f"circuit_breaker:failures:{service_name}"
    failures = await redis.incr(key)
    await redis.expire(key, 60)  # 60s failure window
    return failures


async def get_failure_count(service_name: str = "upstream") -> int:
    redis = await get_redis()
    key = f"circuit_breaker:failures:{service_name}"
    val = await redis.get(key)
    return int(val or 0)
