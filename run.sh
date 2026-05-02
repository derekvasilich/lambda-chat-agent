#!/bin/bash
export PATH=$PATH:$(pwd)/bin
export PYTHONPATH=$PYTHONPATH:$(pwd)
exec python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8080