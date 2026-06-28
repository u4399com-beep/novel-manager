#!/bin/bash
cd "$(dirname "$0")/backend"

echo "=== Starting Novel Manager ==="

# Start backend
python3 -m uvicorn app.main:app --port 8008 --log-level warning > /tmp/backend.log 2>&1 &
echo "Backend: http://localhost:8008"

# Start frontend
cd ../frontend
/Users/nbtools/.local/node-v20.18.0/bin/node node_modules/.bin/vite --port 5173 > /tmp/frontend.log 2>&1 &
echo "Frontend: http://localhost:5173"

# Start queue
cd ../backend
python3 queue_runner.py --concurrent 8 > /tmp/queue_runner.log 2>&1 &
echo "Queue: started"

sleep 2
curl -s http://localhost:8008/health && echo " ✅"
