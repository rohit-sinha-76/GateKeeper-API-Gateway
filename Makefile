.PHONY: run test docker-build help

run: ## Start all services using Docker Compose (foreground)
	@echo "Starting GateKeeper API Gateway services..."
	docker compose up --build
	@echo "Services stopped."

test: ## Run unit tests (uses in-memory fakeredis)
	@echo "Running unit tests..."
	PYTHONPATH=. python -m pytest -v

docker-build: ## Build Docker images for all services
	@echo "Building Docker images..."
	docker compose build

help: ## Display this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-25s\033[0m %s\n", $$1, $$2}'
