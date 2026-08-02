"""
Comprehensive unit and concurrency tests for GateKeeper Load Balancer service.
Tests Round Robin, Least Connections, IP Hash, Random, dynamic reconfiguration,
error counter cleanup, and telemetry accounting.
"""
import pytest
import asyncio
from services.load_balancer import (
    LoadBalancer,
    UpstreamServer,
    LoadBalancingAlgorithm,
)


@pytest.fixture
def lb():
    servers = [
        UpstreamServer(id="server-1", name="Node 1", url="http://127.0.0.1:8001"),
        UpstreamServer(id="server-2", name="Node 2", url="http://127.0.0.1:8002"),
        UpstreamServer(id="server-3", name="Node 3", url="http://127.0.0.1:8003"),
        UpstreamServer(id="server-4", name="Node 4", url="http://127.0.0.1:8004"),
    ]
    return LoadBalancer(initial_servers=servers)


def test_round_robin_cycles_sequentially(lb):
    """Test Round Robin distributes sequentially: 1 -> 2 -> 3 -> 4 -> 1."""
    lb.set_algorithm(LoadBalancingAlgorithm.ROUND_ROBIN)
    lb.set_active_server_count(4)

    sequence = [lb.select_server().id for _ in range(8)]
    assert sequence == [
        "server-1", "server-2", "server-3", "server-4",
        "server-1", "server-2", "server-3", "server-4",
    ]


def test_round_robin_with_two_servers(lb):
    """Test Round Robin with 2 active servers alternates: 1 -> 2 -> 1 -> 2."""
    lb.set_algorithm(LoadBalancingAlgorithm.ROUND_ROBIN)
    lb.set_active_server_count(2)

    sequence = [lb.select_server().id for _ in range(6)]
    assert sequence == ["server-1", "server-2", "server-1", "server-2", "server-1", "server-2"]


def test_least_connections_selects_minimum_load(lb):
    """Test Least Connections selects the server with the lowest in-flight active requests."""
    lb.set_algorithm(LoadBalancingAlgorithm.LEAST_CONNECTIONS)
    lb.set_active_server_count(3)

    # Artificially set in-flight loads
    servers = lb.servers
    servers[0].active_requests = 5  # server-1
    servers[1].active_requests = 1  # server-2 (lowest)
    servers[2].active_requests = 7  # server-3

    selected = lb.select_server()
    assert selected.id == "server-2"

    # If server-2 receives more load, server-1 becomes lowest
    servers[1].active_requests = 8
    selected2 = lb.select_server()
    assert selected2.id == "server-1"


def test_ip_hash_is_deterministic(lb):
    """Test IP Hash consistently routes the same client IP to the exact same server."""
    lb.set_algorithm(LoadBalancingAlgorithm.IP_HASH)
    lb.set_active_server_count(4)

    client_a = "192.168.1.100"
    client_b = "10.0.0.50"

    target_a = lb.select_server(client_ip=client_a).id
    target_b = lb.select_server(client_ip=client_b).id

    # Repeated calls must map to identical servers
    for _ in range(20):
        assert lb.select_server(client_ip=client_a).id == target_a
        assert lb.select_server(client_ip=client_b).id == target_b


def test_random_selects_only_active_servers(lb):
    """Test Random algorithm selects only currently active servers."""
    lb.set_algorithm(LoadBalancingAlgorithm.RANDOM)
    lb.set_active_server_count(2)  # Only server-1 and server-2 active

    active_ids = {"server-1", "server-2"}
    for _ in range(50):
        selected = lb.select_server()
        assert selected.id in active_ids


def test_dynamic_server_scaling(lb):
    """Test dynamically modifying active server count from 1 -> 4 -> 2 -> 3 without restarts."""
    lb.set_algorithm(LoadBalancingAlgorithm.ROUND_ROBIN)

    # 1 Server
    lb.set_active_server_count(1)
    assert len(lb.get_active_servers()) == 1
    assert lb.select_server().id == "server-1"

    # Scale up to 4
    lb.set_active_server_count(4)
    assert len(lb.get_active_servers()) == 4

    # Scale down to 2
    lb.set_active_server_count(2)
    assert len(lb.get_active_servers()) == 2
    assert {s.id for s in lb.get_active_servers()} == {"server-1", "server-2"}


def test_invalid_configuration_raises_error(lb):
    """Test setting invalid server counts or algorithms raises descriptive ValueErrors."""
    with pytest.raises(ValueError):
        lb.set_active_server_count(0)

    with pytest.raises(ValueError):
        lb.set_active_server_count(5)

    with pytest.raises(ValueError):
        lb.set_algorithm("unsupported_algo")


def test_in_flight_request_accounting_and_cleanup(lb):
    """Verify active_requests increments on start and decrements in finally across all outcomes."""
    server = lb.servers[0]
    assert server.active_requests == 0

    # 1. Success lifecycle
    lb.record_request_start(server)
    assert server.active_requests == 1
    lb.record_request_end(server, status_code=200, duration_ms=15.0)
    assert server.active_requests == 0
    assert server.successful_requests == 1
    assert server.total_requests == 1

    # 2. 500 error lifecycle
    lb.record_request_start(server)
    lb.record_request_end(server, status_code=500, duration_ms=25.0)
    assert server.active_requests == 0
    assert server.upstream_5xx == 1

    # 3. Timeout lifecycle
    lb.record_request_start(server)
    lb.record_request_end(server, is_timeout=True, duration_ms=5000.0)
    assert server.active_requests == 0
    assert server.timeouts == 1

    # 4. Connection error lifecycle
    lb.record_request_start(server)
    lb.record_request_end(server, is_connect_error=True, duration_ms=5.0)
    assert server.active_requests == 0
    assert server.connection_errors == 1


