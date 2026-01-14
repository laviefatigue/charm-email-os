#!/bin/sh
echo "=== Charm Email OS API ==="
echo "Date: $(date)"
echo "Python: $(python --version)"
echo "Working dir: $(pwd)"
echo "Files:"
ls -la
echo ""
echo "Testing Python import..."
python -c "from fastapi import FastAPI; print('FastAPI OK')"
python -c "import main; print('main.py OK')"
echo ""
echo "Starting uvicorn..."
exec uvicorn main:app --host 0.0.0.0 --port 8000 --log-level debug
