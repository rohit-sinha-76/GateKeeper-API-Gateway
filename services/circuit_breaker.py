from services.redis_client import get_redis

FAILURE_THRESHOLD = 5


async def record_failure(service_name: str = "upstream") -> int:
    redis = await get_redis()
    key = f"circuit_breaker:failures:{service_name}"
    failures = await redis.incr(key)
    await redis.expire(key, 60)
    return failures


async def is_circuit_open(service_name: str = "upstream") -> bool:
    redis = await get_redis()
    key = f"circuit_breaker:failures:{service_name}"
    val = await redis.get(key)
    return int(val or 0) >= FAILURE_THRESHOLD


async def reset_circuit(service_name: str = "upstream"):
    redis = await get_redis()
    await redis.delete(f"circuit_breaker:failures:{service_name}")
