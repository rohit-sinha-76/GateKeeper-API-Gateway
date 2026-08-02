# GateKeeper API Gateway

A lightweight asynchronous API gateway built with FastAPI, Redis, and HTTPX, providing API-key authentication, tiered rate limiting, circuit breaking, and reverse request proxying.

---

## Overview

GateKeeper acts as a reverse proxy layer positioned between external clients and downstream microservices. It centralizes cross-cutting networking and security concerns, including request correlation tracing, client authentication, traffic shaping, downstream failure isolation, and real-time observability.

The gateway is built on an asynchronous event loop using FastAPI and HTTPX to handle concurrent I/O operations without blocking the thread pool. Redis is utilized for distributed state management across gateway worker processes.

---

## Architecture

```text
Client Request
  |
  v
[Tracing & Compression Middleware] (X-Request-ID, X-Process-Time, GZip)
  |
  v
[FastAPI Router]
  +--> GET /health                     -> Healthcheck
  +--> GET /monitor                    -> Static telemetry dashboard
  +--> GET /api/stats                  -> Live Redis traffic metrics
  +--> POST /api/v1/admin/*            -> Admin control (X-Admin-Key required)
  +--> ANY /{path}                     -> Reverse proxy route
         |
         +--> [Authentication]        -> Constant-time X-API-Key check & tier lookup
         |
         +--> [Tiered Rate Limiter]   -> Redis Lua fixed-window counter (Fail-open)
         |
         +--> [Circuit Breaker]       -> Redis state machine (CLOSED/OPEN/HALF-OPEN)
         |
         +--> [Pooled HTTP Client]    -> Persistent httpx.AsyncClient connection pool
                 |
                 v
             Upstream Service (e.g., http://localhost:8001)
```

---

## Features

- **API-Key Authentication:** Constant-time (`secrets.compare_digest`) verification with identity and tier extraction (`free`, `premium`, `internal`).
- **Tiered Distributed Rate Limiting:** Fixed-window rate limiting executed via an atomic Redis Lua script (`INCR` + `EXPIRE`).
- **Distributed 3-State Circuit Breaker:** State machine (`CLOSED`, `OPEN`, `HALF-OPEN`) in Redis with atomic canary probe locking (`SET NX`) to prevent recovery thundering herds.
- **Persistent HTTP Connection Pooling:** Shared `httpx.AsyncClient` lifecycle with connection pool limits (`httpx.Limits`) to enable keep-alive reuse and minimize socket churn.
- **Hop-by-Hop Header Hygiene:** Strips RFC 7230 hop-by-hop headers (`Connection`, `Keep-Alive`, `Proxy-Authenticate`, `Proxy-Authorization`, `TE`, `Trailer`, `Transfer-Encoding`, `Upgrade`) on ingress and egress.
- **Correlation Tracing & Observability:** Injects `X-Request-ID` and `X-Process-Time` headers, produces structured JSON logs, and provides a real-time monitoring dashboard at `/monitor`.
- **Fault-Tolerant Fail-Open Design:** Gracefully falls open if Redis encounters network blips or outages to preserve gateway availability.
- **Administrative Control API:** Dedicated endpoints to inspect and reset rate limits and circuit breaker states, protected by `X-Admin-Key`.
- **Production Containerization:** Two-stage multi-stage `Dockerfile` executing as non-root `appuser` (UID 10001) with Docker `HEALTHCHECK`.

---

## Rate Limiting

GateKeeper enforces tier-based rate limits:

| Tier | Default Limit | Window | Identification Key |
|---|---|---|---|
| `free` | 60 requests | 60 seconds | `rate_limit:<client_ip>:<api_key>` |
| `premium` | 600 requests | 60 seconds | `rate_limit:<client_ip>:<api_key>` |
| `internal` | 6000 requests | 60 seconds | `rate_limit:<client_ip>:<api_key>` |

Rate limiting is evaluated using an atomic Redis Lua script:
```lua
local current = redis.call('INCR', KEYS[1])
if current == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return current
```

GateKeeper uses a fixed-window rate-limiting strategy. Requests near a window boundary can produce a burst across two adjacent windows; this is an intentional characteristic of the selected algorithm to minimize Redis storage and CPU overhead.

---

## Circuit Breaker

The gateway tracks downstream availability per service:

```text
CLOSED
  |
  | failure threshold reached (5 failures in 60s)
  v
OPEN (fast-fails incoming traffic with HTTP 503 for 15s)
  |
  | cooldown period elapses
  v
HALF_OPEN
  |
  +-- Canary probe succeeds --> CLOSED (counters reset)
  |
  +-- Canary probe fails -----> OPEN (fresh cooldown initiated)
```

In `HALF_OPEN` state, an atomic Redis lock (`SET NX` with 10s TTL) admits exactly one canary request to test upstream recovery. All concurrent requests arriving during the probe are rejected with HTTP 503 to eliminate downstream thundering-herd traffic.

Upstream HTTP 500, 502, 503, and 504 status codes, along with connection errors and gateway timeouts, are classified as failures by the circuit breaker.

