import pytest
import httpx


@pytest.mark.asyncio
async def test_missing_api_key_returns_401(client):
    """Verify that requests missing X-API-Key return 401 with standard WWW-Authenticate header."""
    response = await client.get("/api/v1/users")
    assert response.status_code == 401
    assert "Missing required API key header" in response.json()["detail"]
    assert response.headers.get("WWW-Authenticate") == "X-API-Key"


@pytest.mark.asyncio
async def test_invalid_api_key_returns_401(client):
    """Verify that forged/unknown API keys are rejected with 401."""
    response = await client.get("/api/v1/users", headers={"X-API-Key": "unregistered-fake-key"})
    assert response.status_code == 401
    assert "Invalid API key provided" in response.json()["detail"]


@pytest.mark.asyncio
async def test_valid_free_api_key_passes_auth(client, mock_upstream):
    """Verify valid free tier key passes auth and attaches free tier rate-limit headers."""
    def upstream_handler(request: httpx.Request):
        return httpx.Response(200, json={"status": "upstream_ok"})

    mock_upstream(upstream_handler)
    response = await client.get("/api/v1/users", headers={"X-API-Key": "free-key-abc123"})
    assert response.status_code == 200
    assert response.headers.get("X-RateLimit-Tier") == "free"
    assert response.headers.get("X-RateLimit-Limit") == "60"


@pytest.mark.asyncio
async def test_valid_premium_api_key_passes_auth(client, mock_upstream):
    """Verify valid premium tier key passes auth and attaches premium tier rate-limit headers."""
    def upstream_handler(request: httpx.Request):
        return httpx.Response(200, json={"status": "upstream_ok"})

    mock_upstream(upstream_handler)
    response = await client.get("/api/v1/users", headers={"X-API-Key": "premium-key-xyz789"})
    assert response.status_code == 200
    assert response.headers.get("X-RateLimit-Tier") == "premium"
    assert response.headers.get("X-RateLimit-Limit") == "600"

