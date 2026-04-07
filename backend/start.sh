#!/bin/bash
# Start the Travel Agent API (Prototype 1)
# Run from: backend/
cd "$(dirname "$0")"
python3 -m uvicorn main:app --reload --port 8000
