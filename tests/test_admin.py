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


@pytest.mark.asyncio
async def test_admin_session_login_and_cookie_auth(client):
    """
    Verify admin can log in via POST /api/v1/admin/auth/login to receive an HttpOnly cookie,
    and perform admin operations using that session cookie without sending the key in headers.
    """
    # 1. Invalid login fails with 401
    bad_login = await client.post("/api/v1/admin/auth/login", json={"admin_key": "wrong-key"})
    assert bad_login.status_code == 401

    # 2. Valid login succeeds and sets admin_session cookie
    login_res = await client.post("/api/v1/admin/auth/login", json={"admin_key": settings.ADMIN_API_KEY})
    assert login_res.status_code == 200
    assert login_res.json()["authenticated"] is True
    assert "admin_session" in login_res.cookies

    # 3. Check status is authenticated
    status_res = await client.get("/api/v1/admin/auth/status")
    assert status_res.status_code == 200
    assert status_res.json()["authenticated"] is True

    # 4. Perform protected admin operation using cookie only (no X-Admin-Key header!)
    admin_op = await client.post("/api/v1/admin/load-balancer/config", json={"server_count": 3})
    assert admin_op.status_code == 200
    assert admin_op.json()["active_server_count"] == 3

    # Reset back to 4
    await client.post("/api/v1/admin/load-balancer/config", json={"server_count": 4})

    # 5. Logout clears session
    logout_res = await client.post("/api/v1/admin/auth/logout")
    assert logout_res.status_code == 200

    # 6. Admin operation fails after logout
    post_logout_op = await client.post("/api/v1/admin/load-balancer/config", json={"server_count": 2})
    assert post_logout_op.status_code == 403


def test_static_dashboard_contains_no_secrets():
    """
    Security Regression Test:
    Verify that static/index.html contains zero instances of the actual ADMIN_API_KEY.
    The browser must never receive the server secret in static source files.
    """
    import os
    index_path = os.path.join(os.path.dirname(__file__), "..", "static", "index.html")
    with open(index_path, "r", encoding="utf-8") as f:
        content = f.read()

    # The actual secret must NOT appear anywhere in static HTML/JS
    assert settings.ADMIN_API_KEY not in content
    assert "admin-secret" not in content.lower()