---

## Dynamic Multi-Server Load Balancing

GateKeeper includes a pluggable, dynamic upstream load balancing engine supporting 1 to 4 upstream backend servers with request snapshot isolation and live per-server telemetry accounting.

### Supported Algorithms

1. **Round Robin (`round_robin`):** Distributes incoming requests sequentially across all active upstream servers ($1 \to 2 \to 3 \to 4 \to 1$).
2. **Least Connections (`least_connections`):** Selects the active server with the lowest count of currently in-flight requests. In-flight counters increment upon request dispatch and strictly decrement in a `finally` block across all outcomes (success, 4xx, 5xx, timeout, connect error).
3. **IP Hash (`ip_hash`):** Deterministically hashes client IP addresses to pin specific clients to designated upstream servers for session affinity.
4. **Random (`random`):** Uniform stochastic distribution across currently active upstream servers.

### Request Snapshot Isolation

When a request begins execution, it captures a point-in-time snapshot of the selected upstream server. If an administrator dynamically reconfigures the active server count (e.g. from 4 servers to 2 servers) while requests are in-flight, in-flight requests continue executing against their chosen server to completion without being terminated or rerouted mid-stream.

### Admin Configuration API

Administrators can dynamically reconfigure the upstream pool and algorithm at runtime via authenticated endpoints:

```bash
# Update server count and algorithm dynamically
curl -X POST http://localhost:8080/api/v1/admin/load-balancer/config \
  -H "X-Admin-Key: admin-secret-gatekeeper-key" \
  -H "Content-Type: application/json" \
  -d '{"server_count": 2, "algorithm": "least_connections"}'

# Reset cumulative per-server telemetry metrics
curl -X POST http://localhost:8080/api/v1/admin/load-balancer/reset \
  -H "X-Admin-Key: admin-secret-gatekeeper-key"
```

---

## Reliability & Failure Modes

During Redis outages or partitions:
- The rate limiter logs an operational alert and fails open, permitting traffic to proceed.
- The circuit breaker defaults to `CLOSED`, allowing direct communication with upstream services.
- Trade-off: During Redis outages, GateKeeper prioritizes upstream availability over strict quota enforcement.

During upstream service outages:
- Connection drops return HTTP 502 Bad Gateway.
- Request timeouts return HTTP 504 Gateway Timeout.
- Open circuit states return HTTP 503 Service Unavailable with `Retry-After` headers.

---

## Testing

The test suite supports dual-mode execution:
1. **Unit & Concurrency Mode (Default):** Uses `fakeredis` (with embedded Lua engine `lupa`) and `httpx.MockTransport` for deterministic, zero-dependency testing.
2. **Real Redis Integration Mode:** When `USE_REAL_REDIS=1` is set, all Redis operations and Lua scripts execute against a live Redis server.

### Running Tests

```bash
# Default unit and concurrency suite (fakeredis backend)
pytest -v

# Real Redis integration suite (against localhost:6379)
USE_REAL_REDIS=1 pytest -v
```

On Windows PowerShell:
```powershell
$env:USE_REAL_REDIS="1"; py -3.10 -m pytest -v
```

The test suite contains 50 automated tests covering:
- Constant-time authentication and tier resolution
- Admin authorization and reset operations
- Atomic Redis Lua rate limiting and boundary conditions
- 3-State circuit breaker transitions and canary probe isolation
- Upstream 500/502/504 failure handling and timeout classification
- Round Robin, Least Connections, IP Hash, and Random load balancing algorithms
- Dynamic scaling ($1 \to 4 \to 2 \to 3$) and mid-flight reconfiguration safety
- High-concurrency atomicity (100 simultaneous coroutines)
- Redis outage fail-open resilience
- Hop-by-hop header stripping and correlation ID propagation


---

## Performance

An in-process load testing script is included in `scripts/benchmark.py` for development-level comparison:

```bash
python scripts/benchmark.py
```

*Note on Benchmarks:* The benchmark measures in-process loopback throughput via ASGI transport (~250–400 req/sec on a single ASGI worker). It does not represent wire-level TCP performance, which depends on deployment hardware, network interface capacity, and workload characteristics.

---

## Running Locally

### Prerequisites
- Python 3.10+
- Redis 7+ (local service or Docker)

### 1. Setup Environment
```bash
git clone https://github.com/rohit-sinha-76/GateKeeper-API-Gateway.git
cd GateKeeper-API-Gateway


python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

pip install -r requirements.txt
cp .env.example .env
```

### 2. Start Services
```bash
# Start Redis (or run local daemon)
docker run -d -p 6379:6379 redis:7-alpine

# Start mock upstream backend (port 8001)
python mock_backend.py

# Start GateKeeper gateway (port 8000)
uvicorn main:app --reload --port 8000
```

### 3. Send Requests
```bash
# Normal proxied request (free tier)
curl -i http://localhost:8000/api/v1/users -H "X-API-Key: free-key-abc123"

# Admin reset request
curl -i -X POST http://localhost:8000/api/v1/admin/circuit-breaker/reset \
  -H "X-Admin-Key: admin-secret-gatekeeper-key"
```

