from fastapi import APIRouter, Request, Depends, HTTPException, status
from core.config import settings
from core.security import verify_api_key, ClientIdentity
from services.rate_limiter import check_rate_limit
from services.proxy import forward_request

router = APIRouter()


@router.api_route("/{full_path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
async def proxy(full_path: str, request: Request, identity: ClientIdentity = Depends(verify_api_key)):
    """Catch-all reverse proxy: Authenticate identity, enforce tiered rate limit, then forward upstream."""
    client_ip = request.client.host if request.client else "127.0.0.1"
    identifier = f"{client_ip}:{identity.api_key}"

    allowed, limit, remaining = await check_rate_limit(
        identifier=identifier,
        tier=identity.tier,
        client_ip=client_ip,
    )

    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded for tier '{identity.tier}'. Try again later.",
            headers={
                "X-RateLimit-Limit": str(limit),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Tier": identity.tier,
                "Retry-After": str(settings.RATE_LIMIT_WINDOW_SECONDS),
            },
        )

    response = await forward_request(request)
    response.headers["X-RateLimit-Limit"] = str(limit)
    response.headers["X-RateLimit-Remaining"] = str(remaining)
    response.headers["X-RateLimit-Tier"] = identity.tier
    return response

