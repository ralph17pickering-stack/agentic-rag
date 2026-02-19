#!/bin/bash

# Agentic RAG Shutdown Script
# Stops all services started by startup.sh

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Stopping Agentic RAG services..."
echo "================================"

# Stop Frontend (vite dev server)
echo "Stopping Frontend..."
pkill -f "vite.*5173" 2>/dev/null && echo "Frontend stopped" || echo "Frontend not running"

# Stop Backend API (uvicorn)
echo "Stopping Backend API..."
pkill -f "uvicorn app.main:app.*8001" 2>/dev/null && echo "Backend stopped" || echo "Backend not running"

# Stop LLM service
echo "Stopping LLM service..."
if docker ps --format '{{.Names}}' | grep -q "^llamacpp-rocm72$"; then
    docker compose -f "$SCRIPT_DIR/qwen3/docker-compose.yml" down
    echo "LLM service stopped"
else
    echo "LLM service not running"
fi

# Stop embedding model service
echo "Stopping embedding model service..."
if docker ps --format '{{.Names}}' | grep -q "^nomic-embed$"; then
    docker compose -f "$SCRIPT_DIR/embed/docker-compose.yml" down
    echo "Embedding model stopped"
else
    echo "Embedding model not running"
fi

# Stop Supabase
echo "Stopping Supabase..."
if docker ps | grep -q "supabase"; then
    docker compose -f "$SCRIPT_DIR/db/docker-compose.yml" --env-file "$SCRIPT_DIR/db/.env" stop
    echo "Supabase stopped"
else
    echo "Supabase not running"
fi

echo "================================"
echo "All services stopped."
