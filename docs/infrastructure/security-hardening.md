---
title: Security Hardening Guide
created: 2026-01-26
updated: 2026-01-26
tags: [infrastructure, security, hardening]
---

# Security Hardening Guide

Security assessment and hardening recommendations for Charm Email OS infrastructure.

## Current Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                       INTERNET                                       │
└───────────────────────────┬─────────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
        ▼                   ▼                   ▼
   [Port 80/443]       [Port 22]          [Port 5432?]
   HTTP/HTTPS            SSH              PostgreSQL
        │                   │                   │
┌───────┴───────────────────┴───────────────────┴─────────────────────┐
│                    VPS (31.97.142.123)                               │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │                         Coolify                                 │ │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────────────────┐   │ │
│  │  │  charm-api  │ │charm-frontend│ │    AI Workers (x3)     │   │ │
│  │  │  (FastAPI)  │ │  (Next.js)   │ │ strategy/domain/spintax│   │ │
│  │  └─────────────┘ └─────────────┘ └─────────────────────────┘   │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                      │
│  Panel: panel.laviefatigue.com (Coolify Admin)                      │
└──────────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    Supabase (External)                                │
│                 PostgreSQL Database                                   │
└──────────────────────────────────────────────────────────────────────┘
```

## Threat Model

### Attack Vectors

| Vector | Risk Level | Current Status | Notes |
|--------|------------|----------------|-------|
| IP Discovery | Medium | Exposed via sslip.io | IP visible in URLs |
| Port Scanning | High | Unknown | Need to verify open ports |
| Coolify Panel | Critical | Protected by auth | Single point of compromise |
| API Endpoints | Medium | No auth layer | Public access to API |
| Man-in-Middle | Medium | HTTP only | No TLS on app URLs |
| Database Direct | High | Check firewall | PostgreSQL port exposure |
| Container Escape | Low | Docker isolation | Coolify managed |
| Credential Theft | Medium | Env vars in containers | Standard practice |

### Assets to Protect

1. **Critical**
   - Coolify admin panel credentials
   - PostgreSQL database credentials
   - Claude OAuth tokens
   - Porkbun/Dynadot API keys

2. **High**
   - Client data (emails, strategies)
   - Campaign configurations
   - Domain portfolio data

3. **Medium**
   - Application source code
   - Worker configurations
   - Deployment settings

## Hardening Checklist

### Phase 1: Immediate (No Performance Impact)

#### 1.1 Verify Port Exposure

```bash
# Run from external machine (not the VPS)
nmap -sT -p 22,80,443,5432,6379,8080 31.97.142.123
```

**Expected result**: Only 22, 80, 443 should be open.

**Action if PostgreSQL (5432) is exposed**:
```bash
# On VPS via Coolify Terminal
sudo ufw deny 5432
sudo ufw status
```

#### 1.2 Enable HTTPS on Coolify Apps

| Application | Current | Target |
|-------------|---------|--------|
| charm-api | HTTP | HTTPS (Let's Encrypt) |
| charm-frontend | HTTP | HTTPS (Let's Encrypt) |
| Workers | Internal only | No change needed |

**Steps in Coolify**:
1. Go to Application > Configuration
2. Add proper domain (not sslip.io)
3. Enable "Generate SSL Certificate"
4. Coolify auto-provisions Let's Encrypt

#### 1.3 Firewall Configuration

```bash
# UFW configuration for VPS
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP (redirect to HTTPS)
sudo ufw allow 443/tcp   # HTTPS
sudo ufw enable
```

#### 1.4 SSH Hardening

Edit `/etc/ssh/sshd_config`:
```
PermitRootLogin no
PasswordAuthentication no
PubkeyAuthentication yes
MaxAuthTries 3
```

### Phase 2: Domain & DNS (Minor Setup Time)

#### 2.1 Use Real Domain Instead of sslip.io

**Current (Exposes IP)**:
```
http://ccssgc4gowsog04wck400o0w.31.97.142.123.sslip.io
```

**Target (Hides IP behind proxy)**:
```
https://api.charm-email.com
https://app.charm-email.com
```

**Benefits**:
- IP hidden behind DNS
- Can add Cloudflare proxy for DDoS protection
- Professional appearance
- Easier SSL management

#### 2.2 Cloudflare Configuration (Optional but Recommended)

| Setting | Value | Purpose |
|---------|-------|---------|
| Proxy Status | Proxied (orange cloud) | Hide origin IP |
| SSL/TLS | Full (Strict) | End-to-end encryption |
| Always Use HTTPS | On | Force HTTPS |
| WAF | On (free tier) | Block common attacks |
| Rate Limiting | 100 req/min per IP | Prevent abuse |

### Phase 3: Application Security (Development Required)

#### 3.1 API Authentication Options

**Option A: API Key (Simple, Low Overhead)**
```python
# middleware/auth.py
from fastapi import Header, HTTPException

async def verify_api_key(x_api_key: str = Header(...)):
    if x_api_key != settings.API_KEY:
        raise HTTPException(status_code=401)
```

Performance Impact: ~1ms per request

**Option B: JWT Tokens (More Secure)**
```python
# For user-facing endpoints
from fastapi_jwt_auth import AuthJWT

@app.get("/protected")
def protected(Authorize: AuthJWT = Depends()):
    Authorize.jwt_required()
    return {"status": "authenticated"}
