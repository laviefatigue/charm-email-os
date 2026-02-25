# Charm Email OS

Email infrastructure management platform for cold outreach operations. Manages inbox health, campaign deployment, domain rotation, and automated kill triggers.

## Quick Start

```bash
# 1. Clone the repository
git clone https://github.com/laviefatigue/charm-email-os.git
cd charm-email-os

# 2. Configure environment
cp .env.example .env.local
# Edit .env.local with your values (see ENV-REFERENCE.md for details)

# 3. Start all services
docker compose -f docker-compose.local.yml up -d

# 4. Access the application
# Frontend: http://localhost:3000
# API Docs: http://localhost:8000/docs
```

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Frontend (Next.js)                        │
│                      http://localhost:3000                       │
├─────────────────────────────────────────────────────────────────┤
│                        API (FastAPI)                             │
│                      http://localhost:8000                       │
├──────────────────┬──────────────────┬───────────────────────────┤
│  EmailBison Sync │  Strategy Worker │  Hypertide Worker         │
│  (Health/Kills)  │  (AI Generation) │  (Domain Purchasing)      │
├──────────────────┴──────────────────┴───────────────────────────┤
│                      PostgreSQL Database                         │
│                      localhost:5433                              │
└─────────────────────────────────────────────────────────────────┘
```

## Services

| Service | Port | Purpose |
|---------|------|---------|
| Frontend | 3000 | Next.js dashboard |
| API | 8000 | FastAPI backend |
| PostgreSQL | 5433 | Database |
| Onboarding | 3004 | Client submission form |

## Features

- **Inbox Health Monitoring** - Automated health scoring and kill triggers
- **Kill Trigger System** - Auto-detect and tag problematic inboxes
- **Campaign Management** - Deploy inboxes to campaigns with rotation
- **Domain Lifecycle** - Track domain age, reputation, rotation needs
- **Strategy Generation** - AI-powered outreach strategy creation
- **Infrastructure Sync** - Real-time sync with EmailBison

## Documentation

Detailed documentation is in the `docs/` folder:

- [Quick Start Guide](docs/local-development/quick-start.md)
- [Environment Variables](docs/local-development/environment-variables.md)
- [Docker Compose Reference](docs/local-development/docker-compose-reference.md)
- [Database Schema](docs/database/schema.md)
- [Health Monitoring](docs/features/health-monitoring.md)
- [Kill Triggers](docs/concepts/kill-triggers.md)

## Database Migrations

Migrations are in the `migrations/` folder. Run them in order:

```bash
# Via Supabase SQL Editor or psql
psql $DATABASE_URL -f migrations/001_add_client_profile_columns.sql
```

See [migrations.md](docs/database/migrations.md) for the full list.

## Development

```bash
# View logs
docker compose -f docker-compose.local.yml logs -f

# Restart a service
docker compose -f docker-compose.local.yml restart charm-api

# Stop all services
docker compose -f docker-compose.local.yml down
```

## Environment Setup

1. Copy `.env.example` to `.env.local`
2. Fill in required values (database, EmailBison API key)
3. Optional: Configure Slack webhooks for alerts

A separate `ENV-REFERENCE.md` document contains the complete variable reference with descriptions for each service.

## License

Proprietary - HireCharm Inc.

## Executive Dashboard

A modern, visually-rich health dashboard for Charm's email infrastructure.

**URL:** http://localhost:3006
**Location:** `/executive-dashboard`
**Client:** Charm (hardcoded)

Features:
- Real-time health metrics with gradient cards
- Kill velocity and breakdown charts
- 30-day volume history
- Provider performance analytics
- Auto-refresh every 5 minutes

See `/executive-dashboard/README.md` for details.
