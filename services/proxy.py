import httpx
from fastapi import Request, Response
from core.config import settings
from utils.logger import get_logger
from services.circuit_breaker import (
    CircuitState,
    get_circuit_state,
    acquire_half_open_probe,
    record_failure,
    record_success,
)

logger = get_logger(__name__)

# Shared global HTTP client pool for the gateway
_http_client: httpx.AsyncClient | None = None

# RFC 7230 Hop-by-hop headers that must NOT be forwarded by a proxy
HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "host",
    "content-length",
}



def get_http_client() -> httpx.AsyncClient:
    """Return the shared pooled HTTP client instance."""
    global _http_client
    if _http_client is None or _http_client.is_closed:
        limits = httpx.Limits(
            max_keepalive_connections=settings.HTTP_MAX_KEEPALIVE_CONNECTIONS,
            max_connections=settings.HTTP_MAX_CONNECTIONS,
            keepalive_expiry=settings.HTTP_KEEPALIVE_EXPIRY_SECONDS,
        )
        timeout = httpx.Timeout(settings.GATEWAY_TIMEOUT_SECONDS)
        _http_client = httpx.AsyncClient(limits=limits, timeout=timeout)
    return _http_client


def set_http_client(client: httpx.AsyncClient | None) -> None:
    """Explicitly set or override the HTTP client (useful for test fixtures / mock transports)."""
    global _http_client
    _http_client = client


async def close_http_client() -> None:
    """Gracefully close the shared connection pool during gateway shutdown."""
    global _http_client
    if _http_client and not _http_client.is_closed:
        await _http_client.aclose()
        _http_client = None


async def forward_request(request: Request) -> Response:
    """
    Forward incoming HTTP request to upstream service via persistent connection pool,
    enforcing circuit breaker state machine and hop-by-hop header hygiene.
    """
    path = request.url.path
    query = request.url.query
    upstream_url = f"{settings.UPSTREAM_URL}{path}"
    if query:
        upstream_url = f"{upstream_url}?{query}"

    request_id = getattr(request.state, "request_id", "unknown")
    service_name = "upstream"

    # 1. Circuit Breaker Evaluation
    circuit_state = await get_circuit_state(service_name)
    if circuit_state == CircuitState.OPEN:
        logger.warning("Circuit breaker OPEN; fast-failing request", extra={"path": path, "request_id": request_id})
        return Response(
            content='{"detail":"Service Unavailable: Circuit Breaker OPEN"}',
            status_code=503,
            media_type="application/json",
            headers={"X-Circuit-Breaker": "OPEN", "Retry-After": str(settings.CIRCUIT_BREAKER_RECOVERY_SECONDS)},
        )

    if circuit_state == CircuitState.HALF_OPEN:
        # In HALF_OPEN, only 1 concurrent probe request is allowed
        can_probe = await acquire_half_open_probe(service_name)
        if not can_probe:
            logger.warning("Circuit Breaker HALF_OPEN: Probe in flight, shedding load", extra={"request_id": request_id})
            return Response(
                content='{"detail":"Service Unavailable: Downstream recovering, probe in flight"}',
                status_code=503,
                media_type="application/json",
                headers={"X-Circuit-Breaker": "HALF_OPEN"},
            )
        logger.info("Circuit Breaker HALF_OPEN: Canary probe admitted", extra={"request_id": request_id})

    # 2. Prepare Request Headers (Filter hop-by-hop headers)
    headers = {k: v for k, v in request.headers.items() if k.lower() not in HOP_BY_HOP_HEADERS}
    headers["X-Request-ID"] = request_id

    # 3. Read Body & Forward via Pooled Client
    body = await request.body()
    client = get_http_client()

    try:
        upstream_response = await client.request(
            method=request.method,
            url=upstream_url,
            headers=headers,
            content=body,
        )

        # Classify upstream response status (500, 502, 503, 504 count as upstream failures)
        if upstream_response.status_code in (500, 502, 503, 504):
            await record_failure(service_name)
        else:
            await record_success(service_name)


        # Filter hop-by-hop headers from upstream response
        resp_headers = {k: v for k, v in upstream_response.headers.items() if k.lower() not in HOP_BY_HOP_HEADERS}

        logger.info(
            "Proxied request completed",
            extra={"path": path, "status": upstream_response.status_code, "request_id": request_id},
        )
        return Response(
            content=upstream_response.content,
            status_code=upstream_response.status_code,
            headers=resp_headers,
            media_type=upstream_response.headers.get("content-type"),
        )

    except httpx.TimeoutException:
        await record_failure(service_name)
        logger.error("Upstream gateway timeout", extra={"path": path, "request_id": request_id})
        return Response(content='{"detail":"Gateway Timeout"}', status_code=504, media_type="application/json")

    except (httpx.ConnectError, httpx.NetworkError) as e:
        await record_failure(service_name)
        logger.error("Upstream connection error", extra={"path": path, "request_id": request_id, "error": str(e)})
        return Response(content='{"detail":"Bad Gateway"}', status_code=502, media_type="application/json")

