#!/bin/bash

# Agentic RAG Startup Script
# This script starts all required services for the application

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

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
    echo ""
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
SUPABASE_DIR="$SCRIPT_DIR/db"
echo "Starting Supabase..."
if ! docker ps | grep -q "supabase"; then
    echo "Supabase not running, starting it now..."
    docker compose -f "$SUPABASE_DIR/docker-compose.yml" --env-file "$SUPABASE_DIR/.env" up -d
else
    echo "Supabase already running"
fi

# Start embedding model service (if not already running)
EMBED_DIR="$SCRIPT_DIR/embed"
echo "Starting embedding model service..."
if docker ps --format '{{.Names}}' | grep -q "^nomic-embed$"; then
    echo "Embedding model already running"
else
    echo "Embedding model not running, starting it now..."
    docker compose -f "$EMBED_DIR/docker-compose.yml" up -d
fi

# Start LLM service (if not already running)
QWEN3_DIR="$SCRIPT_DIR/qwen3"
echo "Starting LLM service..."
if docker ps --format '{{.Names}}' | grep -q "^llamacpp-rocm72$"; then
    echo "LLM service already running"
else
    echo "LLM service not running, starting it now..."
    docker compose -f "$QWEN3_DIR/docker-compose.yml" up -d
fi

# Start Backend API
echo "Starting Backend API..."
BACKEND_DIR="$SCRIPT_DIR/app/backend"
if [ ! -d "$BACKEND_DIR/venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$BACKEND_DIR/venv"
    "$BACKEND_DIR/venv/bin/pip" install --upgrade pip
    "$BACKEND_DIR/venv/bin/pip" install -r "$BACKEND_DIR/requirements.txt"
else
    "$BACKEND_DIR/venv/bin/pip" install -q -r "$BACKEND_DIR/requirements.txt"
fi

"$BACKEND_DIR/venv/bin/uvicorn" app.main:app \
    --host 0.0.0.0 --port 8001 --reload \
    --app-dir "$BACKEND_DIR" \
    > /tmp/agentic-rag-backend.log 2>&1 &
BACKEND_PID=$!
disown $BACKEND_PID

echo "Backend API started with PID: $BACKEND_PID (log: /tmp/agentic-rag-backend.log)"

# Start Frontend
echo "Starting Frontend..."
FRONTEND_DIR="$SCRIPT_DIR/app/frontend"
npm --prefix "$FRONTEND_DIR" install
npm --prefix "$FRONTEND_DIR" run dev > /tmp/agentic-rag-frontend.log 2>&1 &
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
echo "Backend API:     http://localhost:8001  (PID: $BACKEND_PID)"
echo "Frontend:        http://localhost:5173  (PID: $FRONTEND_PID)"
echo "Supabase:        http://localhost:8000"
echo "Embedding model: http://localhost:8082"
echo "LLM service:     http://localhost:8081"
echo ""
echo "Logs:"
echo "  Backend:  tail -f /tmp/agentic-rag-backend.log"
echo "  Frontend: tail -f /tmp/agentic-rag-frontend.log"
echo ""
echo "To stop: ./shutdown.sh"
