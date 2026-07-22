import pytest
import pytest_asyncio
import fakeredis.aioredis
import httpx
from main import app
from services.redis_client import set_redis, close_redis
from services.proxy import set_http_client, close_http_client


import os
import redis.asyncio as aioredis
from core.config import settings


@pytest_asyncio.fixture(autouse=True)
async def redis_setup():
    """
    Provide Redis backend for tests:
    - Uses real Redis when USE_REAL_REDIS environment variable is set (e.g. in CI with live Redis).
    - Defaults to in-memory fakeredis with Lua engine for fast, isolated unit testing.
    """
    if os.getenv("USE_REAL_REDIS") == "1":
        real_redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        set_redis(real_redis)
        await real_redis.flushdb()
        yield real_redis
        await real_redis.flushdb()
        await real_redis.aclose()
        set_redis(None)
    else:
        server = fakeredis.FakeServer()
        fake_redis = fakeredis.aioredis.FakeRedis(server=server, decode_responses=True)
        set_redis(fake_redis)
        yield fake_redis
        await fake_redis.flushall()
        await fake_redis.aclose()
        set_redis(None)



@pytest_asyncio.fixture
async def client():
    """ASGI TestClient connected to the FastAPI gateway application."""
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
def mock_upstream():
    """
    Fixture to configure mock upstream HTTP handler responses for proxy testing.
    """
    def _create_mock_client(handler):
        transport = httpx.MockTransport(handler)
        mock_client = httpx.AsyncClient(transport=transport, base_url="http://localhost:8001")
        set_http_client(mock_client)
        return mock_client

    yield _create_mock_client
    set_http_client(None)

