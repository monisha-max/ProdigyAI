#!/bin/bash
# Start MCP Toolbox in background
./toolbox --tools-file="tools.yaml" --port 5000 &

# Wait for toolbox to be ready
echo "Waiting for MCP Toolbox to start..."
for i in $(seq 1 30); do
    if curl -s http://127.0.0.1:5000/api/toolset > /dev/null 2>&1; then
        echo "MCP Toolbox is ready!"
        break
    fi
    sleep 1
done

# Start FastAPI server
exec uvicorn main:app --host 0.0.0.0 --port 8080
