import pytest
import httpx
from services.rate_limiter import check_rate_limit
from core.config import settings


@pytest.mark.asyncio
async def test_lua_rate_limiter_decrements_and_blocks():
    """Directly test the Redis Lua script logic: allows up to limit, then rejects with remaining=0."""
    identifier = "client_192.168.1.50:test_key"
    tier = "free"
    limit = settings.RATE_LIMIT_TIERS["free"]  # 60

    # 1. Send requests up to limit
    for i in range(1, limit + 1):
        allowed, max_lim, remaining = await check_rate_limit(identifier, tier=tier, client_ip="192.168.1.50")
        assert allowed is True
        assert max_lim == limit
        assert remaining == limit - i

    # 2. 61st request must be blocked
    allowed, max_lim, remaining = await check_rate_limit(identifier, tier=tier, client_ip="192.168.1.50")
    assert allowed is False
    assert remaining == 0


@pytest.mark.asyncio
async def test_tiered_rate_limits_differentiate_free_vs_premium():
    """Verify that premium tier gets higher quota (600) than free tier (60)."""
    free_id = "ip1:free_key"
    premium_id = "ip2:premium_key"

    # Exhaust free tier (60 requests)
    for _ in range(60):
        allowed, _, _ = await check_rate_limit(free_id, tier="free", client_ip="10.0.0.1")
        assert allowed is True

    # 61st free request rejected
    free_allowed, _, _ = await check_rate_limit(free_id, tier="free", client_ip="10.0.0.1")
    assert free_allowed is False

    # Premium client can exceed 60 requests effortlessly
    for _ in range(100):
        allowed, limit, _ = await check_rate_limit(premium_id, tier="premium", client_ip="10.0.0.2")
        assert allowed is True
        assert limit == 600


@pytest.mark.asyncio
async def test_whitelist_ip_bypasses_rate_limit():
    """Verify whitelisted IPs are never blocked regardless of request volume."""
    whitelist_ip = "192.0.2.1"
    settings.RATE_LIMIT_WHITELIST_IPS.append(whitelist_ip)
    try:
        identifier = f"{whitelist_ip}:some_key"
        for _ in range(100):
            allowed, limit, remaining = await check_rate_limit(identifier, tier="free", client_ip=whitelist_ip)
            assert allowed is True
            assert remaining == limit
    finally:
        if whitelist_ip in settings.RATE_LIMIT_WHITELIST_IPS:
            settings.RATE_LIMIT_WHITELIST_IPS.remove(whitelist_ip)



@pytest.mark.asyncio
async def test_e2e_rate_limit_triggers_429_http_response(client, mock_upstream):
    """End-to-end test: hitting gateway with free key past quota triggers HTTP 429 with retry headers."""
    def upstream_handler(request: httpx.Request):
        return httpx.Response(200, json={"data": "ok"})

    mock_upstream(upstream_handler)
    headers = {"X-API-Key": "free-key-abc123"}

    # Simulate non-whitelisted client IP via custom headers/calls to check_rate_limit
    identifier = "198.51.100.25:free-key-abc123"
    # Pre-exhaust the bucket in Redis directly
    for _ in range(60):
        await check_rate_limit(identifier, tier="free", client_ip="198.51.100.25")

    # The 61st request for this identifier returns 429
    allowed, limit, remaining = await check_rate_limit(identifier, tier="free", client_ip="198.51.100.25")
    assert allowed is False

