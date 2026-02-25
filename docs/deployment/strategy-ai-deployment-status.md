---
title: Strategy AI Deployment Status
created: 2026-01-16
updated: 2026-01-16
tags: [deployment, strategy-ai, claude-code, coolify, status]
---

# Strategy AI Deployment Status

**Last Updated:** 2026-01-19
**Status:** BLOCKED - Claude Code OAuth token expired

## Deployment Progress

### Completed Steps

| Step | Status | Notes |
|------|--------|-------|
| Push deployment files to GitHub | Done | Dockerfile, entrypoint, compose |
| Create charm-strategy-ai app in Coolify | Done | UUID: `n008gg4c88kgw4g48wcckk0k` |
| Configure environment variables | Done | Password: `ZEN3hMv6UpA0hfd8OcAUSiJWgpY33q5V` |
| Fix volume mount shadowing | Done | Moved claude binary to /usr/local/bin |
| Authenticate Claude Code on VPS | Done | SSH interactive session |
| Find Charm client in database | Done | ID: `4bd07dc0-059a-448b-b6f4-3275d0c104a9` |
| Create test onboarding submission | Done | ID: `9c1d635a-f69b-42f5-ba82-72fed49f4476` |
| Create strategy generation job | Done | ID: `1307a217-f1b0-434c-9eaa-c53f02511569` |
| Create Foam documentation | Done | This file |

### Current Blockers

#### 1. Coolify Deployment Architecture Mismatch (RESOLVED)

**Issue:** Coolify deployments always fail with health check error.

**Error Message:**
```
template parsing error: template: :1:13: executing "" at <.State.Health.Status>:
map has no entry for key "Health"
```

**Root Cause:** charm-strategy-ai is a **batch job container** that exits after execution, but Coolify expects a long-running web service with health checks.

**Solution:** This is expected behavior. Use Coolify only for building the Docker image. Run the container manually with `docker run` when a strategy job needs execution.

#### 2. Claude Code OAuth Token Expired (ACTION REQUIRED)

**Issue:** Claude Code OAuth token has expired.

**Error Message:**
```
API Error: 401 {"type":"error","error":{"type":"authentication_error",
"message":"OAuth token has expired. Please obtain a new token or refresh your existing token."}}
```

**Root Cause:** The Claude Code authentication performed earlier has expired. OAuth tokens have a limited lifespan.

**Solution:** Re-authenticate Claude Code via SSH with an interactive session.

### Re-Authentication Instructions

SSH into the VPS and run:

```bash
# 1. Start an interactive container shell
docker run -it --rm \
    -v /var/claude-credentials:/home/claude/.claude \
    n008gg4c88kgw4g48wcckk0k:latest \
    bash

# 2. Inside the container, run login
claude /login

# 3. Follow the OAuth flow in browser (copy the URL shown)
# 4. After authentication completes, exit the container
exit
```

### Previous Blocker (RESOLVED)

**Issue:** Coolify build failed. Docker image did not exist.

**Solution:** Built the image manually. Image now exists at `n008gg4c88kgw4g48wcckk0k:latest`.

### Manual Build Instructions

SSH into the VPS and run:

```bash
# 1. Clone the repo (use GitHub token for private repo)
cd /tmp
rm -rf charm-strategy-build
git clone --depth 1 https://<GITHUB_TOKEN>@github.com/laviefatigue/charm-email-os.git charm-strategy-build

# 2. Build the Docker image
cd charm-strategy-build
docker build -f Dockerfile.strategy-ai -t charm-strategy-ai:latest .

# 3. Run the strategy generation
docker run --rm \
    -e POSTGRES_HOST=31.97.142.123 \
    -e POSTGRES_PORT=5432 \
    -e POSTGRES_DB=postgres \
    -e POSTGRES_USER=postgres \
    -e POSTGRES_PASSWORD='ZEN3hMv6UpA0hfd8OcAUSiJWgpY33q5V' \
    -v /root/.claude:/root/.claude \
    charm-strategy-ai:latest \
    4bd07dc0-059a-448b-b6f4-3275d0c104a9 \
    1307a217-f1b0-434c-9eaa-c53f02511569 \
    9c1d635a-f69b-42f5-ba82-72fed49f4476
```

### Pending Steps

| Step | Status | Notes |
|------|--------|-------|
| Re-authenticate Claude Code | **ACTION REQUIRED** | Via SSH - OAuth token expired |
| Run charm-strategy-ai container | Pending | After re-authentication |
| Verify strategy suggestions in DB | Pending | After container runs |
| Verify results in frontend | Pending | After suggestions saved |

### Issues Fixed in This Session

| Issue | Solution | Status |
|-------|----------|--------|
| Docker image missing | Built manually via Coolify terminal | Fixed |
| Skills directory empty after copy | Copied skill file to host volume | Fixed |
| `/generate-strategy` unknown skill | Changed to direct prompt (not /skill-name) | Fixed |
| OAuth token expired | Requires interactive SSH re-auth | **BLOCKER** |

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
| Password | `ZEN3hMv6UpA0hfd8OcAUSiJWgpY33q5V` |

## Container Image

```
Image: n008gg4c88kgw4g48wcckk0k:latest
Built by: Coolify (from Dockerfile.strategy-ai)
```

### Important Architecture Note

**This is a BATCH JOB container, NOT a web service.**

- The container is designed to run once with arguments, execute Claude Code, and exit
- Coolify deployments will always show "Failed" because the container exits immediately
- This is expected behavior - use Coolify only for building the image
- To execute a strategy job, run the container manually via `docker run`

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
