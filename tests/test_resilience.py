import pytest
import httpx
from services.redis_client import set_redis
from services.rate_limiter import check_rate_limit
from services.circuit_breaker import get_circuit_state, CircuitState


class FailingRedisStub:
    """Mock Redis client that throws network/connection errors on every call."""
    async def eval(self, *args, **kwargs):
        raise ConnectionError("Redis cluster unreachable")

    async def get(self, *args, **kwargs):
        raise TimeoutError("Redis socket read timeout")

    async def set(self, *args, **kwargs):
        raise ConnectionError("Redis host down")

    async def incr(self, *args, **kwargs):
        raise ConnectionError("Redis down")

    async def delete(self, *args, **kwargs):
        raise ConnectionError("Redis down")

    async def expire(self, *args, **kwargs):
        raise ConnectionError("Redis down")

    def pipeline(self, *args, **kwargs):
        raise ConnectionError("Redis pipeline failed")



@pytest.mark.asyncio
async def test_rate_limiter_fails_open_on_redis_outage():
    """Verify that when Redis crashes, the rate limiter fails-open to prevent 500 outages."""
    set_redis(FailingRedisStub())

    # Should allow traffic gracefully rather than raising unhandled exception
    allowed, limit, remaining = await check_rate_limit("192.168.1.1:key", tier="free", client_ip="192.168.1.1")
    assert allowed is True
    assert limit == 60


@pytest.mark.asyncio
async def test_circuit_breaker_fails_open_on_redis_outage():
    """Verify that when Redis crashes, circuit breaker defaults to CLOSED (fail-open)."""
    set_redis(FailingRedisStub())

    state = await get_circuit_state("upstream")
    assert state == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_proxy_route_succeeds_during_redis_outage(client, mock_upstream):
    """Verify end-to-end proxy route continues serving valid traffic when Redis is dead."""
    def upstream_handler(request: httpx.Request):
        return httpx.Response(200, json={"message": "served during Redis outage"})

    mock_upstream(upstream_handler)
    set_redis(FailingRedisStub())

    response = await client.get("/api/v1/resilience-test", headers={"X-API-Key": "free-key-abc123"})
    assert response.status_code == 200
    assert response.json()["message"] == "served during Redis outage"
