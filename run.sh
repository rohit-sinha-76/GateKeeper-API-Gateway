#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e

echo "Starting GateKeeper API Gateway and Mock Backend..."

# Ensure venv is activated
if [ -d "venv" ]; then
    source venv/bin/activate
else
    echo "Virtual environment 'venv' not found. Please run 'python -m venv venv && pip install -r requirements.txt'."
    exit 1
fi

# Set environment variables for the gateway
# REDIS_URL defaults to 127.0.0.1:6379, assuming a local Redis instance is running.
export REDIS_URL="${REDIS_URL:-redis://127.0.0.1:6379/0}"
# CRITICAL: Adjust active server count for local single mock_backend.py instance (which only runs on 8001)
export DEFAULT_ACTIVE_SERVER_COUNT="${DEFAULT_ACTIVE_SERVER_COUNT:-1}"
export UPSTREAM_SERVER_1_URL="${UPSTREAM_SERVER_1_URL:-http://127.0.0.1:8001}"

# Start mock_backend.py in the background
echo "Starting mock_backend.py on port 8001..."
python mock_backend.py > mock_backend.log 2>&1 &
MOCK_BACKEND_PID=$!
echo "Mock Backend PID: $MOCK_BACKEND_PID (logs in mock_backend.log)"

# Give backend a moment to start up
sleep 2

# Start main.py (FastAPI Gateway) in the background with --reload for development
echo "Starting GateKeeper API Gateway on port 8000..."
uvicorn main:app --reload --port 8000 > gateway.log 2>&1 &
GATEWAY_PID=$!
echo "Gateway PID: $GATEWAY_PID (logs in gateway.log)"

echo ""
echo "--------------------------------------------------------"
echo "GateKeeper API Gateway and Mock Backend are running."
echo "Gateway accessible at: http://localhost:8000"
echo "Dashboard accessible at: http://localhost:8000/monitor"
echo "To stop processes: kill $MOCK_BACKEND_PID $GATEWAY_PID"
echo "--------------------------------------------------------"
echo ""
