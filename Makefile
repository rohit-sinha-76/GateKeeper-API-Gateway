.PHONY: run test docker-build

# Default target when `make` is run without arguments
all: run

# Bring up the entire GateKeeper API Gateway system using Docker Compose.
# This includes the gateway, Redis, and all mock backend services.
# The --build flag ensures images are rebuilt if sources have changed.
run:
	@echo "🚀 Starting GateKeeper API Gateway with Docker Compose..."
	docker compose up --build

# Run the automated test suite.
# By default, tests use in-memory fakeredis with Lua engine for speed.
# To run integration tests against a real Redis instance, use `USE_REAL_REDIS=1 make test`.
test:
	@echo "🧪 Running test suite..."
	PYTHONPATH=. python -m pytest -v

# Build Docker images for all services defined in docker-compose.yml.
# This command only builds images and does not start any containers.
docker-build:
	@echo "🐳 Building Docker images for GateKeeper services..."
	docker compose build
