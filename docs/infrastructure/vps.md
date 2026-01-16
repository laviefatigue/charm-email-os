---
title: VPS Server Configuration
created: 2026-01-16
updated: 2026-01-16
tags: [infrastructure, vps, server]
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

## Security

- Coolify manages container isolation
- Each application runs in its own Docker container
- Environment variables stored securely in Coolify

## Related

- [[coolify]] - PaaS running on this VPS
- [[supabase]] - External database (not on this VPS)
