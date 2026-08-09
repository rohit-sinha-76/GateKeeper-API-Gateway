# GateKeeper API Gateway

An asynchronous API gateway with distributed rate limiting, circuit breaking, dynamic multi-server load balancing, and upstream telemetry.

[![CI](https://github.com/rohit-sinha-76/GateKeeper-API-Gateway/actions/workflows/ci.yml/badge.svg)](https://github.com/rohit-sinha-76/GateKeeper-API-Gateway/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110%2B-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Redis](https://img.shields.io/badge/Redis-7-DC382D?logo=redis&logoColor=white)](https://redis.io/)
[![HTTPX](https://img.shields.io/badge/HTTPX-Async%20Pool-000000)](https://www.python-httpx.org/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)
[![Tests](https://img.shields.io/badge/Tests-54%20Passed-brightgreen?logo=pytest&logoColor=white)](https://docs.pytest.org/)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

---

## Overview

GateKeeper is an API gateway positioned as a reverse proxy between incoming client traffic and downstream backend services. It centralizes cross-cutting networking and operational concerns, including request correlation tracing, client identity verification, traffic shaping, downstream failure isolation, dynamic upstream load balancing, and telemetry.

The gateway is built on an asynchronous event loop using FastAPI and HTTPX to process concurrent I/O operations without blocking worker threads. Redis provides distributed state management across worker processes for rate limiting, circuit breaker health states, and global request metrics.

The repository includes a multi-server development simulator (running four distinct upstream backend nodes) and a browser-based monitoring dashboard at `/monitor` that displays live per-server metrics, traffic share, error distributions, and circuit states.

---

## Architecture

```text
Client Request
  │
  ▼
[Tracing & Compression Middleware]   ──► Injects X-Request-ID, X-Process-Time, GZip, Host Validation
  │
  ▼
[FastAPI Gateway Router]
  ├── GET  /health                   ──► Health check endpoint
  ├── GET  /monitor                  ──► Telemetry dashboard UI
  ├── GET  /api/stats                ──► Cluster telemetry & circuit health
  ├── POST /api/v1/admin/*           ──► Privileged management API (Header or Session Cookie)
  └── ANY  /{path}                   ──► Reverse Proxy Pipeline
             │
             ├── [1. Client Authentication]    ──► Constant-time X-API-Key check & tier lookup
             │
             ├── [2. Tiered Rate Limiting]     ──► Redis Lua atomic fixed-window counter (Fail-open)
             │
             ├── [3. Circuit Breaker]          ──► 3-state Redis machine with atomic canary probe lock
             │
             ├── [4. Upstream Load Balancer]   ──► Server snapshot selection (RR / Least-Conn / IP Hash / Random)
             │
             └── [5. Pooled HTTP Forwarder]    ──► Persistent connection pool, in-flight tracking, header hygiene
                    │
                    ├──► Upstream Node 1 (port 8001)
                    ├──► Upstream Node 2 (port 8002)
                    ├──► Upstream Node 3 (port 8003)
                    └──► Upstream Node 4 (port 8004)
```

---

## Key Features

- **Asynchronous HTTP Proxying:** Persistent connection pooling using `httpx.AsyncClient` with configurable connection limits, keep-alive expiry, and RFC 7230 hop-by-hop header hygiene.
- **Dynamic Multi-Server Load Balancing:** Runtime server pool configuration (1 to 4 active nodes) with four selectable routing algorithms: Round Robin, Least Connections, IP Hash, and Random.
- **Request Snapshot Isolation:** In-flight requests capture a point-in-time reference to their chosen upstream node, ensuring zero disruption or state corruption if an administrator resizes the active server pool mid-flight.
- **Distributed Rate Limiting:** Fixed-window rate limiting executed via an atomic Redis Lua script (`INCR` + `EXPIRE`) with tier-based quota allocation (`free`, `premium`, `internal`).
- **Distributed 3-State Circuit Breaker:** Redis-backed state machine (`CLOSED`, `OPEN`, `HALF_OPEN`) with single-probe canary concurrency protection (`SET NX`) to prevent downstream thundering-herd effects during recovery.
- **Dual-Path Admin Security:** Administrative operations support both programmatic `X-Admin-Key` headers (for CLI/CI) and server-issued `HttpOnly`, `SameSite=Lax` HMAC-SHA256 session cookies for browser dashboard interactions, with zero credentials exposed in static assets.
- **Per-Server Telemetry & Dashboard:** Live metrics tracking total requests, accepted (2xx), client errors (4xx), upstream failures (5xx), timeouts, connection errors, active in-flight requests, and average response latency.
- **Resilient Fail-Open Strategy:** Gracefully falls open during Redis partitions or outages to preserve gateway availability.

---

## Request Lifecycle

1. **Ingress Middleware:** Generates a unique UUID `X-Request-ID` (or preserves incoming correlation headers) and records the initial monotonic start time.
2. **Authentication:** Validates the `X-API-Key` header using constant-time string comparison (`secrets.compare_digest`) and resolves the client identity and rate limit tier.
3. **Rate Limit Evaluation:** Executes an atomic Redis Lua script to check whether the client quota has been exceeded for the active 60-second window. Returns HTTP 429 if exceeded.
4. **Circuit Breaker Check:** Evaluates upstream service health. If `OPEN`, fast-fails the request with HTTP 503 and a `Retry-After` header. If `HALF_OPEN`, admits exactly one canary probe while shedding concurrent requests.
5. **Server Selection:** Selects an active upstream node according to the configured load balancing algorithm.
6. **Request Forwarding:** Forwards the sanitized HTTP payload over persistent pooled connections, increments in-flight telemetry counters, and captures high-resolution response timing in a strict `try/finally` block.
7. **Response Hygiene:** Filters hop-by-hop and encoding headers, injects `X-Upstream-Server` and `X-Process-Time`, and returns the payload to the client.

---

## Load Balancing Engine

GateKeeper includes a dynamic load balancer supporting four routing strategies across 1 to 4 upstream backend servers:

| Algorithm | Identifier | Routing Behavior |
|---|---|---|
| **Round Robin** | `round_robin` | Sequentially cycles traffic across active upstream nodes ($1 \to 2 \to 3 \to 4 \to 1$). Automatically resets sequence index on pool resize events. |
| **Least Connections** | `least_connections` | Routes incoming requests to the active upstream node with the fewest currently in-flight requests. In-flight counters strictly increment at start and decrement in a `finally` block. |
| **IP Hash** | `ip_hash` | Computes an MD5 integer hash from the client socket IP address to deterministically bind clients to designated upstream servers. |
| **Random** | `random` | Uniform stochastic distribution across currently active upstream nodes. |

### Dynamic Pool Scaling & Snapshot Isolation

Administrators can adjust the active pool count (1–4) and routing algorithm at runtime via the dashboard or admin REST API without restarting the gateway. In-flight requests hold a direct reference to their target `UpstreamServer` object and complete cleanly, while new incoming traffic routes exclusively to the newly updated active set.

---

## Distributed Rate Limiting

Rate limiting is enforced on a per-tier basis before requests reach the load balancer or upstream servers:

| Tier | Request Limit | Window | Identification Format |
|---|---|---|---|
| `free` | 60 req/min | 60 seconds | `rate_limit:free:<identifier>` |
| `premium` | 600 req/min | 60 seconds | `rate_limit:premium:<identifier>` |
| `internal` | 6,000 req/min | 60 seconds | `rate_limit:internal:<identifier>` |

### Atomic Lua Execution

Rate limit counters are incremented atomically using a single Redis Lua script to prevent race conditions during high concurrent traffic bursts:

```lua
local current = redis.call('INCR', KEYS[1])
if current == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return current
```

*Note on Fixed Windows:* Fixed-window counters permit up to 2x configured burst capacity across a 60-second window boundary. This design choice minimizes Redis memory footprint and execution overhead.

---

## Circuit Breaker

The gateway maintains upstream failure isolation using a Redis-backed 3-state machine:

```text
  ┌────────────────────────────────────────────────────────┐
  │                                                        │
  ▼                                                        │
CLOSED ──(5 failures within 30s)──► OPEN (fast-fail 503)   │
  ▲                                      │                 │
  │                               (15s cooldown)           │
  │                                      │                 │
  │                                      ▼                 │
  └────────(Canary Probe Succeeded)── HALF_OPEN ───────────┘
                                         │
                             (Canary Probe Failed)
```

- **Failure Classification:** Upstream HTTP 500, 502, 503, 504 responses, gateway timeouts, and network connection drops count toward the failure threshold.
- **Canary Probe Isolation:** In `HALF_OPEN` state, an atomic Redis key (`SET NX` with 10s TTL) allows exactly one probe request through to test upstream health. Concurrent requests are shed with HTTP 503 until the probe resolves.
- **Scope:** The circuit breaker state is global across the gateway instance.

---

## Admin Security & Authentication

Administrative endpoints (`/api/v1/admin/*`) require administrator authorization through either of two supported methods:

1. **Programmatic Header:** `X-Admin-Key: <your-admin-key>` for CLI, automated scripts, and integration tests.
2. **Server Session Cookie:** `admin_session` cookie containing an HMAC-SHA256 signed timestamp token (`<timestamp>.<signature>`) issued by `POST /api/v1/admin/auth/login`.

The dashboard UI authenticates via an interactive modal that exchanges credentials for an `HttpOnly`, `SameSite=Lax` session cookie. Zero administrator secrets or keys are hardcoded in frontend JavaScript or delivered over static assets.

---

## Observability & Live Dashboard

GateKeeper serves an integrated monitoring dashboard at `/monitor` that polls `/api/stats` at 1-second intervals:

- **Cluster Summary:** Total requests, allowed (2xx), blocked (429), and current circuit breaker state (`CLOSED`, `OPEN`, `HALF_OPEN`).
- **Per-Node Telemetry:** Live traffic share percentage, total requests, accepted (2xx), errors (4xx/5xx/errors), in-flight requests, and average response latency in milliseconds.
- **Live Controls:** Interactive toggles to scale active server count (1–4), change routing algorithms, trigger rate limit bursts, and execute cluster resets.
- **Log Terminal:** Streaming event log displaying upstream routing decisions, status codes, and latency measurements.

---

## Testing

The test suite includes **54 automated tests** covering authentication, rate limiting, circuit breaker transitions, load balancing algorithms, concurrency, dynamic scaling, proxying, and security regression checks.

### Test Execution

```bash
# Run unit and concurrency test suite (uses in-memory fakeredis with Lua engine)
pytest -v

# Run real Redis integration test suite (requires running Redis on localhost:6379)
USE_REAL_REDIS=1 pytest -v
```

On Windows PowerShell:
```powershell
# Unit tests
py -3.10 -m pytest -v

# Real Redis integration tests
$env:USE_REAL_REDIS="1"; py -3.10 -m pytest -v
```

### Test Coverage Summary

- **Authentication (`test_auth.py`):** Missing key rejection (401), invalid key rejection (401), tier identification (`free`, `premium`).
- **Admin Security (`test_admin.py`):** Unauthenticated rejection (403), invalid token rejection (403), rate limit reset, circuit reset, session login/logout lifecycle, and static asset secret scanning.
- **Circuit Breaker (`test_circuit_breaker.py`):** State transitions (`CLOSED` $\to$ `OPEN` $\to$ `HALF_OPEN` $\to$ `CLOSED`), failure threshold tripping, canary failure re-tripping, and 500 error classification.
- **Concurrency & Atomicity (`test_concurrency.py`):** Concurrent rate-limiting atomicity and race-free circuit tripping under parallel load.
- **Load Balancing (`test_load_balancer.py`):** Sequential Round Robin cycling, Least Connections minimum-load routing, IP Hash determinism, Random uniform distribution, dynamic scaling ($1 \to 4 \to 2 \to 3$), in-flight request accounting, telemetry resets, and scale-down mid-flight safety.
- **Proxy Forwarding (`test_proxy.py`):** GET/POST payload preservation, hop-by-hop header stripping, gateway timeout handling (504), and connection error handling (502).
- **Resilience (`test_resilience.py`):** Fail-open rate limiting and circuit breaking during simulated Redis outages.

---

## Running Locally

### Prerequisites

- Python 3.10+
- Redis 7+ (local daemon or Docker)

### 1. Clone & Setup Environment

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
# Start Redis
docker run -d --name gatekeeper-redis -p 6379:6379 redis:7-alpine

# Start mock upstream backend (runs 4 nodes on ports 8001-8004)
python mock_backend.py

# In a separate terminal, start GateKeeper gateway (port 8000)
uvicorn main:app --reload --port 8000
```

### 3. Send Sample Requests

```bash
# Proxied request using Free Tier API key
curl -i http://localhost:8000/api/v1/users -H "X-API-Key: free-key-abc123"

# Proxied request using Premium Tier API key
curl -i http://localhost:8000/api/v1/users -H "X-API-Key: premium-key-xyz789"

# Open the dashboard in your browser
# http://localhost:8000/monitor
```

---

## Docker & Compose

Run the complete multi-server topology (Gateway, Redis, and 4 Mock Backend nodes) using Docker Compose:

```bash
# Build and start all services
docker compose up --build

# Access the gateway dashboard at http://localhost:8080/monitor
```

### Development Service Topology

```text
[Host: Port 8080]
       │
       ▼
gateway (FastAPI) ───► redis (port 6379)
       │
       ├───► mock_backend (Node 1: port 8001)
       ├───► mock_backend (Node 2: port 8002)
       ├───► mock_backend (Node 3: port 8003)
       └───► mock_backend (Node 4: port 8004)
```

The gateway container uses a two-stage build (`python:3.10-slim`) executing as an unprivileged non-root user (`appuser`, UID 10001) with Docker `HEALTHCHECK` monitoring.

---

## Configuration Reference

All settings can be configured via `.env` or system environment variables:

| Variable | Type | Default | Description |
|---|---|---|---|
| `ENV` | `str` | `development` | Runtime environment (`development`, `production`, `test`) |
| `DEBUG` | `bool` | `false` | Enable debug logging |
| `REDIS_URL` | `str` | `redis://127.0.0.1:6379/0` | Redis connection URL |
| `REDIS_SOCKET_TIMEOUT` | `float` | `0.25` | Redis socket I/O timeout in seconds |
| `REDIS_CONNECT_TIMEOUT` | `float` | `0.25` | Redis connection timeout in seconds |
| `ADMIN_API_KEY` | `str` | `your_secure_admin_key_here` | Secret key for administrator operations |
| `API_KEY_HEADER_NAME` | `str` | `X-API-Key` | Header name for client API key |
| `ADMIN_API_KEY_HEADER_NAME` | `str` | `X-Admin-Key` | Header name for administrator authentication |
| `RATE_LIMIT_WINDOW_SECONDS` | `int` | `60` | Rolling rate limit window duration in seconds |
| `UPSTREAM_SERVER_1_URL` | `str` | `http://127.0.0.1:8001` | Target URL for Upstream Node 1 |
| `UPSTREAM_SERVER_2_URL` | `str` | `http://127.0.0.1:8002` | Target URL for Upstream Node 2 |
| `UPSTREAM_SERVER_3_URL` | `str` | `http://127.0.0.1:8003` | Target URL for Upstream Node 3 |
| `UPSTREAM_SERVER_4_URL` | `str` | `http://127.0.0.1:8004` | Target URL for Upstream Node 4 |
| `DEFAULT_LOAD_BALANCER_ALGORITHM` | `str` | `round_robin` | Default algorithm (`round_robin`, `least_connections`, `ip_hash`, `random`) |
| `DEFAULT_ACTIVE_SERVER_COUNT` | `int` | `4` | Default count of active upstream nodes (1 to 4) |
| `GATEWAY_TIMEOUT_SECONDS` | `float` | `10.0` | Upstream HTTP request timeout in seconds |
| `HTTP_MAX_CONNECTIONS` | `int` | `500` | Max total HTTP connections in pool |
| `HTTP_MAX_KEEPALIVE_CONNECTIONS` | `int` | `100` | Max idle keep-alive HTTP connections |
| `HTTP_KEEPALIVE_EXPIRY_SECONDS` | `float` | `30.0` | Keep-alive connection idle expiry in seconds |
| `CIRCUIT_BREAKER_FAILURE_THRESHOLD` | `int` | `5` | Upstream failures required to trip circuit to `OPEN` |
| `CIRCUIT_BREAKER_RECOVERY_SECONDS` | `int` | `15` | Cooldown period before transitioning to `HALF_OPEN` |
| `CIRCUIT_BREAKER_WINDOW_SECONDS` | `int` | `30` | Failure counter evaluation window in seconds |

---

## Project Structure

```text
GateKeeper-API-Gateway/
├── core/
│   ├── config.py              # Pydantic Settings and environment variable schema
│   ├── exceptions.py          # Custom gateway exceptions and structured error handler
│   └── security.py            # Constant-time API key auth and HMAC session verification
├── middleware/
│   └── tracing.py             # Correlation ID (X-Request-ID) & duration (X-Process-Time)
├── routers/
│   ├── admin.py               # Admin configuration, auth session, and reset endpoints
│   ├── monitor.py             # Dashboard UI route and /api/stats JSON telemetry endpoint
│   └── proxy.py               # Reverse proxy catch-all routing
├── scripts/
│   └── benchmark.py           # In-process loopback load and latency benchmark
├── services/
│   ├── circuit_breaker.py     # 3-state circuit breaker with atomic canary probe lock
│   ├── load_balancer.py       # Multi-server load balancing engine and telemetry tracker
│   ├── proxy.py               # Pooled HTTP forwarding and hop-by-hop header hygiene
│   ├── rate_limiter.py        # Redis Lua atomic fixed-window rate limiter
│   └── redis_client.py        # Redis connection pool lifecycle management
├── static/
│   └── index.html             # Chart.js monitoring dashboard UI
├── tests/
│   ├── conftest.py            # Pytest fixtures for dual-mode fakeredis / real Redis
│   ├── test_admin.py          # Admin authorization and session security tests
│   ├── test_auth.py           # API key validation and tier lookup tests
│   ├── test_circuit_breaker.py# Circuit breaker state transition and failure tests
│   ├── test_concurrency.py    # Atomic concurrency and race condition tests
│   ├── test_exceptions.py     # Gateway exception response format tests
│   ├── test_health.py         # System health endpoint test
│   ├── test_load_balancer.py  # Load balancing algorithms and dynamic scaling tests
│   ├── test_logger.py         # JSON logging format tests
│   ├── test_middleware.py     # Correlation header propagation tests
│   ├── test_monitor.py        # Telemetry metrics and dashboard tests
│   ├── test_proxy.py          # Reverse proxy forwarding, timeout, and error tests
│   ├── test_rate_limit.py     # Tiered Lua rate limit tests
│   └── test_resilience.py     # Redis outage fail-open resilience tests
├── .github/workflows/
│   └── ci.yml                 # GitHub Actions CI workflow with Redis 7 service container
├── .env.example               # Configuration template with safe placeholders
├── .gitignore                 # Version control exclusions
├── docker-compose.yml         # Multi-node compose topology
├── Dockerfile                 # Multi-stage unprivileged non-root container build
├── Makefile                   # Developer task automation
├── pytest.ini                 # Pytest configuration
└── requirements.txt           # Application dependencies
```

---

## Known Limitations

1. **Fixed-Window Rate Limiting:** Fixed-window rate limiting permits up to 2x configured burst capacity across window boundaries.
2. **Global Circuit Breaker:** The circuit breaker tracks downstream health globally for the gateway instance rather than maintaining independent circuit breaker state machines per upstream server.
3. **Payload Buffering:** Request and response bodies are buffered in memory (`request.body()` and `upstream_response.content`). Chunked HTTP streaming for large multi-gigabyte files is not supported.
4. **IP Hash Affinity on Pool Resize:** When the active server count is reconfigured (e.g. from 4 nodes down to 2 nodes), the hash modulo changes and client session affinity shifts across the remaining nodes.

---

## Future Improvements

- Per-upstream circuit breaker instances to isolate individual failing nodes within a healthy pool.
- Consistent hashing ring to minimize client reassignment during dynamic server pool resize events.
- Streaming proxy support using `httpx.stream()` for memory-efficient handling of large payloads.
- Background health checks with automatic node eviction and re-admission.

---

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
