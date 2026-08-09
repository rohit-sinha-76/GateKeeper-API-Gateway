.PHONY: run run-backend test test-real-redis docker-build docker-up docker-down clean

run:
	uvicorn main:app --reload --host 0.0.0.0 --port 8000

run-backend:
	python mock_backend.py

test:
	pytest -v

test-real-redis:
	USE_REAL_REDIS=1 pytest -v

docker-build:
	docker build -t gatekeeper-api-gateway:latest .

docker-up:
	docker compose up --build

docker-down:
	docker compose down

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
