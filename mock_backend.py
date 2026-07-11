# Minimal mock backend running on port 8001 for local development.
import uvicorn
from fastapi import FastAPI

app = FastAPI(title="Mock Backend Service")


@app.get("/api/v1/users")
async def get_users():
    return [
        {"id": 1, "name": "Alice", "email": "alice@example.com"},
        {"id": 2, "name": "Bob", "email": "bob@example.com"},
    ]


@app.get("/api/v1/products")
async def get_products():
    return [
        {"id": 1, "name": "Widget Pro", "price": 29.99},
        {"id": 2, "name": "Gadget X", "price": 49.99},
    ]


if __name__ == "__main__":
    uvicorn.run("mock_backend:app", host="0.0.0.0", port=8001, reload=False)
