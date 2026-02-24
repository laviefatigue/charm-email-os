# Charm Executive Dashboard

Modern, executive-style health dashboard for Charm email infrastructure. Built with Next.js 14, TypeScript, and Recharts.

## Quick Start

### Deploy with Docker Compose

The executive dashboard is integrated into the Charm Email OS Docker stack.

```bash
# Start all services including executive dashboard
cd D:\Work\charm-email-os
docker compose -f docker-compose.local.yml up -d

# View logs
docker compose -f docker-compose.local.yml logs -f executive-dashboard

# Rebuild after code changes
docker compose -f docker-compose.local.yml up -d --build executive-dashboard
```

**Access:** http://localhost:3006

---

## Features

- **Key Metrics Cards** - Total inboxes, health score, survival rate, domain status
- **Health Visualizations** - Gauge, distribution bars, lifecycle breakdown
- **Trend Analysis** - Kill velocity, kill breakdown, 30-day volume history
- **Provider Analytics** - Performance metrics by email provider
- **Auto-refresh** - Updates every 5 minutes
- **Responsive Design** - Works on all devices

---

## Configuration

Hardcoded to **Charm** client (ID: `4bd07dc0-059a-448b-b6f4-3275d0c104a9`)

**File:** `src/lib/config.ts`

---

## Troubleshooting

### Dashboard won't load

```bash
# Check API
curl http://localhost:8000/api/health/infrastructure/4bd07dc0-059a-448b-b6f4-3275d0c104a9

# Check logs
docker compose -f docker-compose.local.yml logs executive-dashboard
```

### Rebuild from scratch

```bash
docker compose -f docker-compose.local.yml down
docker rmi charm-executive-dashboard
docker compose -f docker-compose.local.yml up -d --build executive-dashboard
```

---

**Port:** 3006
**Status:** Production Ready ✅
