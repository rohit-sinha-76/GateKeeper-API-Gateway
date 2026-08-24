.PHONY: run test docker-build clean

run:
	@echo "Starting GateKeeper API Gateway, Redis, and Mock Backends via Docker Compose..."
	docker compose up --build

test:
	@echo "Ensuring Python dependencies are installed..."
	pip install -r requirements.txt
	@echo "Starting Redis for integration tests..."
	docker compose up -d redis
	@echo "Running integration tests with real Redis..."
	USE_REAL_REDIS=1 REDIS_URL=redis://localhost:6379/0 PYTHONPATH=. python -m pytest -v
	@echo "Stopping Redis container..."
	docker compose down redis

docker-build:
	@echo "Building Docker images for GateKeeper and Mock Backends..."
	docker compose build

clean:
	@echo "Stopping and removing all Docker Compose services and volumes..."
	docker compose down -v --rmi all
	@echo "Removing Python virtual environment..."
	rm -rf venv
	@echo "Cleaning Python build artifacts..."
	find . -type f -name "*.py[co]" -delete
	find . -type d -name "__pycache__" -delete
	rm -rf .pytest_cache
	@echo "Cleanup complete."
