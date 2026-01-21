---
title: Domain Purchasing
created: 2026-01-21
updated: 2026-01-21
tags: [feature, domains, purchasing, registrars, porkbun]
---

# Domain Purchasing

Domain availability checking and purchasing via registrar APIs.

## Overview

After [[domain-generation]] creates candidates, this system checks availability and pricing across registrars, then handles purchase execution.

```
┌──────────────────────────────────────────────────────────────────────┐
│  Domain Sourcing Pipeline                                            │
├──────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  1. GENERATE        2. SEARCH           3. APPROVE      4. PURCHASE  │
│  ┌──────────┐      ┌──────────┐        ┌──────────┐    ┌──────────┐ │
│  │ AI/Pattern│ ──► │ Porkbun  │ ──►    │ Human    │ ──►│ Registrar│ │
│  │ Generator │      │ Dynadot  │        │ Review   │    │ API      │ │
│  └──────────┘      └──────────┘        └──────────┘    └──────────┘ │
│                                                                       │
└──────────────────────────────────────────────────────────────────────┘
```

## Supported Registrars

| Registrar | Status | API Docs | Notes |
|-----------|--------|----------|-------|
| **Porkbun** | Working | [API v3](https://porkbun.com/api/json/v3/documentation) | Primary registrar, free WHOIS privacy |
| **Dynadot** | Planned | [API v3](https://www.dynadot.com/domain/api3.html) | Competitive pricing, needs API key |
| Namecheap | Future | - | Enum defined, not implemented |
| Cloudflare | Future | - | Enum defined, not implemented |

## Porkbun Integration

### Configuration

Environment variables in `.env`:

```bash
PORKBUN_API_KEY=pk1_xxx
PORKBUN_API_SECRET=sk1_xxx
```

Get credentials from: https://porkbun.com/account/api

### API Details

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/ping` | POST | Test connectivity |
| `/domain/checkDomain/{domain}` | POST | Check availability + pricing |
| `/domain/register/{domain}` | POST | Purchase domain |
| `/domain/updateNs/{domain}` | POST | Set nameservers |
| `/pricing/get` | POST | Get all TLD pricing |

### Rate Limiting

**Critical**: Porkbun allows only **1 domain check per 10 seconds**.

The test script and registrar integration handle this automatically with 11-second delays between checks.

### Response Structure

```json
{
  "status": "SUCCESS",
  "response": {
    "avail": "yes",
    "price": "11.08",
    "regularPrice": "11.08",
    "firstYearPromo": "no",
    "premium": "no",
    "additional": {
      "renewal": { "price": "11.08" },
      "transfer": { "price": "11.08" }
    }
  }
}
```

### Pricing

Standard .com domains: ~$11.08/year (includes free WHOIS privacy)

## Dynadot Integration

### Status: Planned

Dynadot support is implemented in code but requires API credentials.

### Configuration Needed

```bash
DYNADOT_API_KEY=xxx
```

Get credentials from: https://www.dynadot.com/community/developers

### Why Add Dynadot

- Price comparison across registrars
- Often has better bulk pricing
- Different promotional deals than Porkbun

## Test Script

A standalone test script exists for verifying registrar connectivity:

**Location**: `D:\Work\charm-email-os\test_domain_search.py`

### Usage

```bash
cd D:\Work\charm-email-os
py test_domain_search.py
```

### What It Tests

1. API connectivity (ping)
2. Domain availability checking
3. Pricing retrieval
4. Rate limit handling

### Sample Output

```
============================================================
DOMAIN SEARCH TEST - Porkbun API
============================================================

[1] Testing API connectivity...
    [OK] API connection successful

[2] Checking domain availability...

    [1/3] example-domain.com: AVAILABLE
    (waiting 11s for rate limit...)
    [2/3] another-domain.com: AVAILABLE
    (waiting 11s for rate limit...)
    [3/3] google.com: TAKEN

AVAILABLE DOMAINS:
  [OK] example-domain.com: AVAILABLE - $11.08 | Renewal: $11.08/yr
```

## Code Locations

| Component | Location |
|-----------|----------|
| Registrar abstraction | `Hypertide/automation/src/hypertide_automation/domain_sourcing/registrars.py` |
| Domain models | `Hypertide/automation/src/hypertide_automation/domain_sourcing/models.py` |
| API routes | `api/routes/domain_sourcing.py` |
| Test script | `test_domain_search.py` |

## Purchase Flow (Full Pipeline)

```python
# 1. Generate domain candidates
POST /api/domain-sourcing/generate-for-client/{client_id}

# 2. Get pending candidates for review
GET /api/domain-sourcing/pending-candidates/{client_id}

# 3. Search registrar pricing
POST /api/domain-sourcing/search
{
  "domains": ["domain1.com", "domain2.com"],
  "registrars": ["porkbun"]
}

# 4. Approve selected domains
POST /api/domain-sourcing/approve/{domain_id}

# 5. Execute purchase
POST /api/domain-sourcing/purchase
{
  "domain": "domain1.com",
  "registrar": "porkbun",
  "nameservers": ["ns1.hypertide.com", "ns2.hypertide.com"]
}
```

## Next Steps

1. **Dynadot Integration**: Add API key and test connectivity
2. **Price Comparison UI**: Show prices from multiple registrars
3. **Bulk Purchase**: Support purchasing multiple domains in one flow
4. **Inbox Integration**: Connect to [[inbox-purchasing]] after domain purchase

## Known Issues

- Porkbun rate limit (1/10s) makes bulk checks slow
- No automatic retry on rate limit errors
- Dynadot XML parsing is simplified (may miss some fields)

## Related

- [[domain-generation]] - AI domain name generation
- [[../architecture/api-endpoints]] - API documentation
- [[../database/schema]] - Database schema for domain records