```

Performance Impact: ~5ms per request

**Recommendation**: Use API keys for internal/worker communication, JWT for user-facing.

#### 3.2 Rate Limiting

```python
# Using slowapi
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@app.get("/api/strategy/generate")
@limiter.limit("10/minute")
async def generate_strategy():
    ...
```

Performance Impact: Negligible (in-memory check)

#### 3.3 Input Validation

Already using Pydantic models - ensure all endpoints validate:

```python
class ClientCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr

    class Config:
        extra = "forbid"  # Reject unknown fields
```

### Phase 4: Infrastructure Hardening

#### 4.1 Container Security

**Current Dockerfile Pattern** (Good):
```dockerfile
# Running as non-root user
RUN useradd -m -s /bin/bash claude
USER claude
```

**Additional Hardening**:
```dockerfile
# Read-only filesystem where possible
# Add to docker-compose or Coolify config
read_only: true
tmpfs:
  - /tmp
```

#### 4.2 Secrets Management

**Current**: Environment variables in Coolify
**Better**: Use Coolify's "Secrets" feature with encryption at rest

| Secret | Current Location | Recommendation |
|--------|------------------|----------------|
| POSTGRES_PASSWORD | Env var | Coolify Secret |
| PORKBUN_API_KEY | .env file | Coolify Secret |
| CLAUDE_TOKEN | Volume mount | Keep as-is (auto-refresh) |

#### 4.3 Network Segmentation

```
┌─────────────────────────────────────────────────────┐
│                  Coolify Network                     │
│                                                      │
│  ┌──────────────┐     ┌──────────────┐             │
│  │   Frontend   │────▶│     API      │             │
│  │  (public)    │     │  (internal)  │             │
│  └──────────────┘     └──────┬───────┘             │
│                              │                      │
│         ┌────────────────────┼────────────────┐    │
│         ▼                    ▼                ▼    │
│  ┌────────────┐    ┌────────────┐    ┌──────────┐ │
│  │  Strategy  │    │   Domain   │    │  Spintax │ │
│  │   Worker   │    │   Worker   │    │  Worker  │ │
│  └────────────┘    └────────────┘    └──────────┘ │
│         │                    │                │    │
│         └────────────────────┴────────────────┘    │
│                              │                      │
└──────────────────────────────┼──────────────────────┘
                               ▼
                    [External: Supabase DB]
```

Workers should NOT be accessible from internet - verify no FQDN assigned.

### Phase 5: Monitoring & Alerting

#### 5.1 Log Aggregation

**Coolify provides**:
- Container logs (viewable in UI)
- Deployment logs

**Add for security monitoring**:
```bash
# Install fail2ban for SSH protection
sudo apt install fail2ban
sudo systemctl enable fail2ban
```

#### 5.2 Alerting Rules

| Event | Alert Method | Priority |
|-------|--------------|----------|
| Failed SSH attempts > 5 | Email | High |
| Container restart loop | Coolify notification | Medium |
| Database connection failure | Coolify notification | High |
| Unusual API traffic spike | Manual check (for now) | Medium |

## Security vs Performance Matrix

| Security Measure | Performance Impact | Implementation Effort | Priority |
|-----------------|-------------------|----------------------|----------|
| Firewall rules | None | Low | P0 |
| HTTPS | +5ms latency | Low | P0 |
| Real domain (hide IP) | None | Medium | P1 |
| Cloudflare proxy | -20ms (CDN benefit) | Medium | P1 |
| API authentication | +1-5ms | Medium | P1 |
| Rate limiting | Negligible | Low | P2 |
| JWT tokens | +5ms | High | P2 |
| WAF rules | +10ms | Medium | P2 |

## Implementation Priority

### This Week (P0)
- [ ] Verify PostgreSQL not exposed externally
- [ ] Enable firewall (UFW)
- [ ] Enable HTTPS on Coolify apps
- [ ] Verify SSH uses key-only auth

### Next Week (P1)
- [ ] Set up real domain for apps
- [ ] Configure Cloudflare proxy
- [ ] Add basic API key authentication
- [ ] Review and restrict Coolify panel access

### This Month (P2)
- [ ] Implement rate limiting
- [ ] Add request logging for security audit
- [ ] Set up fail2ban
- [ ] Document incident response procedure

## Incident Response

### If Compromise Suspected

1. **Immediate** (within 5 minutes)
   - Rotate all database credentials
   - Invalidate Claude OAuth tokens
   - Change Coolify admin password

2. **Short-term** (within 1 hour)
   - Review Coolify deployment logs
   - Check for unauthorized containers
   - Audit recent git commits

3. **Recovery**
   - Redeploy from known-good commit
   - Restore database from backup if needed
   - Enable additional monitoring

### Credential Rotation Procedure

```bash
# 1. Generate new PostgreSQL password
NEW_PW=$(openssl rand -base64 32)

# 2. Update in Supabase dashboard

# 3. Update in Coolify for each app:
#    - charm-api
#    - charm-strategy-worker
#    - charm-domain-worker
#    - charm-spintax-worker

# 4. Redeploy all applications
```

## Related

- [[vps]] - VPS server details
- [[coolify]] - Coolify deployment platform
- [[../deployment/index]] - Deployment documentation
- [[supabase]] - Database configuration
