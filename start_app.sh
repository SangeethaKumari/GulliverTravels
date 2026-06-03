#!/bin/bash

# Trap Ctrl+C (SIGINT) and clean up background processes
trap cleanup INT

cleanup() {
    echo -e "\n🛑 Stopping all services..."
    kill $MCP_PID $BACKEND_PID $FRONTEND_PID 2>/dev/null
    exit 0
}

echo "🚀 Starting GulliverTravels multi-agent services..."

# 1. Start FastMCP Tool Server
echo "⚡ Starting FastMCP Tool Server..."
uv run python -m backend.src.mcp.fastmcp_server &
MCP_PID=$!

# 2. Wait a brief moment
sleep 2

# 3. Start FastAPI Backend Gateway on port 8000
echo "🌐 Starting FastAPI Gateway on port 8000..."
PYTHONPATH=. uv run python -m backend.src.travelagent.main &
BACKEND_PID=$!

# 4. Start React Frontend
echo "💻 Starting React UI Dev Server..."
cd frontend
npm run dev &
FRONTEND_PID=$!

# Wait for background processes to finish
wait
