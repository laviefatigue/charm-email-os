#!/bin/bash
# Sync production database to local PostgreSQL via API
#
# Prerequisites:
#   1. Local postgres container running (docker-compose.debug.yml)
#   2. .env.local with:
#      PROD_API_URL=https://api.wizardgrimoire.cloud
#      ADMIN_KEY=your-admin-key
#
# Usage:
#   ./scripts/sync-from-production.sh

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== Production → Local Database Sync ===${NC}"

# Load environment variables
if [ -f .env.local ]; then
    export $(grep -v '^#' .env.local | xargs)
else
    echo -e "${RED}Error: .env.local not found${NC}"
    exit 1
fi

# Set defaults
PROD_API_URL="${PROD_API_URL:-https://api.wizardgrimoire.cloud}"
ADMIN_KEY="${ADMIN_KEY:-}"

if [ -z "$ADMIN_KEY" ]; then
    echo -e "${RED}Error: ADMIN_KEY not set in .env.local${NC}"
    echo "Add: ADMIN_KEY=your-admin-key"
    exit 1
fi

# Local values
LOCAL_HOST="localhost"
LOCAL_PORT="5433"
LOCAL_DB="postgres"
LOCAL_USER="postgres"
LOCAL_PASS="localdevpassword"

# Check if local postgres is running
if ! docker ps | grep -q charm-postgres; then
    echo -e "${RED}Error: Local postgres container not running${NC}"
    echo "Start it with: docker compose -f docker-compose.debug.yml up -d postgres"
    exit 1
fi

# Create temp directory for dump
DUMP_DIR="/tmp/charm-db-sync"
mkdir -p "$DUMP_DIR"
DUMP_FILE="$DUMP_DIR/production_dump.sql"

echo -e "${YELLOW}Step 1/4: Downloading database from production API...${NC}"
echo "  URL: $PROD_API_URL/api/admin/db-export"

# Download dump via API
HTTP_CODE=$(curl -s -w "%{http_code}" -o "$DUMP_FILE" \
    "${PROD_API_URL}/api/admin/db-export?key=${ADMIN_KEY}&exclude_audit=true")

if [ "$HTTP_CODE" != "200" ]; then
    echo -e "${RED}Error: API returned HTTP $HTTP_CODE${NC}"
    cat "$DUMP_FILE"
    exit 1
fi

DUMP_SIZE=$(du -h "$DUMP_FILE" | cut -f1)
echo -e "${GREEN}  Download complete: $DUMP_SIZE${NC}"

echo -e "${YELLOW}Step 2/4: Stopping charm-api to release connections...${NC}"
docker stop charm-api 2>/dev/null || true

echo -e "${YELLOW}Step 3/4: Restoring to local database...${NC}"
PGPASSWORD="$LOCAL_PASS" psql \
    -h "$LOCAL_HOST" \
    -p "$LOCAL_PORT" \
    -U "$LOCAL_USER" \
    -d "$LOCAL_DB" \
    -f "$DUMP_FILE" \
    2>&1 | grep -E "(ERROR|FATAL)" || true

echo -e "${YELLOW}Step 4/4: Restarting charm-api...${NC}"
docker start charm-api 2>/dev/null || true

# Cleanup
rm -f "$DUMP_FILE"

echo ""
echo -e "${GREEN}=== Sync Complete ===${NC}"
echo ""
echo "Local database now mirrors production."
echo "API available at: http://localhost:8000"
echo ""

# Show table counts
echo -e "${YELLOW}Table counts:${NC}"
PGPASSWORD="$LOCAL_PASS" psql -h "$LOCAL_HOST" -p "$LOCAL_PORT" -U "$LOCAL_USER" -d "$LOCAL_DB" -c "
SELECT
    'domains' as table_name, COUNT(*) as rows FROM domains
UNION ALL SELECT 'sender_accounts', COUNT(*) FROM sender_accounts
UNION ALL SELECT 'clients', COUNT(*) FROM clients
UNION ALL SELECT 'workspaces', COUNT(*) FROM workspaces
UNION ALL SELECT 'kill_queue', COUNT(*) FROM kill_queue
ORDER BY table_name;
"
