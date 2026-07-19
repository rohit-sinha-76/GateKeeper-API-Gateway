import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_admin_reset_rate_limit(client):
    with patch("routers.admin.get_redis", new_callable=AsyncMock) as mock_redis:
        mock_redis_inst = AsyncMock()
        mock_redis_inst.delete.return_value = 1
        mock_redis.return_value = mock_redis_inst

        response = await client.post("/api/v1/admin/rate-limit/reset?identifier=127.0.0.1:key")
        assert response.status_code == 200
        assert response.json()["reset"] is True


@pytest.mark.asyncio
async def test_admin_reset_circuit_breaker(client):
    with patch("routers.admin.reset_circuit", new_callable=AsyncMock) as mock_reset:
        response = await client.post("/api/v1/admin/circuit-breaker/reset?service_name=upstream")
        assert response.status_code == 200
        assert response.json()["circuit"] == "CLOSED"
