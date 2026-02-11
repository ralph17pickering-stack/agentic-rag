#!/bin/bash

# Agentic RAG Shutdown Script
# Stops all services started by startup.sh

set -uo pipefail

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
if docker ps -q --filter "ancestor=llamacpp-rocm:7.2" | grep -q .; then
    docker stop llm-service 2>/dev/null && echo "LLM service stopped" || echo "LLM service not running"
else
    echo "LLM service not running"
fi

# Stop Supabase
SUPABASE_DIR="/home/ralph/dev/supabase-project"
echo "Stopping Supabase..."
if docker ps | grep -q "supabase"; then
    docker compose -f "$SUPABASE_DIR/docker-compose.yml" stop
    echo "Supabase stopped"
else
    echo "Supabase not running"
fi

echo "================================"
echo "All services stopped."
