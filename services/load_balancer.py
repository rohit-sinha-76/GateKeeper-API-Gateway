"""
Dynamic multi-server load balancer service for GateKeeper API Gateway.
Supports Round Robin, Least Connections, IP Hash, and Random algorithms
with dynamic server pool configuration, request snapshots, and runtime metrics.
"""
import enum
import hashlib
import random
import time
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from core.config import settings
from utils.logger import get_logger

logger = get_logger(__name__)


class LoadBalancingAlgorithm(str, enum.Enum):
    ROUND_ROBIN = "round_robin"
    LEAST_CONNECTIONS = "least_connections"
    IP_HASH = "ip_hash"
    RANDOM = "random"


@dataclass
class UpstreamServer:
    id: str
    name: str
    url: str
    is_active: bool = True
    active_requests: int = 0
    total_requests: int = 0
    successful_requests: int = 0
    upstream_4xx: int = 0
    upstream_5xx: int = 0
    timeouts: int = 0
    connection_errors: int = 0
    total_latency_ms: float = 0.0

    @property
    def avg_latency_ms(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return round(self.total_latency_ms / self.total_requests, 2)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "url": self.url,
            "is_active": self.is_active,
            "active_requests": max(0, self.active_requests),
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "upstream_4xx": self.upstream_4xx,
            "upstream_5xx": self.upstream_5xx,
            "timeouts": self.timeouts,
            "connection_errors": self.connection_errors,
            "avg_latency_ms": self.avg_latency_ms,
        }

    def reset_telemetry(self) -> None:
        self.total_requests = 0
        self.successful_requests = 0
        self.upstream_4xx = 0
        self.upstream_5xx = 0
        self.timeouts = 0
        self.connection_errors = 0
        self.total_latency_ms = 0.0


class LoadBalancer:
    def __init__(self, initial_servers: Optional[List[UpstreamServer]] = None):
        if initial_servers:
            self._servers: List[UpstreamServer] = list(initial_servers)
        else:
            self._servers = [
                UpstreamServer(id="server-1", name="Backend Node 1", url=getattr(settings, "UPSTREAM_SERVER_1_URL", "http://127.0.0.1:8001")),
                UpstreamServer(id="server-2", name="Backend Node 2", url=getattr(settings, "UPSTREAM_SERVER_2_URL", "http://127.0.0.1:8002")),
                UpstreamServer(id="server-3", name="Backend Node 3", url=getattr(settings, "UPSTREAM_SERVER_3_URL", "http://127.0.0.1:8003")),
                UpstreamServer(id="server-4", name="Backend Node 4", url=getattr(settings, "UPSTREAM_SERVER_4_URL", "http://127.0.0.1:8004")),
            ]

        self._algorithm: LoadBalancingAlgorithm = LoadBalancingAlgorithm.ROUND_ROBIN
        self._active_server_count: int = min(len(self._servers), max(1, getattr(settings, "DEFAULT_ACTIVE_SERVER_COUNT", 4)))
        self._rr_index: int = 0
        self._sync_active_states()

    def _sync_active_states(self) -> None:
        """Ensure active status matches active_server_count."""
        for i, s in enumerate(self._servers):
            s.is_active = (i < self._active_server_count)

    @property
    def algorithm(self) -> LoadBalancingAlgorithm:
        return self._algorithm

    @property
    def active_server_count(self) -> int:
        return self._active_server_count

    @property
    def servers(self) -> List[UpstreamServer]:
        return list(self._servers)

    def get_active_servers(self) -> List[UpstreamServer]:
        """Return a point-in-time snapshot of active upstream servers."""
        return [s for s in self._servers if s.is_active]

    def set_active_server_count(self, count: int) -> None:
        """Dynamically configure the active server count (1 to 4)."""
        if not (1 <= count <= len(self._servers)):
            raise ValueError(f"Server count must be between 1 and {len(self._servers)}, got {count}")
        self._active_server_count = count
        self._sync_active_states()
        logger.info("Load balancer active server count updated", extra={"active_servers": count})

    def set_algorithm(self, algo: LoadBalancingAlgorithm | str) -> None:
        """Dynamically update the active load balancing algorithm."""
        if isinstance(algo, str):
            try:
                algo = LoadBalancingAlgorithm(algo.lower())
            except ValueError:
                raise ValueError(f"Unsupported algorithm: {algo}. Choose from: {[a.value for a in LoadBalancingAlgorithm]}")
        self._algorithm = algo
        logger.info("Load balancer algorithm updated", extra={"algorithm": algo.value})

    def select_server(self, client_ip: str = "127.0.0.1") -> UpstreamServer:
        """
        Select an upstream server based on current algorithm snapshot.
        Once selected, caller receives reference to server for isolated request tracking.
        """
        active = self.get_active_servers()
        if not active:
            # Fallback to first configured server if all marked inactive
            return self._servers[0]

        if self._algorithm == LoadBalancingAlgorithm.ROUND_ROBIN:
            idx = self._rr_index % len(active)
            self._rr_index = (self._rr_index + 1) % 1000000000
            return active[idx]

        elif self._algorithm == LoadBalancingAlgorithm.LEAST_CONNECTIONS:
            # Pick active server with smallest active in-flight request count
            return min(active, key=lambda s: s.active_requests)

        elif self._algorithm == LoadBalancingAlgorithm.IP_HASH:
            # Deterministic hash of client IP
            hash_bytes = hashlib.md5(client_ip.encode("utf-8")).digest()
            hash_int = int.from_bytes(hash_bytes[:4], "big")
            idx = hash_int % len(active)
            return active[idx]

        elif self._algorithm == LoadBalancingAlgorithm.RANDOM:
            return random.choice(active)

        return active[0]

    def record_request_start(self, server: UpstreamServer) -> None:
        """Increment in-flight request counter when request begins."""
        server.active_requests += 1

    def record_request_end(
        self,
        server: UpstreamServer,
        status_code: Optional[int] = None,
        duration_ms: float = 0.0,
        is_timeout: bool = False,
        is_connect_error: bool = False,
    ) -> None:
        """
        Decrement active in-flight request count in finally block and record telemetry metrics.
        """
        server.active_requests = max(0, server.active_requests - 1)
        server.total_requests += 1
        server.total_latency_ms += max(0.0, duration_ms)

        if is_timeout:
            server.timeouts += 1
        elif is_connect_error:
            server.connection_errors += 1
        elif status_code is not None:
            if 200 <= status_code < 300:
                server.successful_requests += 1
            elif 400 <= status_code < 500:
                server.upstream_4xx += 1
            elif 500 <= status_code < 600:
                server.upstream_5xx += 1

    def reset_telemetry(self) -> None:
        """Reset cumulative telemetry across all servers without changing configuration."""
        for s in self._servers:
            s.reset_telemetry()
        logger.info("Load balancer telemetry reset across all upstream servers")

    def get_stats(self) -> Dict[str, Any]:
        """Return structured telemetry for monitoring API and dashboard."""
        return {
            "algorithm": self._algorithm.value,
            "active_server_count": self._active_server_count,
            "total_configured_servers": len(self._servers),
            "servers": [s.to_dict() for s in self._servers],
        }


# Singleton shared instance
load_balancer = LoadBalancer()
