from fastapi import APIRouter
from redis.exceptions import RedisError
from services.redis_client import get_redis
from services.circuit_breaker import get_circuit_state
from services.load_balancer import load_balancer
from utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api", tags=["Monitor"])


@router.get("/stats")
async def get_stats():
    """Return real-time gateway metrics, circuit health, and load balancer telemetry for the dashboard."""
    hits = 0
    blocks = 0
    circuit_state = "CLOSED"

    try:
        redis = await get_redis()
        hits_val = await redis.get("global_hits")
        blocks_val = await redis.get("global_blocks")
        hits = int(hits_val) if hits_val else 0
        blocks = int(blocks_val) if blocks_val else 0
        state = await get_circuit_state("upstream")
        circuit_state = state.value
    except (RedisError, ConnectionError, TimeoutError, OSError) as e:
        logger.warning("Redis unavailable when fetching monitor stats", extra={"error": str(e)})

    return {
        "total_hits": hits,
        "total_blocks": blocks,
        "allowed": max(0, hits - blocks),
        "circuit_breaker": circuit_state,
        "load_balancer": load_balancer.get_stats(),
    }


