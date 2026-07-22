import asyncio
import time
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import statistics
import httpx
import fakeredis.aioredis
from main import app
from services.redis_client import set_redis
from services.proxy import set_http_client



async def run_benchmark(total_requests: int = 1000, concurrency: int = 25):
    """
    Run an in-memory load test against GateKeeper measuring throughput,
    p50/p95/p99 latency percentiles, and error rates.
    """
    # 1. Setup in-memory Redis and fast mock upstream
    server = fakeredis.FakeServer()
    fake_redis = fakeredis.aioredis.FakeRedis(server=server, decode_responses=True)
    set_redis(fake_redis)

    def fast_upstream(request: httpx.Request):
        return httpx.Response(200, json={"status": "ok", "timestamp": time.time()})

    transport = httpx.MockTransport(fast_upstream)
    mock_client = httpx.AsyncClient(transport=transport, base_url="http://localhost:8001")
    set_http_client(mock_client)

    # 2. Benchmark Client with premium key (6000 quota)
    headers = {"X-API-Key": "internal-key-ops001"}
    latencies = []
    status_counts = {}

    semaphore = asyncio.Semaphore(concurrency)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        async def send_single_request():
            async with semaphore:
                start = time.perf_counter()
                try:
                    response = await client.get("/api/v1/bench", headers=headers)
                    duration_ms = (time.perf_counter() - start) * 1000
                    latencies.append(duration_ms)
                    status_counts[response.status_code] = status_counts.get(response.status_code, 0) + 1
                except Exception as e:
                    status_counts[f"ERR: {type(e).__name__}"] = status_counts.get(f"ERR: {type(e).__name__}", 0) + 1

        overall_start = time.perf_counter()
        tasks = [send_single_request() for _ in range(total_requests)]
        await asyncio.gather(*tasks)
        total_time = time.perf_counter() - overall_start

    # 3. Calculate Percentiles
    latencies.sort()
    rps = total_requests / total_time
    p50 = statistics.median(latencies)
    p95 = latencies[int(len(latencies) * 0.95)]
    p99 = latencies[int(len(latencies) * 0.99)]
    min_lat = min(latencies)
    max_lat = max(latencies)
    mean_lat = statistics.mean(latencies)

    print("\n" + "=" * 55)
    print("       GATEKEEPER LOAD & LATENCY BENCHMARK")
    print("=" * 55)
    print(f"Total Requests:     {total_requests}")
    print(f"Concurrency Level:  {concurrency}")
    print(f"Total Time Taken:   {total_time:.3f} s")
    print(f"Throughput (RPS):   {rps:.2f} req/sec")
    print("-" * 55)
    print("LATENCY DISTRIBUTION (ms):")
    print(f"  Min:              {min_lat:.2f} ms")
    print(f"  Mean:             {mean_lat:.2f} ms")
    print(f"  p50 (Median):     {p50:.2f} ms")
    print(f"  p95:              {p95:.2f} ms")
    print(f"  p99:              {p99:.2f} ms")
    print(f"  Max:              {max_lat:.2f} ms")
    print("-" * 55)
    print("STATUS CODES:")
    for code, count in status_counts.items():
        print(f"  HTTP {code}:         {count} ({(count/total_requests)*100:.1f}%)")
    print("=" * 55 + "\n")


if __name__ == "__main__":
    asyncio.run(run_benchmark(total_requests=1000, concurrency=25))
