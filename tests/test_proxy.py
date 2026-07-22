import pytest
import httpx


@pytest.mark.asyncio
async def test_proxy_forwards_get_and_preserves_query(client, mock_upstream):
    """Verify reverse proxy forwards GET requests, query parameters, and custom headers."""
    captured_request = None

    def upstream_handler(request: httpx.Request):
        nonlocal captured_request
        captured_request = request
        return httpx.Response(200, json={"items": [1, 2, 3]}, headers={"X-Upstream-Header": "GateKeeper"})

    mock_upstream(upstream_handler)

    response = await client.get(
        "/api/v1/items?limit=10&offset=20",
        headers={"X-API-Key": "free-key-abc123", "Custom-Client-Header": "foobar"},
    )
    assert response.status_code == 200
    assert response.json() == {"items": [1, 2, 3]}
    assert captured_request is not None
    assert captured_request.url.query.decode() == "limit=10&offset=20"
    assert captured_request.headers.get("custom-client-header") == "foobar"
    assert "X-Request-ID" in response.headers
    assert "X-Process-Time" in response.headers


@pytest.mark.asyncio
async def test_proxy_forwards_post_with_body(client, mock_upstream):
    """Verify reverse proxy forwards POST payload body cleanly."""
    captured_body = None

    def upstream_handler(request: httpx.Request):
        nonlocal captured_body
        captured_body = request.content
        return httpx.Response(201, json={"status": "created"})

    mock_upstream(upstream_handler)

    payload = {"name": "New Resource", "price": 99.9}
    response = await client.post(
        "/api/v1/items",
        json=payload,
        headers={"X-API-Key": "premium-key-xyz789"},
    )
    assert response.status_code == 201
    assert b"New Resource" in captured_body


@pytest.mark.asyncio
async def test_proxy_strips_hop_by_hop_headers(client, mock_upstream):
    """Verify RFC 7230 hop-by-hop headers (Proxy-Authorization, Upgrade, Trailer) are stripped before forwarding."""
    captured_headers = None

    def upstream_handler(request: httpx.Request):
        nonlocal captured_headers
        captured_headers = {k.lower(): v for k, v in request.headers.items()}
        return httpx.Response(200, content="OK", headers={"transfer-encoding": "chunked", "x-custom-hop": "valid"})

    mock_upstream(upstream_handler)

    response = await client.get(
        "/api/v1/check-headers",
        headers={
            "X-API-Key": "free-key-abc123",
            "Proxy-Authorization": "Basic dXNlcjpwYXNz",
            "Upgrade": "websocket",
            "Trailer": "Expires",
        },
    )
    assert response.status_code == 200
    assert "proxy-authorization" not in captured_headers
    assert "upgrade" not in captured_headers
    assert "trailer" not in captured_headers
    assert "transfer-encoding" not in response.headers
    assert response.headers.get("x-custom-hop") == "valid"



@pytest.mark.asyncio
async def test_proxy_handles_upstream_timeout(client, mock_upstream):
    """Verify that upstream network timeouts return 504 Gateway Timeout."""
    def timeout_handler(request: httpx.Request):
        raise httpx.TimeoutException("Upstream timed out")

    mock_upstream(timeout_handler)

    response = await client.get("/api/v1/slow", headers={"X-API-Key": "free-key-abc123"})
    assert response.status_code == 504
    assert "Gateway Timeout" in response.json()["detail"]


@pytest.mark.asyncio
async def test_proxy_handles_upstream_connect_error(client, mock_upstream):
    """Verify that upstream connection refusals return 502 Bad Gateway."""
    def error_handler(request: httpx.Request):
        raise httpx.ConnectError("Connection refused by upstream")

    mock_upstream(error_handler)

    response = await client.get("/api/v1/down", headers={"X-API-Key": "free-key-abc123"})
    assert response.status_code == 502
    assert "Bad Gateway" in response.json()["detail"]
