---
title: Nameserver Verification
created: 2026-01-22
updated: 2026-01-22
tags: [feature, infrastructure, dns, domains]
---

# Nameserver Verification

Automated verification and configuration of domain nameservers for Hypertide/DNSimple compatibility.

## Overview

After domain purchase from Porkbun or Dynadot, nameservers must be configured to DNSimple for Hypertide inbox provisioning. This feature provides:

1. **Verification** - Check if NS are correctly set at the registrar
2. **Fix/Set** - Configure NS to DNSimple values if missing or incorrect
3. **Status Tracking** - Track propagation status (24-48 hours)

## Required Nameservers

Hypertide requires domains to use DNSimple nameservers:
- `ns1.dnsimple.com`
- `ns2.dnsimple-edge.net`
- `ns3.dnsimple.com`
- `ns4.dnsimple-edge.org`

## NS Status States

| Status | Badge Color | Meaning |
|--------|-------------|---------|
| `pending` | Gray | Not yet verified, click "Verify NS" to check |
| `verified` | Green | NS correctly configured at registrar |
| `propagating` | Blue | NS set recently, waiting 24-48h for DNS propagation |
| `mismatch` | Amber | NS don't match DNSimple requirements |
| `failed` | Red | Domain not found in registrar account |

## UI Components

### DomainsNeedingSetupTable

Located in `components/purchasing/DomainsNeedingSetupTable.tsx`

**Buttons:**
- **Verify NS** - Checks current NS at registrar for selected domains
- **Fix NS** - Sets NS to DNSimple values (only shows when domains need fixing)
- **Setup Inboxes** - Proceeds to Hypertide provisioning

**Columns:**
- Domain name
- TLD badge
- Status (Needs Setup / Provisioning)
- NS Verified (status badge)
- DNS Ready (24hr check)
- Provider (Porkbun / Dynadot)
- Purchased date

## API Endpoints

### Verify Nameservers

```
POST /api/v1/domain-sourcing/verify-nameservers
```

**Request:**
```json
{
  "domain_names": ["example1.com", "example2.com"]
}
```

**Response:**
```json
{
  "results": [
    {
      "domain": "example1.com",
      "status": "verified",
      "current_nameservers": ["ns1.dnsimple.com", "ns2.dnsimple-edge.net", ...],
      "registrar": "dynadot"
    }
  ],
  "verified_count": 1,
  "propagating_count": 0,
  "mismatch_count": 0,
  "failed_count": 0
}
```

### Set Nameservers

```
POST /api/v1/domain-sourcing/set-nameservers
```

**Request:**
```json
{
  "domain_names": ["example1.com", "example2.com"]
}
```

**Response:**
```json
{
  "results": [
    {
      "domain": "example1.com",
      "success": true,
      "registrar": "dynadot"
    }
  ],
  "success_count": 1,
  "failed_count": 0
}
```

## Registrar Detection

The system automatically detects which registrar owns a domain by querying both:

1. **Porkbun** - REST API (`/domain/getNs/{domain}`)
2. **Dynadot** - XML API (`domain_info` command)

A domain returning `[]` (empty list) means it exists but has no NS configured (parked domain).
A domain returning `None` means it doesn't exist in that registrar's account.

## DNS Propagation

After nameservers are set, DNS propagation takes 24-48 hours. The system tracks this via:

- `nameservers_updated_at` timestamp on domain record
- `propagating` status for domains updated within 48 hours
- `DNS Ready` badge shows when propagation window has passed

## Database Fields

The `domains` table includes:

| Field | Type | Description |
|-------|------|-------------|
| `nameserver_status` | VARCHAR | pending, verified, propagating, mismatch, failed |
| `nameserver_verified_at` | TIMESTAMP | Last verification check time |
| `nameservers_updated_at` | TIMESTAMP | When NS were last set |
| `current_nameservers` | TEXT[] | Array of current NS from registrar |
| `selected_provider` | VARCHAR | porkbun or dynadot |

## Workflow

```
Domain Purchased
       │
       ▼
  NS set to DNSimple (automatic during purchase)
       │
       ▼
  User clicks "Verify NS"
       │
       ├─► NS match → status = verified
       │
       ├─► NS don't match → status = mismatch
       │                         │
       │                         ▼
       │                   User clicks "Fix NS"
       │                         │
       │                         ▼
       │                   status = propagating
       │                         │
       │                    (wait 24-48h)
       │                         │
       │                         ▼
       │                   Re-verify → verified
       │
       └─► Domain not found → status = failed
```

## Related

- [[domain-lifecycle]] - Full domain status flow
- [[domain-purchasing]] - Domain purchase workflow
- [[infrastructure-hub]] - Infrastructure management overview
