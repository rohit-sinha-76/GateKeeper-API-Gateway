from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from core.config import settings
from utils.logger import get_logger
from middleware.tracing import TracingMiddleware
from services.redis_client import close_redis
from routers.monitor import router as monitor_router
from routers.proxy import router as proxy_router

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting GateKeeper API Gateway", extra={"env": settings.ENV})
    yield
    await close_redis()
    logger.info("Shutting down GateKeeper API Gateway")


app = FastAPI(
    title=settings.PROJECT_NAME,
    debug=settings.DEBUG,
    lifespan=lifespan,
)

# Middleware (registered before routes)
app.add_middleware(TracingMiddleware)

# Static files for the dashboard
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/monitor", include_in_schema=False)
async def dashboard():
    return FileResponse("static/index.html")


@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "ok", "version": "1.0.0"}


# CRITICAL: Register monitor router ABOVE the catch-all proxy router
app.include_router(monitor_router)
app.include_router(proxy_router)
