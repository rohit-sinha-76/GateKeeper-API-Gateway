#!/bin/bash
set -e

echo "Starting GateKeeper services locally..."

# Check if venv exists and activate it
if [ -d "venv" ]; then
    echo "Activating virtual environment..."
    source venv/bin/activate
else
    echo "Virtual environment 'venv' not found. Please run 'python -m venv venv && pip install -r requirements.txt' first."
    exit 1
fi

echo "Starting mock upstream backend nodes (ports 8001-8004) in background..."
# The mock_backend.py script without arguments launches all 4 nodes internally using uvicorn.Server
python mock_backend.py &
MOCK_BACKEND_PID=$!
echo "Mock backend PID: $MOCK_BACKEND_PID"

# Wait a moment for the mock backends to fully initialize
echo "Giving mock backend a moment to start up..."
sleep 5

echo "Starting GateKeeper API Gateway (port 8000) in foreground..."
# Start the main FastAPI application using uvicorn with --reload for development
uvicorn main:app --reload --port 8000

# Ensure the mock backend is killed when the gateway process exits
trap "echo 'Shutting down mock backend (PID: $MOCK_BACKEND_PID)...'; kill $MOCK_BACKEND_PID" EXIT
