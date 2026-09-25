import uvicorn
from fastapi import FastAPI, Response, HTTPException

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
        raise HTTPException(status_code=500, detail=f"Simulated 500 server outage on {node_id}")

    return app


# Create a single FastAPI app for port 8001
app = create_app("server-1", 8001)

if __name__ == "__main__":
    # Run the single mock backend on port 8001
    print("[MOCK BACKEND] Starting single node server-1 on port 8001...")
    uvicorn.run(app, host="0.0.0.0", port=8001, log_level="info")
