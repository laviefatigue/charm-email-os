---
title: Troubleshooting Guide
created: 2026-02-10
updated: 2026-02-10
tags: [troubleshooting, debugging, errors]
---

# Troubleshooting Guide

Common issues and solutions when working with the local development environment.

## Quick Diagnostics

```bash
# Check all containers
docker compose -f docker-compose.local.yml ps

# View recent logs
docker compose -f docker-compose.local.yml logs --tail=50

# Check container health
docker inspect charm-api --format='{{.State.Health.Status}}'
docker inspect charm-frontend --format='{{.State.Health.Status}}'
docker inspect charm-postgres --format='{{.State.Health.Status}}'
```

## Database Issues

### Port 5433 Already In Use

**Symptom**: Container won't start, port conflict error

**Solution**:
```bash
# Find what's using the port
netstat -an | findstr 5433

# Option 1: Kill the process using the port
# Option 2: Change the port in docker-compose.local.yml
ports:
  - "5434:5432"  # Use 5434 instead
```

### Database Won't Start

**Symptom**: `charm-postgres` container exits immediately

**Solution**:
```bash
# Check logs
docker logs charm-postgres

# Reset database volume
docker compose -f docker-compose.local.yml down -v
docker compose -f docker-compose.local.yml up -d
```

### Schema Missing

**Symptom**: API returns "relation does not exist" errors

**Solution**:
```bash
# Verify schema was applied
docker exec -it charm-postgres psql -U postgres -d postgres -c "\dt"

# If tables missing, reinitialize
docker compose -f docker-compose.local.yml down -v
docker compose -f docker-compose.local.yml up -d
```

### Seed Data Missing

**Symptom**: Charm client not found

**Solution**:
```bash
# Check if client exists
docker exec -it charm-postgres psql -U postgres -d postgres -c "SELECT id, name FROM clients;"

# If missing, reset database
docker compose -f docker-compose.local.yml down -v
docker compose -f docker-compose.local.yml up -d
```

## API Issues

### API Health Check Fails

**Symptom**: `charm-api` shows unhealthy

**Solution**:
```bash
# Check API logs
docker logs charm-api

# Common cause: Database not ready
# Solution: Restart API after database is healthy
docker compose -f docker-compose.local.yml restart charm-api
```

### API Returns 500 Errors

**Symptom**: Internal server errors on API calls

**Solution**:
```bash
# Check API logs for error details
docker logs charm-api --tail=100

# Common causes:
# - Database connection issues
# - Missing environment variables
# - Schema mismatch
```

### CORS Errors

**Symptom**: Frontend gets blocked by CORS

**Solution**: Verify CORS_ORIGINS in docker-compose.local.yml:
```yaml
environment:
  - CORS_ORIGINS=["http://localhost:3000","http://charm-frontend:3000"]
```

## Frontend Issues

### Frontend Build Fails

**Symptom**: `charm-frontend` container won't build

**Solution**:
```bash
# Rebuild from scratch
docker compose -f docker-compose.local.yml build --no-cache charm-frontend
docker compose -f docker-compose.local.yml up -d charm-frontend
```

### Frontend Can't Connect to API

**Symptom**: Network errors in browser console

**Solution**:
```bash
# Verify API is running
curl http://localhost:8000/health

# Check NEXT_PUBLIC_API_URL
docker exec charm-frontend printenv | grep API
```

### Hot Reload Not Working

**Symptom**: Changes don't reflect immediately

**Solution**: Use hybrid mode for hot reload:
```bash
# Stop frontend container
docker compose -f docker-compose.local.yml stop charm-frontend

# Run frontend locally
cd charm-email-os
npm run dev
```

## Worker Issues

### Worker Not Processing Jobs

**Symptom**: Jobs stay in `pending` status

**Solution**:
```bash
# Check worker is running
docker ps | grep worker

# Check worker logs
docker logs charm-strategy-worker --tail=50

# Verify OAuth is valid
docker exec -it charm-strategy-worker claude /status
```

### "Invalid API Key" Error

**Symptom**: Worker logs show authentication error

**Solution**:
```bash
# Re-authenticate
docker exec -it charm-strategy-worker claude /login
# Follow OAuth flow in browser
```

### MCP Server Connection Failed

**Symptom**: Worker can't connect to MCP server

**Solution**:
```bash
# Check MCP server is bundled correctly
docker exec -it charm-strategy-worker ls /app/strategy_mcp/

# Verify MCP configuration
docker exec -it charm-strategy-worker cat /app/.claude/mcp.json
```

## Docker Issues

### Container Keeps Restarting

**Symptom**: Container in restart loop

**Solution**:
```bash
# Check logs for error
docker logs <container-name>

# Remove restart policy temporarily
docker update --restart=no <container-name>
```

### Out of Disk Space

**Symptom**: Build fails with disk space error

**Solution**:
```bash
# Clean up Docker resources
docker system prune -a --volumes

# Check disk usage
docker system df
```

### Network Issues

**Symptom**: Containers can't communicate

**Solution**:
```bash
# Verify network exists
docker network ls | grep charm

# Recreate network
docker compose -f docker-compose.local.yml down
docker compose -f docker-compose.local.yml up -d
```

## Common Error Messages

### "connection refused"

Database isn't ready or wrong port.

```bash
# Verify database is running
docker ps | grep postgres

# Check port mapping
docker port charm-postgres
```

### "relation does not exist"

Schema not applied or wrong database.

```bash
# Verify tables exist
docker exec -it charm-postgres psql -U postgres -d postgres -c "\dt"
```

### "CORS error"

Frontend origin not in allowed list.

```bash
# Check API CORS config
docker exec charm-api printenv | grep CORS
```

### "Invalid API key"

Claude Code OAuth expired.

```bash
docker exec -it <worker-container> claude /login
```

### "Module not found"

Missing Python/Node dependencies.

```bash
# Rebuild container
docker compose -f docker-compose.local.yml build --no-cache <service>
```

## Full Reset

When all else fails:

```bash
# Stop everything
docker compose -f docker-compose.local.yml down -v

# Remove all related images
docker images | grep charm | awk '{print $3}' | xargs docker rmi -f

# Rebuild and start
docker compose -f docker-compose.local.yml up -d --build

# Wait for healthy
docker compose -f docker-compose.local.yml ps
```

## Getting Help

1. Check container logs: `docker logs <container-name>`
2. Check this documentation
3. Review [[development-workflow]] for correct procedures
4. Check [[architecture]] for system understanding

## Related

- [[index]] - Local development hub
- [[development-workflow]] - Correct development procedures
- [[architecture]] - System architecture
