---
title: VPS Server Configuration
created: 2026-01-16
updated: 2026-02-02
tags: [infrastructure, vps, server, disk-management]
---

# VPS Server

Hetzner VPS hosting the Coolify instance and all deployed applications.

## Server Details

| Property | Value |
|----------|-------|
| IP Address | `31.97.142.123` |
| Provider | Hetzner |
| Software | Coolify (Docker-based PaaS) |

## Domain Resolution

Uses sslip.io for automatic DNS resolution:
- `*.31.97.142.123.sslip.io` → `31.97.142.123`

### Application URLs

| Application | URL Pattern |
|-------------|-------------|
| charm-api | `http://{uuid}.31.97.142.123.sslip.io` |
| charm-frontend | `http://{uuid}.31.97.142.123.sslip.io` |

## Network Configuration

| Port | Service |
|------|---------|
| 80 | HTTP (Coolify proxy) |
| 443 | HTTPS (Coolify proxy) |
| 22 | SSH |

## Access

- **Coolify Dashboard**: `https://panel.laviefatigue.com`
- **SSH**: Available if needed (contact admin)

## Resource Usage

As of 2026-01-30, the VPS hosts:
- **21 Docker applications** (20 running, 1 stopped)
- **1 PostgreSQL database**
- **2 Coolify services**

### Disk Usage Concerns

The server has experienced disk exhaustion from accumulated Docker artifacts. Key consumers:
- Docker images (21 apps × multiple layers each)
- Docker build cache (multi-stage builds)
- Docker volumes from old containers
- Failed deployment artifacts

See [[coolify#Disk Management & Deployment Optimization]] for cleanup procedures and prevention settings.

### Quick Disk Check (SSH)

```bash
df -h /                    # Overall disk usage
docker system df           # Docker-specific breakdown
docker system df -v        # Detailed per-image sizes
```

## Security

- Coolify manages container isolation
- Each application runs in its own Docker container
- Environment variables stored securely in Coolify

## Related

- [[coolify]] - PaaS running on this VPS
- [[supabase]] - External database (not on this VPS)
