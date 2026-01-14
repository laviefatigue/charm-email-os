#!/bin/sh
echo "=== Container Starting ==="
echo "Date: $(date)"
echo "Python: $(python --version)"
echo "Working directory: $(pwd)"
echo "Files: $(ls -la)"
echo "Main.py content:"
cat main.py
echo ""
echo "=== Starting uvicorn ==="
exec uvicorn main:app --host 0.0.0.0 --port 8000
