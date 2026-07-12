import httpx
from fastapi import Request, Response
from core.config import settings
from utils.logger import get_logger

logger = get_logger(__name__)


async def forward_request(request: Request) -> Response:
    """Forward the incoming request to the upstream service."""
    path = request.url.path
    query = request.url.query
    upstream_url = f"{settings.UPSTREAM_URL}{path}"
    if query:
        upstream_url = f"{upstream_url}?{query}"

    request_id = getattr(request.state, "request_id", "unknown")
    headers = dict(request.headers)
    headers["X-Request-ID"] = request_id
    # Remove hop-by-hop headers
    for h in ("host", "content-length"):
        headers.pop(h, None)

    body = await request.body()

    try:
        async with httpx.AsyncClient(timeout=settings.GATEWAY_TIMEOUT_SECONDS) as client:
            upstream_response = await client.request(
                method=request.method,
                url=upstream_url,
                headers=headers,
                content=body,
            )
        logger.info("Proxied request", extra={"path": path, "status": upstream_response.status_code, "request_id": request_id})
        return Response(
            content=upstream_response.content,
            status_code=upstream_response.status_code,
            headers=dict(upstream_response.headers),
            media_type=upstream_response.headers.get("content-type"),
        )
    except httpx.TimeoutException:
        logger.error("Upstream timeout", extra={"path": path, "request_id": request_id})
        return Response(content='{"detail":"Gateway Timeout"}', status_code=504, media_type="application/json")
    except httpx.ConnectError:
        logger.error("Upstream connection error", extra={"path": path, "request_id": request_id})
        return Response(content='{"detail":"Bad Gateway"}', status_code=502, media_type="application/json")
