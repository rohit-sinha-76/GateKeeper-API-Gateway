import asyncio
import pytest
from services.rate_limiter import check_rate_limit
from services.circuit_breaker import record_failure, get_circuit_state, CircuitState
from core.config import settings


@pytest.mark.asyncio
async def test_concurrent_rate_limit_requests_are_atomic():
    """
    Launch 100 concurrent requests against the same rate limit identifier simultaneously.
    Verify that exactly 60 succeed (free tier quota) and exactly 40 are rejected without race conditions.
    """
    identifier = "concurrent_client_10.0.0.99:key"
    client_ip = "10.0.0.99"
    tier = "free"
    limit = 60
    total_concurrent = 100

    tasks = [
        check_rate_limit(identifier=identifier, tier=tier, client_ip=client_ip)
        for _ in range(total_concurrent)
    ]
    results = await asyncio.gather(*tasks)

    allowed_count = sum(1 for (allowed, _, _) in results if allowed is True)
    blocked_count = sum(1 for (allowed, _, _) in results if allowed is False)

    assert allowed_count == limit, f"Expected exactly {limit} allowed requests, got {allowed_count}"
    assert blocked_count == (total_concurrent - limit), f"Expected exactly {total_concurrent - limit} blocked requests, got {blocked_count}"


@pytest.mark.asyncio
async def test_concurrent_failures_trip_circuit_safely():
    """
    Launch 20 concurrent failing requests. Verify circuit breaker trips to OPEN safely
    without corrupted state or deadlocks.
    """
    svc = "concurrent_fail_svc"
    tasks = [record_failure(svc) for _ in range(20)]
    results = await asyncio.gather(*tasks)

    final_state = await get_circuit_state(svc)
    assert final_state == CircuitState.OPEN
    assert CircuitState.OPEN in results
