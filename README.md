# GateKeeper API Gateway

A **production-grade asynchronous API gateway** built with FastAPI, Redis, and httpx.

## Features

| Feature | Detail |
|---|---|
| API Key Auth | `X-API-Key` header with tiered access (free/premium) |
| Rate Limiting | Fixed-window algorithm using **atomic Redis Lua Scripts** (prevents race conditions) |
| Request Tracing | Every request gets a unique `X-Request-ID` (Correlation ID) & `X-Process-Time` |
| Circuit Breaker | Automatic downstream failure tracking & circuit state protection |
| Admin Control | Endpoints to reset rate limits and circuit breaker states |
| Live Dashboard | Futuristic Chart.js monitoring UI at `/monitor` |
| Docker Ready | Multi-stage Dockerfile & `docker-compose.yml` setup |

## Architecture

```
Client → [TracingMiddleware] → [CORS & Security] → [Auth (X-API-Key)] → [Circuit Breaker Check] → [Rate Limiter] → [Proxy → Upstream]
                                                                                                                        ↓
                                                                                                               [Monitor Dashboard]
```

## Quick Start

### Local (without Docker)
```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Start Redis
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
| `POST /api/v1/admin/rate-limit/reset` | Reset rate limit counter for an IP/Key |
| `POST /api/v1/admin/circuit-breaker/reset` | Reset circuit breaker for downstream |
| `ANY /{path}` | Proxied to upstream service |

## API Key Authentication
Pass your key via the `X-API-Key` header:
```bash
curl http://localhost:8000/api/v1/users -H "X-API-Key: free-key-abc123"
```

Available keys for testing:
- `free-key-abc123` → free tier (100 req/min)
- `premium-key-xyz789` → premium tier

## Running Tests
```bash
pytest -v
```
