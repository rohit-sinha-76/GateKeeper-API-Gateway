# ⬡ GateKeeper API Gateway

A **production-grade asynchronous API gateway** built with FastAPI, Redis, and httpx.

## Features

| Feature | Detail |
|---|---|
| 🔑 API Key Auth | `X-API-Key` header with tiered access (free/premium) |
| 🚦 Rate Limiting | Fixed-window algorithm using **atomic Redis Pipelines** (prevents race conditions) |
| 🔗 Request Tracing | Every request gets a unique `X-Request-ID` (Correlation ID) for observability |
| ⚡ Async Proxy | Non-blocking request forwarding via `httpx.AsyncClient` |
| 📊 Live Dashboard | Futuristic Chart.js monitoring UI at `/monitor` |
| 🐳 Docker Ready | `docker-compose up` spins up gateway + Redis + mock backend |

## Architecture

```
Client → [TracingMiddleware] → [Auth (X-API-Key)] → [Rate Limiter (Redis)] → [Proxy → Upstream]
                                                                                       ↓
                                                                              [Monitor Dashboard]
```

## Quick Start

### Local (without Docker)
```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Start Redis (requires Docker or a local Redis install)
docker run -p 6379:6379 redis:7-alpine

# 3. Start the mock backend
python mock_backend.py

# 4. Start the gateway
uvicorn main:app --reload --port 8000
```

### With Docker Compose
```bash
docker-compose up --build
```

## Endpoints

| Endpoint | Description |
|---|---|
| `GET /health` | Health check |
| `GET /monitor` | Live monitoring dashboard |
| `GET /api/stats` | Raw traffic stats (JSON) |
| `ANY /{path}` | Proxied to upstream service |

## API Key Authentication
Pass your key via the `X-API-Key` header:
```bash
curl http://localhost:8000/api/v1/users -H "X-API-Key: free-key-abc123"
```

Available keys for testing:
- `free-key-abc123` → free tier (100 req/min)
- `premium-key-xyz789` → premium tier

## Key Design Decisions

**Atomic Rate Limiting:** We use a Redis Pipeline to run `INCR` and `EXPIRE` in the same transaction. This prevents a race condition where two simultaneous requests could both set the counter before the TTL is applied.

**Request Tracing (Correlation ID):** Every request is stamped with an `X-Request-ID` header that flows from the client → gateway → upstream service. This makes debugging distributed systems trivial.

**UPSTREAM_URL via environment variable:** The proxy reads the backend URL from config, not a hardcoded `localhost`. This means the same code works locally and inside Docker with zero changes.

## Running Tests
```bash
pytest -v
```