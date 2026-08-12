.PHONY: run test docker-build

run:
	@echo "Starting GateKeeper API Gateway, Redis, and Mock Backends with Docker Compose..."
	docker compose up --build

test:
	@echo "Installing Python dependencies..."
	python -m pip install --upgrade pip
	pip install -r requirements.txt
	@echo "Ensuring Redis service is up for integration tests..."
	docker compose up -d redis
	@echo "Running Pytest suite with real Redis..."
	PYTHONPATH=. REDIS_URL=redis://localhost:6379/0 USE_REAL_REDIS=1 python -m pytest -v
	@echo "Stopping Redis service..."
	docker compose stop redis

docker-build:
	@echo "Building Docker images for GateKeeper and Mock Backends..."
	docker compose build
