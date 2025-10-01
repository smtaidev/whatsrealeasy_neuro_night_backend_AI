#!/bin/bash
set -e

if [ "$SERVICE_TYPE" = "inbound" ]; then
    echo "Starting Inbound Service on port 8000..."
    exec python -m uvicorn inbound_service.main:app --host 0.0.0.0 --port 8000 --workers 1
else
    echo "Starting Outbound Service on port 8500..."
    exec python -m uvicorn outbound_service.main:app --host 0.0.0.0 --port 8500 --workers 1
fi