---

## Configuration

Environment variables can be set via `.env` or system environment:

| Variable | Description | Default |
|---|---|---|
| `REDIS_URL` | Redis connection URL | `redis://localhost:6379/0` |
| `UPSTREAM_URL` | Downstream service target URL | `http://localhost:8001` |
| `ADMIN_API_KEY` | Secret key required for admin endpoints | `admin-secret-gatekeeper-key` |
| `GATEWAY_TIMEOUT_SECONDS` | HTTP upstream request timeout | `10.0` |
| `CIRCUIT_BREAKER_FAILURE_THRESHOLD` | Failures required to trip circuit | `5` |
| `CIRCUIT_BREAKER_RECOVERY_SECONDS` | Cooldown period before HALF-OPEN | `15.0` |
| `CIRCUIT_BREAKER_WINDOW_SECONDS` | Rolling window for failure counter | `60` |
| `HTTP_MAX_CONNECTIONS` | Max persistent HTTP connections | `500` |
| `HTTP_MAX_KEEPALIVE_CONNECTIONS` | Max keep-alive idle connections | `100` |

---

## Docker & Compose

### Build and Run with Docker Compose
```bash
docker compose up --build
```

### Standalone Docker Build
```bash
docker build -t gatekeeper-api-gateway .
docker run -p 8000:8000 -e REDIS_URL=redis://host.docker.internal:6379/0 gatekeeper-api-gateway
```

The container uses a multi-stage build and drops privileges to an unprivileged `appuser` (UID 10001).

---

## CI Pipeline

GitHub Actions CI (`.github/workflows/ci.yml`) executes on every push and pull request against `main`:
- Spins up a `redis:7-alpine` service container with health checks.
- Sets up Python 3.10 and caches dependencies.
- Runs the test suite with `USE_REAL_REDIS: "1"` against the live Redis service container.

---

## Project Structure

```text
GateKeeper-API-Gateway/
├── core/
│   ├── config.py              # Application settings & environment parsing
│   ├── exceptions.py          # Custom gateway exception definitions
│   └── security.py            # Constant-time API key & admin verification
├── middleware/
│   └── tracing.py             # Correlation ID & request duration middleware
├── routers/
│   ├── admin.py               # Authenticated administrative endpoints
│   ├── monitor.py             # Dashboard HTML & JSON telemetry endpoints
│   └── proxy.py               # Reverse proxy catch-all routing
├── scripts/
│   └── benchmark.py           # In-process latency & load benchmark
├── services/
│   ├── circuit_breaker.py     # 3-State circuit breaker & canary probe logic
│   ├── proxy.py               # Pooled HTTP forwarding & header filtering
│   ├── rate_limiter.py        # Redis Lua atomic rate limiting
│   └── redis_client.py        # Redis connection pool management
├── static/
│   └── index.html             # Chart.js telemetry dashboard UI
├── tests/
│   ├── conftest.py            # Dual-mode Redis and mock client fixtures
│   ├── test_admin.py          # Admin authorization test suite
│   ├── test_auth.py           # API key authentication test suite
│   ├── test_circuit_breaker.py# Circuit breaker state transition tests
│   ├── test_concurrency.py    # Atomic concurrency & race condition tests
│   ├── test_exceptions.py     # Gateway exception handler tests
│   ├── test_health.py         # System health endpoint tests
│   ├── test_logger.py         # Structured JSON logging tests
│   ├── test_middleware.py     # Tracing and header propagation tests
│   ├── test_monitor.py        # Telemetry metrics & dashboard tests
│   ├── test_proxy.py          # Proxy forwarding, timeout & error tests
│   ├── test_rate_limit.py     # Tiered Lua rate limit tests
│   └── test_resilience.py     # Redis failure injection & fail-open tests
├── .github/workflows/
│   └── ci.yml                 # Automated CI workflow with Redis service
├── .env.example               # Configuration template
├── .gitignore                 # Tracked file exclusions
├── docker-compose.yml         # Compose configuration
├── Dockerfile                 # Multi-stage non-root container definition
├── Makefile                   # Developer task automation
├── pytest.ini                 # Pytest configuration
├── requirements.txt           # Production & test dependencies
└── README.md                  # Project documentation
```

---

## Limitations

1. **Fixed-Window Rate Limiting:** Fixed-window counting permits up to 2x configured burst capacity across a 60-second window boundary.
2. **Payload Buffering:** Request and response bodies are buffered in memory (`request.body()` and `upstream_response.content`). Chunked HTTP streaming for multi-gigabyte payloads is not supported in the current version.
3. **Single Upstream Target:** The reverse proxy routes traffic to a single configured `UPSTREAM_URL`. Dynamic prefix-based routing tables are not currently implemented.

---

## Future Improvements

- Streaming request and response body support via `httpx.stream()` for large payloads.
- Dynamic multi-service routing table with prefix-based service discovery.
- Sliding-window log or token-bucket rate limiter options for smoother boundary traffic shaping.


