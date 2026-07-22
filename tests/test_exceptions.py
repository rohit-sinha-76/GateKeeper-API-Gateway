import pytest
from fastapi import Request
from core.exceptions import GatewayException, gateway_exception_handler


@pytest.mark.asyncio
async def test_gateway_exception_handler_formats_json():
    """Verify GatewayException handler returns structured JSON with request_id."""
    class DummyState:
        request_id = "test-req-123"

    class DummyRequest:
        state = DummyState()

    exc = GatewayException(message="Custom Gateway Failure", status_code=503)
    response = await gateway_exception_handler(DummyRequest(), exc)

    assert response.status_code == 503
    import json
    data = json.loads(response.body.decode())
    assert data["detail"] == "Custom Gateway Failure"
    assert data["request_id"] == "test-req-123"
