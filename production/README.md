# Charm Email OS - Production Infrastructure

This folder contains all production configurations, documentation, and MCP tools for managing Charm Email OS infrastructure.

## Infrastructure Overview

| Component | Provider | Purpose |
|-----------|----------|---------|
| DNS & Security | Cloudflare | Zero Trust Access, Tunnel, DDoS protection |
| Hosting | Coolify | Container orchestration on VPS |
| Domains | Hostinger/Porkbun/Dynadot | Domain registration for email infrastructure |
| VPS | Hostinger | Ubuntu server (187.77.19.81) |

## Production URLs

| Service | URL | Authentication |
|---------|-----|----------------|
| Frontend | https://app.wizardgrimoire.cloud | Google OAuth (@hirecharm.com) |
| API | https://api.wizardgrimoire.cloud | None (internal use) |
| Dashboard | https://dashboard.wizardgrimoire.cloud | Google OAuth (@hirecharm.com) |
| Coolify | https://coolify.wizardgrimoire.cloud | Google OAuth (@hirecharm.com) |

## Folder Structure

```
production/
├── README.md                 # This file
├── cloudflare/               # Cloudflare tunnel, DNS, Access configs
│   ├── README.md
│   ├── tunnel-config.yml     # Tunnel routing configuration
│   └── access-policies.md    # Zero Trust Access policies
├── coolify/                  # Coolify deployment configs
│   ├── README.md
│   └── services.md           # Running services documentation
├── mcp/                      # MCP tools for infrastructure management
│   ├── README.md
│   └── mcp-servers.json      # Combined MCP server configuration
├── slack/                    # Slack integrations
│   └── README.md             # Daily inbox audit notifications
├── environment/              # Environment variables reference
│   └── README.md
└── security/                 # Security procedures
    └── deployment-procedures.md
```

## Deployment (CRITICAL)

**Auto-deploy is DISABLED on all apps.** Manual deployment required after pushing to GitHub.

### Why Manual?
All 7 apps share the same monorepo. With auto-deploy, pushing ANY change rebuilt ALL 7 apps, overloading the VPS.

### Deployment Steps
1. **Push code** to GitHub
2. **Identify which apps changed** based on your commit
3. **Deploy ONLY those apps** using Coolify MCP:
   ```
   mcp__coolify__deploy uuid="<app-uuid>" confirm=true
   ```
4. **Wait for build to complete** (1-5 min) before testing

### App UUIDs
| App | UUID | Deploy When |
|-----|------|-------------|
| charm-api | `nckgggwww8sggg0kc4wo00o8` | `/api/**` changes |
| charm-frontend | `qw88skgwgwgk8g44c0g4wgks` | `/charm-email-os/**` changes |
| emailbison-sync | `l4g44o00s4cccg804osswgcc` | `emailbison_sync_worker.py`, `/sync_modules/**` |
| hypertide-worker | `e0go4ocg8cggw08kowocok4g` | `hypertide_worker.py` |
| domain-worker | `u4oo8o0wocsgss8o4cs4g4oc` | `domain_worker.py` |
| price-checker | `rcckg8k84os8c400kwk4ck04` | `price_checker_worker.py` |
| executive-dashboard | `gkkgsscwck0o80gwkcsogcow` | `/executive-dashboard/**` |

See [coolify/services.md](coolify/services.md) for full deployment workflow.

## Quick Commands

### Health Checks
```bash
# API health
curl https://api.wizardgrimoire.cloud/health

# All services (via Coolify MCP)
# Use /coolify-status skill
```

### Database Migrations
```
# See security/deployment-procedures.md for full details
# Recommended: Coolify Web Terminal → postgres → Terminal → psql -U charm -d postgres
```

### MCP Tools Available
- **cloudflare** - Manage DNS, tunnel, Access policies
- **coolify** - Deploy, logs, status checks
- **hostinger-api** - Domain and VPS management
- **chrome-devtools** - Browser automation for Coolify UI

## Security Architecture

```
                    ┌─────────────────┐
                    │   Cloudflare    │
                    │  Zero Trust     │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
    ┌─────────▼───┐  ┌───────▼─────┐  ┌─────▼──────┐
    │ app.wizard  │  │ api.wizard  │  │ coolify.   │
    │ grimoire    │  │ grimoire    │  │ wizard...  │
    │ .cloud      │  │ .cloud      │  │            │
    └──────┬──────┘  └──────┬──────┘  └─────┬──────┘
           │                │               │
           └────────────────┼───────────────┘
                            │
                    ┌───────▼───────┐
                    │   Cloudflare  │
                    │    Tunnel     │
                    │ (cloudflared) │
                    └───────┬───────┘
                            │
                    ┌───────▼───────┐
                    │     VPS       │
                    │ 187.77.19.81  │
                    │  UFW: SSH only│
                    └───────┬───────┘
                            │
                    ┌───────▼───────┐
                    │    Coolify    │
                    │   (port 80)   │
                    └───────────────┘
```

## Key Principles

1. **IP Never Exposed** - All traffic through Cloudflare Tunnel
2. **Authentication Required** - Google OAuth for admin interfaces
3. **API Public** - API endpoint has no Access (needed for frontend fetch)
4. **Firewall Locked** - VPS only accepts SSH (port 22)
5. **Separation** - Production configs here, dev configs in root
