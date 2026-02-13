---
title: Coolify Deployment Platform (Deprecated)
created: 2026-01-16
updated: 2026-02-11
tags: [infrastructure, coolify, deployment, docker, deprecated]
---

# Coolify (DEPRECATED)

> **⚠️ DEPRECATED**: Coolify/VPS deployments are no longer active. The Charm Email OS system now runs entirely on **localhost via Docker**. This documentation is preserved for legacy reference only. Do not deploy to Coolify unless explicitly requested.
>
> **Use instead**: [[../local-development/index]] for the current localhost-first setup.

---

*Legacy documentation below - for reference only*

Self-hosted PaaS for deploying and managing Docker containers.

## Service Details

| Property | Value |
|----------|-------|
| Dashboard | `https://panel.laviefatigue.com` |
| Access Method | Web UI + Coolify MCP Server |
| VPS IP | `31.97.142.123` |

## Deployed Applications

### Charm Email OS (7 services)

| Application | UUID | Purpose |
|-------------|------|---------|
| charm-api | `ccssgc4gowsog04wck400o0w` | FastAPI backend |
| charm-frontend | `jskswosswg80cg8wwk8g8kww` | Next.js frontend |
| charm-purchase-worker | `xo4o4wcco0scgs8gskggw00k` | HyperTide automation daemon |
| charm-domain-worker | `ew8cw0o00ksws8gg4gggws4k` | Domain generation worker |
| charm-price-checker | `ewskcsk0s0gw0kgc08kkoccg` | Domain pricing service |
| charm-spintax-worker | `roccs4g0gwkcs8ws8k8kgog4` | Spintax generation worker |
| charm-strategy-worker | `qwgc8ws0wwk0wgg4s48ssg0w` | Strategy AI worker |

### Other Applications (14 apps)

| Application | UUID | Status |
|-------------|------|--------|
| emailbison-mcp | `zcgkoskw0g8kswc8ss4gscgw` | running |
| hirecharm-onboarding-test | `gc4cckco80okc4o8wkw44ws0` | running |
| ownrbl-ceo-dashboard | `kgc08cs8oc0c0ko44w0k4c0s` | running |
| ownrbl-serve-all | `ekco8w0swow8kwk0ksc80soc` | running |
| fathom-extractor | `xccso8844ok0skoswow0wk4c` | running |
| spout-dashboard | `y40g4s8gsoo8sgckkkoo4gcg` | running |
| gtm-overview | `xo0sc8ow8wcssg4k0cckkg0k` | running |
| suspension-direct | `xcg84k4044sck4c4o48k40ow` | running |
| nextiva | `bo0sokwokkwkc4cgg08cg80o` | running |
| mac-cosmetics | `aso8c48gkccwc0sg44ks8s8w` | running |
| hurricane-pool-filters | `x8scs8w4wo80ooswkw8sc4kc` | running |
| merchcamp-proposal | `lo0wcgg0gsco0ko0gw04go4c` | running |
| aquaflex-proposal | `iwc4cg4ogcsoo8ck8cgg00kg` | running |
| hurricane-pool-filters-proposal | `bs0kw8co08wcgock8wk0c8gc` | **stopped** |

## Deployment Process

### Auto-Deploy (push to master)

Only **charm-api** and **charm-frontend** auto-deploy on push to master. All 5 workers have auto-deploy disabled (pinned to a specific commit SHA) to prevent unnecessary builds.

| Service | Auto-Deploy | Trigger |
|---------|-------------|---------|
| charm-api | **ON** | Push to master |
| charm-frontend | **ON** | Push to master |
| charm-purchase-worker | OFF | Manual only |
| charm-domain-worker | OFF | Manual only |
| charm-price-checker | OFF | Manual only |
| charm-spintax-worker | OFF | Manual only |
| charm-strategy-worker | OFF | Manual only |

### Manual Worker Deployment

When a worker's code changes, trigger it manually via Coolify MCP:

```python
# Deploy a specific worker
mcp__coolify__trigger_deployment(
    application_uuid="<worker-uuid>",
    confirm=True
)
```

**Worker UUIDs for manual trigger:**

| Worker | UUID |
|--------|------|
| purchase-worker | `xo4o4wcco0scgs8gskggw00k` |
| domain-worker | `ew8cw0o00ksws8gg4gggws4k` |
| price-checker | `ewskcsk0s0gw0kgc08kkoccg` |
| spintax-worker | `roccs4g0gwkcs8ws8k8kgog4` |
| strategy-worker | `qwgc8ws0wwk0wgg4s48ssg0w` |

When shared code changes (e.g. common libraries, shared requirements.txt), deploy workers **sequentially** — not in parallel — to avoid disk pressure.

### Other Coolify MCP Commands

```python
# Check deployment status
mcp__coolify__get_deployment_details(
    deployment_uuid="..."
)

# View application logs
mcp__coolify__get_application_logs(
    application_uuid="ccssgc4gowsog04wck400o0w"
)
```

## Environment Variables

### charm-purchase-worker

