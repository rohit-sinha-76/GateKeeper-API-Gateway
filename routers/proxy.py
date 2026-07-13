from fastapi import APIRouter, Request, Depends, Response, HTTPException
from core.config import settings
from core.security import verify_api_key
from services.rate_limiter import check_rate_limit
from services.proxy import forward_request

router = APIRouter()


@router.api_route("/{full_path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def proxy(full_path: str, request: Request, tier: str = Depends(verify_api_key)):
    """Catch-all proxy: authenticate, rate-limit, then forward."""
    # Build identifier from IP + API key header
    client_ip = request.client.host if request.client else "unknown"
    api_key = request.headers.get(settings.API_KEY_HEADER_NAME, "unknown")
    identifier = f"{client_ip}:{api_key}"

    allowed, limit, remaining = await check_rate_limit(identifier)

    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Try again later.",
            headers={
                "X-RateLimit-Limit": str(limit),
                "X-RateLimit-Remaining": "0",
            },
        )

    response = await forward_request(request)
    response.headers["X-RateLimit-Limit"] = str(limit)
    response.headers["X-RateLimit-Remaining"] = str(remaining)
    return response
