.PHONY: run test docker-build

run:
	uvicorn main:app --reload --host 0.0.0.0 --port 8000

test:
	pytest

docker-build:
	docker build -t gatekeeper-api-gateway:latest .
