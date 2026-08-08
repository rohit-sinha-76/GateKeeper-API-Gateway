import secrets
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, Query, Body, Response, Request, HTTPException, status
from core.config import settings
from core.security import (
    verify_admin_key,
    create_admin_session_token,
    verify_admin_session_token,
    ClientIdentity,
)
from services.redis_client import get_redis
from services.circuit_breaker import reset_circuit
from services.load_balancer import load_balancer, LoadBalancingAlgorithm
from utils.logger import get_logger

logger = get_logger(__name__)

# 1. Public Auth Router (for authenticating browser sessions)
auth_router = APIRouter(prefix="/api/v1/admin/auth", tags=["Admin Auth"])

class AdminLoginRequest(BaseModel):
    admin_key: str = Field(..., description="Administrator secret key")


@auth_router.post("/login")
async def admin_login(payload: AdminLoginRequest, response: Response):
    """Authenticate admin credentials and set an HttpOnly session cookie."""
    if not secrets.compare_digest(payload.admin_key, settings.ADMIN_API_KEY):
        logger.warning("Failed admin login attempt: invalid key provided")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid administrator credentials.",
        )

    token = create_admin_session_token()
    response.set_cookie(
        key="admin_session",
        value=token,
        httponly=True,
        samesite="lax",
        max_age=86400,
        path="/",
    )
    logger.info("Admin session successfully authenticated")
    return {"status": "ok", "authenticated": True}


@auth_router.post("/logout")
async def admin_logout(response: Response):
    """Clear the admin session cookie."""
    response.delete_cookie(key="admin_session", path="/")
    logger.info("Admin session logged out")
    return {"status": "ok", "authenticated": False}


@auth_router.get("/status")
async def admin_status(request: Request):
    """Check whether the current request is authenticated as administrator."""
    # Check header
    header_key = request.headers.get(settings.ADMIN_API_KEY_HEADER_NAME)
    if header_key and secrets.compare_digest(header_key, settings.ADMIN_API_KEY):
        return {"authenticated": True, "method": "header"}

    # Check session cookie
    session_cookie = request.cookies.get("admin_session")
    if session_cookie and verify_admin_session_token(session_cookie):
        return {"authenticated": True, "method": "session"}

    return {"authenticated": False}


# 2. Protected Admin Operations Router (Requires valid X-Admin-Key or admin_session cookie)
router = APIRouter(
    prefix="/api/v1/admin",
    tags=["Admin"],
    dependencies=[Depends(verify_admin_key)],
)


class RateLimitResetRequest(BaseModel):
    identifier: str = Field(default="all", description="Target IP/key identifier or 'all' to reset all quotas")


class CircuitBreakerResetRequest(BaseModel):
    service_name: str = Field(default="upstream", description="Service name to reset")


class LoadBalancerConfigRequest(BaseModel):
    server_count: int | None = Field(default=None, ge=1, le=4, description="Active upstream server count (1 to 4)")
    algorithm: str | None = Field(default=None, description="Algorithm: round_robin, least_connections, ip_hash, random")


@router.post("/rate-limit/reset")
async def reset_rate_limit(
    payload: RateLimitResetRequest | None = Body(default=None),
    identifier: str | None = Query(default=None),
    admin: ClientIdentity = Depends(verify_admin_key),
):
    """Reset rate limit counter for a specific IP or API key, or 'all' to reset all quotas (Admin only)."""
    target = identifier or (payload.identifier if payload else "all") or "all"
    redis = await get_redis()

    deleted_count = 0
    if target == "all":
        keys = await redis.keys("rate_limit:*")
        if keys:
            deleted_count = await redis.delete(*keys)
        await redis.set("global_blocks", 0)
    else:
        keys = await redis.keys(f"rate_limit:*:{target}*")
        if not keys:
            keys = [f"rate_limit:{target}", f"rate_limit:free:{target}", f"rate_limit:premium:{target}", f"rate_limit:internal:{target}"]
        if keys:
            deleted_count = await redis.delete(*keys)

    logger.info("Admin reset rate limit", extra={"target": target, "deleted": deleted_count, "admin": admin.api_key})
    return {"status": "ok", "reset": True, "identifier": target, "target": target, "keys_deleted": deleted_count}


@router.post("/circuit-breaker/reset")
async def reset_circuit_breaker(
    payload: CircuitBreakerResetRequest | None = Body(default=None),
    service_name: str | None = Query(default=None),
    admin: ClientIdentity = Depends(verify_admin_key),
):
    """Reset the circuit breaker to CLOSED for a given service (Admin only)."""
    target_svc = service_name or (payload.service_name if payload else "upstream") or "upstream"
    await reset_circuit(target_svc)
    logger.info("Admin reset circuit breaker", extra={"service": target_svc, "admin": admin.api_key})
    return {"status": "ok", "service": target_svc, "circuit": "CLOSED"}


@router.post("/load-balancer/config")
async def configure_load_balancer(
    payload: LoadBalancerConfigRequest,
    admin: ClientIdentity = Depends(verify_admin_key),
):
    """Dynamically configure active server pool count and algorithm (Admin only)."""
    if payload.server_count is not None:
        try:
            load_balancer.set_active_server_count(payload.server_count)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    if payload.algorithm is not None:
        try:
            load_balancer.set_algorithm(payload.algorithm)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    logger.info(
        "Admin updated load balancer configuration",
        extra={
            "admin": admin.api_key,
            "active_server_count": load_balancer.active_server_count,
            "algorithm": load_balancer.algorithm.value,
        },
    )
    return {
        "status": "ok",
        "active_server_count": load_balancer.active_server_count,
        "algorithm": load_balancer.algorithm.value,
    }


@router.post("/load-balancer/reset")
async def reset_load_balancer_telemetry(
    admin: ClientIdentity = Depends(verify_admin_key),
):
    """Reset load balancer telemetry metrics across all upstream servers (Admin only)."""
    load_balancer.reset_telemetry()
    logger.info("Admin reset load balancer telemetry", extra={"admin": admin.api_key})
    return {"status": "ok", "reset": True}
