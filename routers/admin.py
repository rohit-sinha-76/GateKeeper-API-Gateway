from fastapi import APIRouter, Depends, Query
from core.security import verify_admin_key, ClientIdentity
from services.redis_client import get_redis
from services.circuit_breaker import reset_circuit
from utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(
    prefix="/api/v1/admin",
    tags=["Admin"],
    dependencies=[Depends(verify_admin_key)],
)


@router.post("/rate-limit/reset")
async def reset_rate_limit(
    identifier: str = Query(..., min_length=1, max_length=255, description="Target IP or key identifier"),
    admin: ClientIdentity = Depends(verify_admin_key),
):
    """Reset rate limit counter for a specific IP or API key (Admin only)."""
    redis = await get_redis()
    key = f"rate_limit:{identifier}"
    deleted = await redis.delete(key)
    logger.info("Admin reset rate limit", extra={"identifier": identifier, "admin": admin.api_key})
    return {"status": "ok", "reset": bool(deleted), "identifier": identifier}


@router.post("/circuit-breaker/reset")
async def reset_circuit_breaker(
    service_name: str = Query("upstream", min_length=1, max_length=100),
    admin: ClientIdentity = Depends(verify_admin_key),
):
    """Reset the circuit breaker to CLOSED for a given service (Admin only)."""
    await reset_circuit(service_name)
    logger.info("Admin reset circuit breaker", extra={"service": service_name, "admin": admin.api_key})
    return {"status": "ok", "service": service_name, "circuit": "CLOSED"}

