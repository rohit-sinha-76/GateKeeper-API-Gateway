import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_missing_api_key_returns_401(client):
    response = await client.get("/api/v1/users")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_invalid_api_key_returns_401(client):
    response = await client.get("/api/v1/users", headers={"X-API-Key": "wrong-key"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_valid_api_key_passes_auth(client):
    # Mock rate limiter to avoid requiring a running Redis instance during tests
    with patch("routers.proxy.check_rate_limit", new_callable=AsyncMock) as mock_rl:
        mock_rl.return_value = (True, 100, 99)
        response = await client.get("/api/v1/users", headers={"X-API-Key": "free-key-abc123"})
    assert response.status_code != 401
