import sys
import argparse
import asyncio
import os
import uvicorn
from fastapi import FastAPI, Response

def create_app(node_id: str, port: int) -> FastAPI:
    app = FastAPI(title=f"Mock Backend {node_id}")

    @app.middleware("http")
    async def add_backend_headers(request, call_next):
        response: Response = await call_next(request)
        response.headers["X-Backend-Node"] = node_id
        response.headers["X-Backend-Port"] = str(port)
        return response

    @app.get("/health")
    async def health():
        return {"status": "ok", "node": node_id, "port": port}

    @app.get("/api/v1/users")
    async def get_users():
        return [
            {"id": 1, "name": "Alice", "email": "alice@example.com", "node": node_id},
            {"id": 2, "name": "Bob", "email": "bob@example.com", "node": node_id},
            {"id": 3, "name": "Charlie", "email": "charlie@example.com", "node": node_id},
            {"id": 4, "name": "Diana", "email": "diana@example.com", "node": node_id},
            {"id": 5, "name": "Eve", "email": "eve@example.com", "node": node_id},
        ]

    @app.get("/api/v1/products")
    async def get_products():
        return [
            {"id": 1, "name": "Widget Pro", "price": 29.99, "node": node_id},
            {"id": 2, "name": "Gadget X", "price": 49.99, "node": node_id},
        ]

    @app.get("/api/v1/fault/500")
    async def simulate_500():
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=f"Simulated 500 server outage on {node_id}")

    return app



# Default node apps for programmatic access
app = create_app("server-1", 8001)
app_node1 = app
app_node2 = create_app("server-2", 8002)
app_node3 = create_app("server-3", 8003)
app_node4 = create_app("server-4", 8004)


async def run_all_nodes():
    """Run all 4 backend nodes concurrently in an asyncio event loop."""
    configs = [
        uvicorn.Config(create_app("server-1", 8001), host="0.0.0.0", port=8001, log_level="warning"),
        uvicorn.Config(create_app("server-2", 8002), host="0.0.0.0", port=8002, log_level="warning"),
        uvicorn.Config(create_app("server-3", 8003), host="0.0.0.0", port=8003, log_level="warning"),
        uvicorn.Config(create_app("server-4", 8004), host="0.0.0.0", port=8004, log_level="warning"),
    ]
    servers = [uvicorn.Server(c) for c in configs]
    print("[MOCK BACKEND] Starting 4 upstream nodes on ports 8001, 8002, 8003, 8004...")
    await asyncio.gather(*(s.serve() for s in servers))


def main():
    parser = argparse.ArgumentParser(description="GateKeeper Mock Backend Runner")
    parser.add_argument("--port", type=int, default=None, help="Port to run single node on")
    parser.add_argument("--node-id", type=str, default=None, help="Node ID (e.g. server-1)")
    args = parser.parse_args()

    port_env = os.getenv("BACKEND_PORT")
    node_env = os.getenv("BACKEND_NODE_ID")

    target_port = args.port or (int(port_env) if port_env else None)
    target_node = args.node_id or node_env or ("server-1" if target_port else None)

    if target_port:
        node_app = create_app(target_node or f"server-port-{target_port}", target_port)
        print(f"[MOCK BACKEND] Starting single node {target_node} on port {target_port}...")
        uvicorn.run(node_app, host="0.0.0.0", port=target_port, log_level="info")
    else:
        asyncio.run(run_all_nodes())


if __name__ == "__main__":
    main()