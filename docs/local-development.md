# Local Development Environment

A 1:1 mirror of the production Charm Email OS stack for local development and testing.

## Quick Start

```bash
# Start all services
docker compose -f docker-compose.local.yml up -d

# View logs
docker compose -f docker-compose.local.yml logs -f

# Stop services (preserves data)
docker compose -f docker-compose.local.yml down

# Reset database (deletes all data)
docker compose -f docker-compose.local.yml down -v
```

## Access Points

| Service | URL | Notes |
|---------|-----|-------|
| Frontend | http://localhost:3000 | Next.js application |
| API | http://localhost:8000 | FastAPI backend |
| API Docs | http://localhost:8000/docs | Swagger UI |
| Database | localhost:5433 | PostgreSQL (user: postgres, pass: localdevpassword) |

## Test Data

The local environment is seeded with:

| Entity | ID | Description |
|--------|-----|-------------|
| Workspace | `a1b2c3d4-e5f6-7890-abcd-ef1234567890` | Charm Test Workspace |
| **Charm Client** | `4bd07dc0-059a-448b-b6f4-3275d0c104a9` | Main test client (matches production) |
| Onboarding Submission | `550e8400-e29b-41d4-a716-446655440000` | Complete submission for Charm |
| Strategy | `660e8400-e29b-41d4-a716-446655440001` | Q1 2026 Outbound Campaign |
| Campaign Cycle | `770e8400-e29b-41d4-a716-446655440001` | Cycle 1 (Feb 10-24) |
| Campaign Document | `aa0e8400-e29b-41d4-a716-446655440001` | Sample stablekernel document |

### Access Charm Client
```
http://localhost:3000/clients/4bd07dc0-059a-448b-b6f4-3275d0c104a9
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    docker-compose.local.yml                  │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────┐ │
│  │  Frontend   │───▶│    API      │───▶│   PostgreSQL    │ │
│  │  :3000      │    │    :8000    │    │   :5433         │ │
│  │  (Next.js)  │    │  (FastAPI)  │    │   (postgres:15) │ │
│  └─────────────┘    └─────────────┘    └─────────────────┘ │
│                                                              │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │              Strategy Worker (Optional)                  │ │
│  │         (Uncomment in docker-compose to enable)          │ │
│  └─────────────────────────────────────────────────────────┘ │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

## Development Workflows

### Frontend Development (Hot Reload)

For faster frontend iteration, run Next.js locally while using Docker for backend:

```bash
# Start only backend services
docker compose -f docker-compose.local.yml up -d postgres charm-api

# Run frontend locally
cd charm-email-os
npm install
npm run dev
```

Frontend will be at http://localhost:3000 with hot reload.

### API Development

For API changes, rebuild the container:

```bash
docker compose -f docker-compose.local.yml up -d --build charm-api
```

Or run the API locally:

```bash
# Start only database
docker compose -f docker-compose.local.yml up -d postgres

# Run API locally
cd api
pip install -r requirements.txt
POSTGRES_HOST=localhost POSTGRES_PORT=5433 POSTGRES_PASSWORD=localdevpassword uvicorn main:app --reload
```

### Database Access

Connect with psql:
```bash
psql -h localhost -p 5433 -U postgres -d postgres
```

Or use any PostgreSQL GUI (DBeaver, pgAdmin, etc.):
- Host: localhost
- Port: 5433
- Database: postgres
- User: postgres
- Password: localdevpassword

### Testing Strategy Generation

To test the strategy AI worker locally:

1. Uncomment the `strategy-worker` service in `docker-compose.local.yml`

2. Set up Claude Code credentials (one-time):
   ```bash
   # Start the worker
   docker compose -f docker-compose.local.yml up -d strategy-worker

   # Enter the container
   docker exec -it charm-strategy-worker bash

   # Authenticate
   claude /login
   # Follow OAuth flow in browser
   ```

3. Create a test generation job:
   ```bash
   python scripts/test_strategy_generation.py
   ```

4. Monitor the worker:
   ```bash
   docker logs -f charm-strategy-worker
   ```

## Comparison: Local vs Production

| Aspect | Local | Production |
|--------|-------|------------|
| Database | Local PostgreSQL (:5433) | OwnRBL PostgreSQL (31.97.142.123) |
| Frontend | Docker or local dev server | Coolify deployment |
| API | Docker (:8000) | Coolify deployment |
| Workers | Optional (uncomment) | Always running |
| Data | Seed data | Real client data |
| Email Bison | Optional (set API key) | Connected |

## Troubleshooting

### Port Conflicts

If port 3000 or 8000 is in use:

```bash
# Edit docker-compose.local.yml and change ports:
ports:
  - "3001:3000"  # Frontend on 3001
  - "8001:8000"  # API on 8001
```

### Database Won't Start

```bash
# Check if port 5433 is in use
netstat -an | findstr 5433

# Reset database
docker compose -f docker-compose.local.yml down -v
docker compose -f docker-compose.local.yml up -d
```

### API Health Check Fails

```bash
# Check API logs
docker logs charm-api

# Common issue: database not ready
# Solution: wait a few seconds and retry
docker compose -f docker-compose.local.yml restart charm-api
```

### Frontend Build Errors

```bash
# Rebuild from scratch
docker compose -f docker-compose.local.yml build --no-cache charm-frontend
docker compose -f docker-compose.local.yml up -d charm-frontend
```

## Files Reference

| File | Purpose |
|------|---------|
| `docker-compose.local.yml` | Main local stack definition |
| `docker/init/01-schema.sql` | Database schema (runs on first start) |
| `docker/init/02-seed.sql` | Test data (runs on first start) |
| `.env.local` | Environment variables template |

## Next Steps

After starting the local environment:

1. **Access the frontend**: http://localhost:3000
2. **Navigate to Charm client**: http://localhost:3000/clients/4bd07dc0-059a-448b-b6f4-3275d0c104a9
3. **Test the Strategy page**: Click on Strategy tab
4. **View API docs**: http://localhost:8000/docs
5. **Run tests**: `npm test` in `charm-email-os/` directory
