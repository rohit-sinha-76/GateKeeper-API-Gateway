from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from core.config import settings
from core.exceptions import GatewayException, gateway_exception_handler
from utils.logger import get_logger
from middleware.tracing import TracingMiddleware
from services.redis_client import close_redis
from services.proxy import get_http_client, close_http_client
from routers.monitor import router as monitor_router
from routers.admin import router as admin_router, auth_router as admin_auth_router
from routers.proxy import router as proxy_router

logger = get_logger(__name__)



@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing GateKeeper API Gateway connection pools", extra={"env": settings.ENV})
    # Warm up shared connection pools
    get_http_client()
    yield
    # Graceful shutdown of persistent connection pools
    await close_http_client()
    await close_redis()
    logger.info("GateKeeper API Gateway shut down successfully")


app = FastAPI(
    title=settings.PROJECT_NAME,
    debug=settings.DEBUG,
    lifespan=lifespan,
)

app.add_exception_handler(GatewayException, gateway_exception_handler)

# Middleware Pipeline
app.add_middleware(TracingMiddleware)
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.ALLOWED_HOSTS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"],
    allow_headers=["*"],
)

# Static files for the dashboard
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/monitor", include_in_schema=False)
async def dashboard():
    return FileResponse("static/index.html")


@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "ok", "version": "1.0.0", "project": settings.PROJECT_NAME}


app.include_router(monitor_router)
app.include_router(admin_auth_router)
app.include_router(admin_router)
app.include_router(proxy_router)
