# Executive Dashboard - Deployment Guide

## What Was Built

A complete Next.js 14 executive dashboard with:
- 25+ components
- 7 visualization charts  
- Real-time API integration
- Docker deployment ready
- Hardcoded to Charm client

## File Structure

```
charm-email-os/
├── executive-dashboard/          # New dashboard (added)
│   ├── src/
│   │   ├── app/
│   │   │   ├── api/dashboard/    # API proxy
│   │   │   ├── globals.css
│   │   │   ├── layout.tsx
│   │   │   └── page.tsx          # Main dashboard
│   │   ├── components/
│   │   │   ├── charts/           # 4 chart components
│   │   │   └── ui/               # 3 UI components
│   │   └── lib/
│   │       ├── config.ts         # Charm client config
│   │       ├── types.ts          # TypeScript types
│   │       └── utils.ts          # Utilities
│   ├── Dockerfile                # Production build
│   ├── package.json
│   ├── next.config.js
│   ├── tailwind.config.js
│   ├── tsconfig.json
│   └── README.md
└── docker-compose.local.yml      # Updated (added service)
```

## Changes Made

### 1. Added Executive Dashboard Service

**File:** `docker-compose.local.yml`

```yaml
executive-dashboard:
  build:
    context: ./executive-dashboard
    dockerfile: Dockerfile
  container_name: charm-executive-dashboard
  ports:
    - "3006:3006"
  environment:
    - NEXT_PUBLIC_API_URL=http://charm-api:8000
  depends_on:
    - charm-api
    - postgres
  networks:
    - charm-network
```

### 2. Updated CORS Settings

Added executive dashboard to allowed origins in `charm-api` service.

### 3. Updated Quick Reference

Added executive dashboard URL to bottom of docker-compose file.

## How to Deploy

### Step 1: Navigate to Project

```bash
cd D:\Work\charm-email-os
```

### Step 2: Start Services

```bash
docker compose -f docker-compose.local.yml up -d
```

This will:
1. Build the executive dashboard Docker image
2. Start the container on port 3006
3. Connect to charm-api and postgres
4. Auto-start on system reboot

### Step 3: Access Dashboard

Open browser: **http://localhost:3006**

## Verification

### Check Container Status

```bash
docker ps | grep charm-executive-dashboard
```

Expected output:
```
charm-executive-dashboard   Up X minutes   0.0.0.0:3006->3006/tcp
```

### Check Logs

```bash
docker compose -f docker-compose.local.yml logs -f executive-dashboard
```

Expected output:
```
charm-executive-dashboard  | ▲ Next.js 14.x.x
charm-executive-dashboard  | - Local:        http://localhost:3006
charm-executive-dashboard  | ✓ Ready in Xms
```

### Test API Connection

```bash
curl http://localhost:3006/api/dashboard
```

Should return JSON with infrastructure data.

## Rebuilding

After making code changes:

```bash
docker compose -f docker-compose.local.yml up -d --build executive-dashboard
```

## Stopping

```bash
docker compose -f docker-compose.local.yml stop executive-dashboard
```

## Removing

```bash
docker compose -f docker-compose.local.yml down
docker rmi charm-executive-dashboard
```

## Access Points

| Service | URL | Port |
|---------|-----|------|
| **Executive Dashboard** | http://localhost:3006 | 3006 |
| Charm Frontend | http://localhost:3000 | 3000 |
| Charm API | http://localhost:8000 | 8000 |
| API Docs | http://localhost:8000/docs | 8000 |
| PostgreSQL | localhost:5433 | 5433 |

## Configuration

### Client Binding

Dashboard is hardcoded to Charm:
- **Client ID:** `4bd07dc0-059a-448b-b6f4-3275d0c104a9`
- **Client Name:** Charm

To change client, edit: `executive-dashboard/src/lib/config.ts`

### API URL

Uses Docker internal network: `http://charm-api:8000`

For local dev (outside Docker): `http://localhost:8000`

### Refresh Interval

Auto-refreshes every 5 minutes (300000ms)

Configurable in: `executive-dashboard/src/lib/config.ts`

## Troubleshooting

### Port 3006 Already in Use

```bash
# Find process using port
netstat -ano | findstr :3006

# Kill process (Windows)
taskkill /PID <pid> /F

# Or change port in docker-compose.local.yml
ports:
  - "3007:3006"  # Use 3007 instead
```

### Dashboard Shows "Connection Error"

1. Check charm-api is running:
   ```bash
   docker ps | grep charm-api
   ```

2. Check database is running:
   ```bash
   docker ps | grep charm-postgres
   ```

3. Test API endpoint:
   ```bash
   curl http://localhost:8000/api/health/infrastructure/4bd07dc0-059a-448b-b6f4-3275d0c104a9
   ```

### No Data Displayed

Verify Charm client exists in database:
```bash
docker exec -it charm-postgres psql -U postgres -d postgres -c "SELECT id, name FROM clients WHERE id = '4bd07dc0-059a-448b-b6f4-3275d0c104a9';"
```

### Build Fails

```bash
# Clear build cache
docker compose -f docker-compose.local.yml build --no-cache executive-dashboard

# Check node_modules
cd executive-dashboard
npm install
```

## Development

### Run Locally (Without Docker)

```bash
cd executive-dashboard

# Install dependencies
npm install

# Run dev server
npm run dev
```

Access: http://localhost:3006

### Make Changes

1. Edit files in `src/`
2. Changes auto-reload in dev mode
3. Rebuild Docker for production:
   ```bash
   docker compose -f docker-compose.local.yml up -d --build executive-dashboard
   ```

## Production Ready

✅ Dockerized and containerized
✅ Health checks configured
✅ Auto-restart enabled
✅ Production build optimized
✅ CORS configured
✅ Error handling implemented
✅ Loading states
✅ Auto-refresh
✅ TypeScript strict mode
✅ Responsive design

---

**Status:** Production Ready
**Version:** 1.0.0
**Last Updated:** 2026-02-23
