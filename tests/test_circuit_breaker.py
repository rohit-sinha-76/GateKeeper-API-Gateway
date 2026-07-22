import asyncio
import time
import pytest
import httpx
from services.circuit_breaker import (
    CircuitState,
    get_circuit_state,
    record_failure,
    record_success,
    acquire_half_open_probe,
    reset_circuit,
)
from core.config import settings


@pytest.mark.asyncio
async def test_circuit_breaker_starts_closed():
    """Verify default initial state of circuit breaker is CLOSED."""
    state = await get_circuit_state("test_svc")
    assert state == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_circuit_trips_to_open_after_threshold_failures():
    """Verify that 5 failures trip the circuit state from CLOSED to OPEN."""
    svc = "test_trip_svc"
    for i in range(settings.CIRCUIT_BREAKER_FAILURE_THRESHOLD - 1):
        state = await record_failure(svc)
        assert state == CircuitState.CLOSED

    # 5th failure must trip to OPEN
    state = await record_failure(svc)
    assert state == CircuitState.OPEN
    assert await get_circuit_state(svc) == CircuitState.OPEN


@pytest.mark.asyncio
async def test_circuit_half_open_transition_and_canary_success():
    """Verify state transitions: OPEN -> HALF_OPEN (after cooldown) -> CLOSED (on canary success)."""
    svc = "test_recovery_svc"

    # Trip circuit to OPEN
    for _ in range(settings.CIRCUIT_BREAKER_FAILURE_THRESHOLD):
        await record_failure(svc)
    assert await get_circuit_state(svc) == CircuitState.OPEN

    # Mock time elapsed past recovery duration
    from services.redis_client import get_redis
    redis = await get_redis()
    opened_at_key = f"circuit_breaker:{svc}:opened_at"
    # Set opened_at to 20 seconds in the past (cooldown is 15s)
    await redis.set(opened_at_key, str(time.time() - (settings.CIRCUIT_BREAKER_RECOVERY_SECONDS + 5)))

    # Verify state is now HALF_OPEN
    state = await get_circuit_state(svc)
    assert state == CircuitState.HALF_OPEN

    # Acquire canary probe
    can_probe = await acquire_half_open_probe(svc)
    assert can_probe is True

    # Second concurrent probe attempt must be rejected (thundering herd protection)
    second_probe = await acquire_half_open_probe(svc)
    assert second_probe is False

    # Canary succeeds -> Circuit resets to CLOSED
    await record_success(svc)
    assert await get_circuit_state(svc) == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_canary_failure_immediately_retrips_circuit_to_open():
    """Verify that if a canary probe fails during HALF_OPEN, the circuit immediately reverts to OPEN."""
    svc = "test_canary_fail_svc"

    # Force into HALF_OPEN
    from services.redis_client import get_redis
    redis = await get_redis()
    await redis.set(f"circuit_breaker:{svc}:state", CircuitState.OPEN.value)
    await redis.set(f"circuit_breaker:{svc}:opened_at", str(time.time() - 20))

    assert await get_circuit_state(svc) == CircuitState.HALF_OPEN

    # Canary fails
    state = await record_failure(svc)
    assert state == CircuitState.OPEN


@pytest.mark.asyncio
async def test_e2e_proxy_circuit_breaker_blocks_when_open(client, mock_upstream):
    """Verify gateway returns 503 with X-Circuit-Breaker: OPEN header when downstream circuit is open."""
    # Force trip upstream circuit
    for _ in range(settings.CIRCUIT_BREAKER_FAILURE_THRESHOLD):
        await record_failure("upstream")

    response = await client.get("/api/v1/users", headers={"X-API-Key": "free-key-abc123"})
    assert response.status_code == 503
    assert response.headers.get("X-Circuit-Breaker") == "OPEN"
    assert "Circuit Breaker OPEN" in response.json()["detail"]


@pytest.mark.asyncio
async def test_upstream_500_errors_trip_circuit_breaker(client, mock_upstream):
    """Verify that repeated upstream 500 Internal Server Errors are classified as failures and trip the circuit."""
    def error_500_handler(request: httpx.Request):
        return httpx.Response(500, json={"error": "Internal database crash"})

    mock_upstream(error_500_handler)
    headers = {"X-API-Key": "free-key-abc123"}

    # Send 5 requests returning 500
    for _ in range(settings.CIRCUIT_BREAKER_FAILURE_THRESHOLD):
        res = await client.get("/api/v1/flaky", headers=headers)
        assert res.status_code == 500

    # 6th request must be blocked by the Circuit Breaker with 503
    blocked_res = await client.get("/api/v1/flaky", headers=headers)
    assert blocked_res.status_code == 503
    assert blocked_res.headers.get("X-Circuit-Breaker") == "OPEN"