def test_telemetry_reset(lb):
    """Test telemetry reset clears metrics across all servers without altering configuration."""
    lb.set_active_server_count(3)
    lb.set_algorithm(LoadBalancingAlgorithm.LEAST_CONNECTIONS)

    server = lb.servers[0]
    lb.record_request_start(server)
    lb.record_request_end(server, status_code=200, duration_ms=10.0)

    stats_before = lb.get_stats()
    assert stats_before["servers"][0]["total_requests"] == 1

    # Reset
    lb.reset_telemetry()
    stats_after = lb.get_stats()
    assert stats_after["servers"][0]["total_requests"] == 0
    assert stats_after["active_server_count"] == 3
    assert stats_after["algorithm"] == "least_connections"


@pytest.mark.asyncio
async def test_concurrent_round_robin_requests(lb):
    """Test concurrent requests safely cycle through round robin without deadlock or corruption."""
    lb.set_algorithm(LoadBalancingAlgorithm.ROUND_ROBIN)
    lb.set_active_server_count(4)

    selected_ids = []

    async def worker():
        server = lb.select_server()
        lb.record_request_start(server)
        await asyncio.sleep(0.01)
        lb.record_request_end(server, status_code=200, duration_ms=10.0)
        selected_ids.append(server.id)

    tasks = [worker() for _ in range(40)]
    await asyncio.gather(*tasks)

    assert len(selected_ids) == 40
    # Every active server must have processed exactly 10 requests
    for server in lb.servers:
        assert server.total_requests == 10
        assert server.active_requests == 0


@pytest.mark.asyncio
async def test_admin_configure_load_balancer_api(client):
    """Test admin endpoint dynamically updates server count and algorithm."""
    from core.config import settings
    admin_headers = {settings.ADMIN_API_KEY_HEADER_NAME: settings.ADMIN_API_KEY}

    # 1. Reject unauthenticated
    unauth = await client.post("/api/v1/admin/load-balancer/config", json={"server_count": 2})
    assert unauth.status_code == 403

    # 2. Update to 2 servers + least_connections
    res = await client.post(
        "/api/v1/admin/load-balancer/config",
        headers=admin_headers,
        json={"server_count": 2, "algorithm": "least_connections"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["active_server_count"] == 2
    assert data["algorithm"] == "least_connections"

    # 3. Reject invalid configuration
    invalid = await client.post(
        "/api/v1/admin/load-balancer/config",
        headers=admin_headers,
        json={"server_count": 99},
    )
    assert invalid.status_code == 422

    # Reset back to 4 + round_robin
    await client.post(
        "/api/v1/admin/load-balancer/config",
        headers=admin_headers,
        json={"server_count": 4, "algorithm": "round_robin"},
    )


@pytest.mark.asyncio
async def test_admin_reset_load_balancer_telemetry_api(client):
    """Test admin endpoint resets load balancer telemetry."""
    from core.config import settings
    admin_headers = {settings.ADMIN_API_KEY_HEADER_NAME: settings.ADMIN_API_KEY}

    res = await client.post("/api/v1/admin/load-balancer/reset", headers=admin_headers)
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_monitor_api_includes_load_balancer_stats(client):
    """Test GET /api/stats returns complete load_balancer telemetry object."""
    res = await client.get("/api/stats")
    assert res.status_code == 200
    data = res.json()
    assert "load_balancer" in data
    lb_stats = data["load_balancer"]
    assert "algorithm" in lb_stats
    assert "active_server_count" in lb_stats
    assert "servers" in lb_stats
    assert len(lb_stats["servers"]) == 4


@pytest.mark.asyncio
async def test_proxy_attaches_upstream_server_header(client, mock_upstream):
    """Test proxied response attaches X-Upstream-Server header."""
    import httpx

    def upstream_handler(request: httpx.Request):
        return httpx.Response(200, json={"data": "success"})

    mock_upstream(upstream_handler)
    res = await client.get("/api/v1/users", headers={"X-API-Key": "free-key-abc123"})
    assert res.status_code == 200
    assert "x-upstream-server" in res.headers


@pytest.mark.asyncio
async def test_in_flight_request_completes_when_pool_scaled_down(lb):
    """
    Test request started against server-3 completes safely even if pool is scaled from 4 -> 2 mid-flight.
    """
    lb.set_active_server_count(4)
    # Target server-3 specifically
    server_3 = lb.servers[2]
    assert server_3.id == "server-3"

    # Request begins on server-3
    lb.record_request_start(server_3)
    assert server_3.active_requests == 1

    # Admin scales down to 2 servers mid-flight
    lb.set_active_server_count(2)
    assert server_3.is_active is False

    # In-flight request on server-3 finishes
    lb.record_request_end(server_3, status_code=200, duration_ms=20.0)
    assert server_3.active_requests == 0
    assert server_3.successful_requests == 1
    assert server_3.total_requests == 1

    # New requests must NOT select server-3
    new_selections = [lb.select_server().id for _ in range(10)]
    assert "server-3" not in new_selections

