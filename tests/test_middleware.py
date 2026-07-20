import pytest


@pytest.mark.asyncio
async def test_tracing_middleware_adds_headers(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert "X-Request-ID" in response.headers
    assert "X-Process-Time" in response.headers
