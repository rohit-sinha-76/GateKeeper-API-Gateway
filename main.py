from contextlib import asynccontextmanager
from fastapi import FastAPI

from core.config import settings
from utils.logger import get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "Starting GateKeeper API Gateway",
        extra={"env": settings.ENV, "debug": settings.DEBUG},
    )
    yield
    logger.info("Shutting down GateKeeper API Gateway")


app = FastAPI(
    title=settings.PROJECT_NAME,
    debug=settings.DEBUG,
    lifespan=lifespan,
)


@app.get("/health", tags=["Health"])
async def health_check():
    return {
        "status": "healthy",
        "project": settings.PROJECT_NAME,
        "environment": settings.ENV,
    }