See [[../deployment/purchase-worker-coolify]] for full ENV var reference. Key groups:

| Group | Variables |
|-------|----------|
| Database | `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` |
| Worker | `POLL_INTERVAL`, `JOB_TIMEOUT`, `CLAUDE_ACCOUNT`, `ALERT_WEBHOOK_URL` |
| Hypertide | `HYPERTIDE_EMAIL`, `HYPERTIDE_PASSWORD` |
| EmailBison | `BISON_USERNAME`, `BISON_PASSWORD`, `BISON_URL`, `EMAILBISON_API_KEY` |
| Stripe | `STRIPE_CARD_NUMBER`, `STRIPE_CARD_EXP`, `STRIPE_CARD_CVC`, `STRIPE_CARD_ZIP` |

### charm-api
| Variable | Purpose |
|----------|---------|
| `POSTGRES_HOST` | Supabase connection host |
| `POSTGRES_PORT` | Database port (6543) |
| `POSTGRES_DB` | Database name (postgres) |
| `POSTGRES_USER` | Database user |
| `POSTGRES_PASSWORD` | Database password |
| `CORS_ORIGINS` | Allowed CORS origins |

### charm-frontend
| Variable | Purpose |
|----------|---------|
| `NEXT_PUBLIC_API_URL` | Backend API URL |

## Docker Configuration

### API Dockerfile Location
`D:\Work\charm-email-os\api\Dockerfile`

### Frontend Dockerfile Location
`D:\Work\charm-email-os\charm-email-os\Dockerfile`

## Monitoring

- View logs: Coolify dashboard → Application → Logs
- View deployments: Coolify dashboard → Application → Deployments
- Health check: Application status in dashboard

## Disk Management & Deployment Optimization

### Current Server Settings (as of 2026-02-02)

| Setting | Value | Impact |
|---------|-------|--------|
| `concurrent_builds` | 2 | Max 2 Docker builds at once |
| `deployment_queue_limit` | 25 | Up to 25 queued deploys |
| `delete_unused_volumes` | **true** | Orphan volumes auto-removed |
| `delete_unused_networks` | **true** | Dead networks auto-removed |
| `docker_cleanup_threshold` | 80 | Cleanup triggers at 80% disk |
| `docker_cleanup_frequency` | `0 */6 * * *` | Every 6 hours |
| `force_docker_cleanup` | true | Forces cleanup when threshold hit |

### Why Disk Can Fill Up

1. **21 apps = 21+ Docker images** — each with multi-layer builds
2. ~~Unused volumes never cleaned~~ — **FIXED 2026-02-02**: `delete_unused_volumes` set to `true`
3. ~~7 Charm services all rebuild on every push~~ — **FIXED 2026-02-02**: Only API + frontend auto-deploy; workers are manual
4. **Failed builds leave artifacts** — partial images, dangling layers, and build cache from failed deploys remain on disk
5. **Build cache unbounded** — multi-stage builds (frontend has 3 stages) create intermediate layers that accumulate
6. ~~Cleanup only once daily~~ — **FIXED 2026-02-02**: Now runs every 6 hours

### Emergency Cleanup (SSH)

When disk is full and builds are failing:

```bash
# Check current disk usage
df -h /
docker system df

# Remove all stopped containers, unused images, build cache, dangling volumes
docker system prune -a --volumes -f

# Verify cleanup
df -h /
docker system df
```

### Reducing Per-Deployment Consumption

#### 1. Auto-deploy disabled on workers (done 2026-02-02)

All 5 workers have `git_commit_sha` pinned to a specific commit instead of `HEAD`, disabling auto-deploy. Only `charm-api` and `charm-frontend` auto-deploy on push to master. See [[#Manual Worker Deployment]] for how to deploy workers when needed.

#### 2. Stop or remove unused applications

The `hurricane-pool-filters-proposal` app is already stopped but still has images on disk. Review other proposal sites (7 total) — if they're no longer needed, remove them entirely to free images and volumes.

**Candidates for removal review:**
- `hurricane-pool-filters-proposal` (already stopped)
- Any completed proposal sites that are no longer client-facing

#### 3. Keep Docker images lean

The frontend Dockerfile already uses multi-stage builds with `node:20-alpine` (good). Ensure other services also:
- Use Alpine base images where possible
- Use multi-stage builds to separate build-time deps from runtime
- Add a `.dockerignore` to exclude `node_modules/`, `.next/`, `__pycache__/`, test files, docs, etc.

#### 4. One push, one wait

Never trigger manual deployments on top of webhook-triggered ones. Push once, wait for the webhook build to complete, then verify. Queuing multiple deploys wastes build slots and disk.

### Monitoring

Check disk usage periodically:

```bash
# Via SSH
df -h /
docker system df
docker image ls --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}" | sort -k3 -h

# Via Coolify MCP
mcp__coolify__execute_diagnostic(target_type="application", target_uuid="...")
```

## Related

- [[supabase]] - Database hosting
- [[vps]] - Server hosting Coolify
- [[../architecture/api-endpoints]] - API routes deployed here
