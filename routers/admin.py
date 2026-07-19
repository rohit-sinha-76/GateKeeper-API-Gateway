from fastapi import APIRouter
from services.redis_client import get_redis
from services.circuit_breaker import reset_circuit

router = APIRouter(prefix="/api/v1/admin", tags=["Admin"])


@router.post("/rate-limit/reset")
async def reset_rate_limit(identifier: str):
    """Reset rate limit counter for a specific IP or API key."""
    redis = await get_redis()
    key = f"rate_limit:{identifier}"
    deleted = await redis.delete(key)
    return {"status": "ok", "reset": bool(deleted), "identifier": identifier}


@router.post("/circuit-breaker/reset")
async def reset_circuit_breaker(service_name: str = "upstream"):
    """Reset the circuit breaker for a given service."""
    await reset_circuit(service_name)
    return {"status": "ok", "service": service_name, "circuit": "CLOSED"}
