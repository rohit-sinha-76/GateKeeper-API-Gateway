import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_rate_limit_triggers_429(client):
    """Hit the gateway enough times to trigger the 429 rate limit response."""
    headers = {"X-API-Key": "free-key-abc123"}

    # Mock the rate limiter to simulate limit exceeded
    with patch("routers.proxy.check_rate_limit", new_callable=AsyncMock) as mock_rl:
        mock_rl.return_value = (False, 100, 0)  # (allowed=False, limit=100, remaining=0)
        response = await client.get("/api/v1/users", headers=headers)

    assert response.status_code == 429
    assert "Rate limit exceeded" in response.json()["detail"]
    assert response.headers.get("X-RateLimit-Remaining") == "0"
