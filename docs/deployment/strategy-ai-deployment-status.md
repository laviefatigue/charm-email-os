---
title: Strategy AI Deployment Status
created: 2026-01-16
updated: 2026-01-16
tags: [deployment, strategy-ai, claude-code, coolify, status]
---

# Strategy AI Deployment Status

**Last Updated:** 2026-01-16
**Status:** BLOCKED - Awaiting POSTGRES_PASSWORD

## Deployment Progress

### Completed Steps

| Step | Status | Notes |
|------|--------|-------|
| Push deployment files to GitHub | Done | Dockerfile, entrypoint, compose |
| Create charm-strategy-ai app in Coolify | Done | UUID: `n008gg4c88kgw4g48wcckk0k` |
| Configure environment variables | Done | All vars set except password retrieved |
| Build Docker image | Done | Built successfully in Coolify |
| Fix volume mount shadowing | Done | Moved claude binary to /usr/local/bin |
| Authenticate Claude Code on VPS | Done | SSH interactive session |
| Find Charm client in database | Done | ID: `4bd07dc0-059a-448b-b6f4-3275d0c104a9` |
| Create test onboarding submission | Done | ID: `9c1d635a-f69b-42f5-ba82-72fed49f4476` |
| Create strategy generation job | Done | ID: `1307a217-f1b0-434c-9eaa-c53f02511569` |

### Current Blocker

**Issue:** Cannot retrieve `POSTGRES_PASSWORD` from Coolify to run container manually.

**Attempted Solutions:**
1. `list_env_vars` MCP tool - Returns `***REDACTED***`
2. Coolify UI via Chrome DevTools - Values masked with bullets
3. Coolify Terminal - Input corruption issues
4. `get_application_raw` MCP tool - Doesn't include env vars

**Resolution Options:**
1. User provides password manually
2. SSH into VPS and retrieve from running container
3. Use Docker Compose deployment instead of manual run

### Pending Steps

| Step | Status | Notes |
|------|--------|-------|
| Run charm-strategy-ai container | Blocked | Needs password |
| Verify strategy suggestions in DB | Pending | After container runs |
| Verify results in frontend | Pending | After suggestions saved |

## Key Identifiers

### Coolify Applications

| Application | UUID | FQDN |
|-------------|------|------|
| charm-api | `ccssgc4gowsog04wck400o0w` | `http://ccssgc4gowsog04wck400o0w.31.97.142.123.sslip.io` |
| charm-frontend | `jskswosswg80cg8wwk8g8kww` | `http://jskswosswg80cg8wwk8g8kww.31.97.142.123.sslip.io` |
| charm-strategy-ai | `n008gg4c88kgw4g48wcckk0k` | N/A (batch job, no FQDN) |

### Test Data

| Entity | UUID |
|--------|------|
| Client (Charm) | `4bd07dc0-059a-448b-b6f4-3275d0c104a9` |
| Onboarding Submission | `9c1d635a-f69b-42f5-ba82-72fed49f4476` |
| Strategy Job | `1307a217-f1b0-434c-9eaa-c53f02511569` |

### Database Connection

| Property | Value |
|----------|-------|
| Host | `31.97.142.123` |
| Port | `5432` |
| Database | `postgres` |
| User | `postgres` |
| Password | `(retrieve from Coolify)` |

## Container Image

```
Image: n008gg4c88kgw4g48wcckk0k:latest
Built by: Coolify (from Dockerfile.strategy-ai)
```

## Command to Execute

Once password is available:

```bash
docker run --rm \
    -e POSTGRES_HOST=31.97.142.123 \
    -e POSTGRES_PORT=5432 \
    -e POSTGRES_DB=postgres \
    -e POSTGRES_USER=postgres \
    -e POSTGRES_PASSWORD='<PASSWORD>' \
    -v /root/.claude:/root/.claude \
    n008gg4c88kgw4g48wcckk0k:latest \
    4bd07dc0-059a-448b-b6f4-3275d0c104a9 \
    1307a217-f1b0-434c-9eaa-c53f02511569 \
    9c1d635a-f69b-42f5-ba82-72fed49f4476
```

## Files Created/Modified

### New Files

| File | Purpose |
|------|---------|
| `Dockerfile.strategy-ai` | Container definition |
| `docker-entrypoint.sh` | Entry script for Claude invocation |
| `docker-compose.strategy-ai.yml` | Compose config for Coolify |
| `run-strategy-job.sh` | Helper script for manual execution |
| `requirements-mcp.txt` | Python deps for MCP server |
| `strategy_mcp/server.py` | MCP server with 4 tools |
| `strategy_mcp_config.json` | MCP configuration |
| `.claude/skills/generate-strategy.md` | Claude skill instructions |

### Database Tables Created

- `strategy_generation_jobs` - Tracks Claude Code runs
- `strategy_suggestions` - Stores generated email variants
- `strategy_revision_requests` - Human feedback for regeneration

## Volume Mount Fix

**Problem:** Claude CLI installed at `/root/.claude/bin/claude` was being shadowed by credential volume mount.

**Solution:** In Dockerfile.strategy-ai:
```dockerfile
# CRITICAL FIX: Move claude binary to /usr/local/bin
RUN cp /root/.claude/bin/claude /usr/local/bin/claude && \
    chmod +x /usr/local/bin/claude
```

## Authentication Status

Claude Code authenticated on VPS via SSH:
- Session: Interactive docker run with bash
- Method: `claude /login` → Browser OAuth
- Credentials: Stored at `/root/.claude/` on VPS host
- Mounted into container via `-v /root/.claude:/root/.claude`

## Next Steps After Unblock

1. **Run container with password**
   ```bash
   ./run-strategy-job.sh 4bd07dc0-059a-448b-b6f4-3275d0c104a9 \
       1307a217-f1b0-434c-9eaa-c53f02511569 \
       9c1d635a-f69b-42f5-ba82-72fed49f4476
   ```

2. **Verify suggestions in database**
   ```sql
   SELECT * FROM strategy_suggestions
   WHERE job_id = '1307a217-f1b0-434c-9eaa-c53f02511569';
   ```

3. **Check job status**
   ```sql
   SELECT * FROM strategy_generation_jobs
   WHERE id = '1307a217-f1b0-434c-9eaa-c53f02511569';
   ```

4. **View in frontend**
   - Navigate to charm-frontend → Clients → Charm → Strategy tab
   - Verify CampaignSuggestions panel shows 3 variants

## Related Documentation

- [[ai-component]] - Container architecture
- [[strategy-worker-vps]] - Worker deployment on VPS
- [[../features/strategy-generation]] - Feature overview
- [[../architecture/claude-code-worker]] - Worker + MCP design

## Troubleshooting

### If container fails to start

```bash
# Check image exists
docker images | grep n008gg4c88kgw4g48wcckk0k

# Check claude is accessible
docker run --rm -v /root/.claude:/root/.claude \
    n008gg4c88kgw4g48wcckk0k:latest \
    bash -c "which claude && claude --version"
```

### If MCP server fails

```bash
# Test database connection
docker run --rm \
    -e POSTGRES_HOST=31.97.142.123 \
    -e POSTGRES_PASSWORD=<password> \
    n008gg4c88kgw4g48wcckk0k:latest \
    bash -c "python3 -c 'import psycopg2; print(\"OK\")'"
```

### If job stays in 'processing'

Check container logs or run interactively:
```bash
docker run -it --rm \
    -e POSTGRES_HOST=31.97.142.123 \
    ... \
    n008gg4c88kgw4g48wcckk0k:latest \
    bash
# Then run entrypoint manually
./docker-entrypoint.sh <client_id> <job_id>
```
