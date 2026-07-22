import pytest


@pytest.mark.asyncio
async def test_monitor_dashboard_html_served(client):
    """Verify that GET /monitor serves the dashboard static HTML."""
    response = await client.get("/monitor")
    assert response.status_code == 200
    assert "GateKeeper" in response.text
    assert "Chart.js" in response.text or "chart.js" in response.text


@pytest.mark.asyncio
async def test_monitor_api_stats_returns_telemetry(client):
    """Verify GET /api/stats returns accurate hit, block, and circuit breaker metrics."""
    response = await client.get("/api/stats")
    assert response.status_code == 200
    data = response.json()
    assert "total_hits" in data
    assert "total_blocks" in data
    assert "allowed" in data
    assert "circuit_breaker" in data
    assert data["circuit_breaker"] in ("CLOSED", "OPEN", "HALF_OPEN")
