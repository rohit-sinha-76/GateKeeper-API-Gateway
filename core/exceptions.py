from fastapi import Request
from fastapi.responses import JSONResponse


class GatewayException(Exception):
    def __init__(self, message: str, status_code: int = 500):
        self.message = message
        self.status_code = status_code


async def gateway_exception_handler(request: Request, exc: GatewayException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.message, "request_id": getattr(request.state, "request_id", "unknown")},
    )
