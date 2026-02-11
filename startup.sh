#!/bin/bash

# Agentic RAG Startup Script
# This script starts all required services for the application

set -euo pipefail

echo "Starting Agentic RAG services..."
echo "================================"

# Function to check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to wait for a service to be ready
wait_for_service() {
    local url=$1
    local name=$2
    local timeout=${3:-30}
    
    echo "Waiting for $name to be ready..."
    for i in $(seq 1 $timeout); do
        if curl -f -s "$url" >/dev/null 2>&1; then
            echo "$name is ready!"
            return 0
        fi
        echo -n "."
        sleep 1
    done
    echo "Error: $name did not become ready within $timeout seconds"
    return 1
}

# Check if required tools are available
echo "Checking dependencies..."
if ! command_exists docker; then
    echo "Error: Docker is not installed or not in PATH"
    exit 1
fi

if ! command_exists npm; then
    echo "Error: npm is not installed or not in PATH"
    exit 1
fi

if ! command_exists python3; then
    echo "Error: python3 is not installed or not in PATH"
    exit 1
fi

echo "All dependencies found!"

# Start Supabase (if not already running)
SUPABASE_DIR="/home/ralph/dev/supabase-project"
echo "Starting Supabase..."
if ! docker ps | grep -q "supabase"; then
    echo "Supabase not running, starting it now..."
    docker compose -f "$SUPABASE_DIR/docker-compose.yml" up -d
else
    echo "Supabase already running"
fi

# Start LLM service (if not already running)
echo "Starting LLM service..."
if ! docker ps | grep -q "llamacpp"; then
    echo "LLM service not running, starting it now..."
    # Use existing llamacpp container instead
    docker run -d \
        --name llm-service \
        -p 8081:8081 \
        --restart unless-stopped \
        --network host \
        llamacpp-rocm:7.2
else
    echo "LLM service already running"
fi

# Start Backend API
echo "Starting Backend API..."
cd backend
# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    source venv/bin/activate
    pip install --upgrade pip
    pip install -r requirements.txt
else
    source venv/bin/activate
    pip install -q -r requirements.txt
fi

# Start uvicorn server in background
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload > /tmp/agentic-rag-backend.log 2>&1 &
BACKEND_PID=$!
disown $BACKEND_PID

echo "Backend API started with PID: $BACKEND_PID (log: /tmp/agentic-rag-backend.log)"

# Start Frontend
echo "Starting Frontend..."
cd ../frontend
if ! command_exists npm; then
    echo "Error: npm is not installed or not in PATH"
    exit 1
fi

# Install frontend dependencies
npm install

# Start frontend in background
npm run dev > /tmp/agentic-rag-frontend.log 2>&1 &
FRONTEND_PID=$!
disown $FRONTEND_PID

echo "Frontend started with PID: $FRONTEND_PID (log: /tmp/agentic-rag-frontend.log)"

# Wait for services to be ready
echo "Waiting for services to be ready..."
wait_for_service "http://localhost:8001/health" "Backend API" 30
wait_for_service "http://localhost:5173" "Frontend" 30

echo ""
echo "All services started successfully!"
echo "================================"
echo "Backend API: http://localhost:8001  (PID: $BACKEND_PID)"
echo "Frontend:    http://localhost:5173  (PID: $FRONTEND_PID)"
echo "Supabase:    http://localhost:8000"
echo ""
echo "Logs:"
echo "  Backend:  tail -f /tmp/agentic-rag-backend.log"
echo "  Frontend: tail -f /tmp/agentic-rag-frontend.log"
echo ""
echo "To stop: ./shutdown.sh"