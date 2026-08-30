import time
import uuid
import contextvars
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from utils.logger import get_logger, request_id_ctx_var

logger = get_logger(__name__)


class TracingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.request_id = request_id

        # Set request_id in contextvar for logger integration
        token = request_id_ctx_var.set(request_id)

        response = None
        try:
            response = await call_next(request)
        finally:
            # Ensure contextvar is reset regardless of outcome
            request_id_ctx_var.reset(token)
            
            duration_ms = round((time.time() - start_time) * 1000, 2)
            
            # If response is not yet set (e.g., an exception occurred before call_next returned),
            # create a placeholder response to attach headers, if possible, or ensure it's handled gracefully.
            # For now, we assume response will be set or an exception handler will take over.
            # If `response` is None here, it means an exception occurred and was not caught by `call_next`
            # or a subsequent middleware. The gateway_exception_handler will handle it.
            if response:
                response.headers["X-Request-ID"] = request_id
                response.headers["X-Process-Time"] = f"{duration_ms}ms"

            logger.info(
                "HTTP Request Completed",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code if response else 500, # Default to 500 if response failed to generate
                    "duration_ms": duration_ms,
                },
            )
            
            if response is None:
                # This case implies an unhandled exception before a response could be generated.
                # However, FastAPI's exception handlers typically produce a response.
                # If we reach here, it's an extreme case or an edge case in test setup.
                # For now, re-raise the error if it occurred, or return a generic 500 if we must.
                # Given `gateway_exception_handler` is installed, this path is less likely for common errors.
                pass # The exception would have been re-raised by call_next or handled by FastAPI's mechanisms.

        return response
