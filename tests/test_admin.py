import pytest
from core.config import settings


@pytest.mark.asyncio
async def test_admin_endpoints_reject_unauthenticated(client):
    """Verify that unauthenticated access to admin endpoints returns 403 Forbidden."""
    res1 = await client.post("/api/v1/admin/rate-limit/reset?identifier=test_id")
    assert res1.status_code == 403

    res2 = await client.post("/api/v1/admin/circuit-breaker/reset?service_name=upstream")
    assert res2.status_code == 403


@pytest.mark.asyncio
async def test_admin_endpoints_reject_invalid_token(client):
    """Verify that invalid admin credentials are rejected with 403."""
    response = await client.post(
        "/api/v1/admin/rate-limit/reset?identifier=test_id",
        headers={settings.ADMIN_API_KEY_HEADER_NAME: "wrong-admin-token"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_reset_rate_limit_authenticated(client):
    """Verify admin can reset rate limit with valid X-Admin-Key against real Redis."""
    headers = {settings.ADMIN_API_KEY_HEADER_NAME: settings.ADMIN_API_KEY}
    response = await client.post(
        "/api/v1/admin/rate-limit/reset?identifier=127.0.0.1:key",
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["identifier"] == "127.0.0.1:key"


@pytest.mark.asyncio
async def test_admin_reset_circuit_breaker_authenticated(client):
    """Verify admin can reset circuit breaker with valid X-Admin-Key."""
    headers = {settings.ADMIN_API_KEY_HEADER_NAME: settings.ADMIN_API_KEY}
    response = await client.post(
        "/api/v1/admin/circuit-breaker/reset?service_name=upstream",
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["circuit"] == "CLOSED"

