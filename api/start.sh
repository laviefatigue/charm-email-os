#!/bin/sh
echo "=== Container Starting ==="
echo "Date: $(date)"
echo "Python: $(python --version)"
echo "Working directory: $(pwd)"
echo "Files:"
ls -la
echo ""
echo "=== Testing imports ==="
python -c "
import sys
print('Testing critical imports...')
try:
    from config import settings
    print(f'config: OK - CORS_ORIGINS={settings.CORS_ORIGINS}')
except Exception as e:
    print(f'config: FAILED - {e}')
    sys.exit(1)

try:
    import database
    print('database: OK')
except Exception as e:
    print(f'database: FAILED - {e}')
    sys.exit(1)

try:
    from routes import workspaces, clients, domains, inboxes, campaigns, leads, health
    print('routes: OK')
except Exception as e:
    print(f'routes: FAILED - {e}')
    sys.exit(1)

try:
    from main import app
    print('main: OK')
except Exception as e:
    print(f'main: FAILED - {e}')
    sys.exit(1)

print('All imports successful!')
"
if [ $? -ne 0 ]; then
    echo "Import test failed!"
    exit 1
fi
echo ""
echo "=== Starting uvicorn ==="
exec uvicorn main:app --host 0.0.0.0 --port 8000
