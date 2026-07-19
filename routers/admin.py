from fastapi import APIRouter
from services.redis_client import get_redis

router = APIRouter(prefix="/api/v1/admin", tags=["Admin"])


@router.post("/rate-limit/reset")
async def reset_rate_limit(identifier: str):
    """Reset rate limit counter for a specific IP or API key."""
    redis = await get_redis()
    key = f"rate_limit:{identifier}"
    deleted = await redis.delete(key)
    return {"status": "ok", "reset": bool(deleted), "identifier": identifier}
