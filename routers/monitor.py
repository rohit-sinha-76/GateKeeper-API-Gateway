from fastapi import APIRouter
from services.redis_client import get_redis

router = APIRouter(prefix="/api", tags=["Monitor"])


@router.get("/stats")
async def get_stats():
    """Return global traffic statistics from Redis for the dashboard."""
    redis = await get_redis()
    hits = int(await redis.get("global_hits") or 0)
    blocks = int(await redis.get("global_blocks") or 0)
    return {
        "total_hits": hits,
        "total_blocks": blocks,
        "allowed": hits - blocks,
    }
