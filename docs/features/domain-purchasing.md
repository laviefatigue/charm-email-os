---
title: Domain Purchasing
created: 2026-01-21
updated: 2026-02-13
tags: [feature, domains, purchasing, registrars, porkbun, dynadot, pricing]
---

# Domain Purchasing

Domain availability checking and purchasing via registrar APIs with automatic price comparison.

## Overview

After [[domain-generation]] creates candidates, this system checks availability and pricing across **both registrars simultaneously**, caches the results, and automatically selects the cheapest provider for purchase.

```
┌──────────────────────────────────────────────────────────────────────┐
│  Domain Sourcing Pipeline                                            │
├──────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  1. GENERATE        2. PRICE CHECK      3. APPROVE      4. PURCHASE  │
│  ┌──────────┐      ┌──────────┐        ┌──────────┐    ┌──────────┐ │
│  │ AI/Pattern│ ──► │ Porkbun  │ ──►    │ Human    │ ──►│ Cheapest │ │
│  │ Generator │      │ Dynadot  │        │ Review   │    │ Provider │ │
│  └──────────┘      │ (parallel)│        └──────────┘    │ (fallback)│ │
│                    └──────────┘                         └──────────┘ │
│                                                                       │
└──────────────────────────────────────────────────────────────────────┘
```

## Supported Registrars

| Registrar | Status | API Docs | Typical .com Price |
|-----------|--------|----------|-------------------|
| **Dynadot** | ✅ Working | [API v3](https://www.dynadot.com/domain/api3.html) | ~$10.88/year |
| **Porkbun** | ✅ Working | [API v3](https://porkbun.com/api/json/v3/documentation) | ~$11.08/year |
| Namecheap | Future | - | - |
| Cloudflare | Future | - | - |

## Dual-Provider Pricing System

### How It Works

1. **Price Check** calls both Dynadot and Porkbun APIs in parallel
2. **Results cached** on domain record (no repeated API calls)
3. **Best price auto-selected** for display and purchase
4. **Fallback on purchase** if primary provider becomes unavailable

### Database Schema

Prices are cached on each domain record:

| Column | Type | Description |
|--------|------|-------------|
| `porkbun_price` | DECIMAL(10,2) | Cached Porkbun price |
| `porkbun_available` | BOOLEAN | Porkbun availability |
| `dynadot_price` | DECIMAL(10,2) | Cached Dynadot price |
| `dynadot_available` | BOOLEAN | Dynadot availability |
| `cached_price` | DECIMAL(10,2) | Best price (for sorting) |
| `selected_provider` | VARCHAR(20) | Provider with best price |
| `price_checked_at` | TIMESTAMP | Last check time |

### UI Display

The Procurement tab shows both providers:
```
PB: $11.08
DD: $10.88 ✓  ← Checkmark indicates best price
```

### Purchase Fallback

If the selected provider becomes unavailable at purchase time:
1. System detects unavailability
2. Automatically tries the other provider
3. Updates `selected_provider` in database
4. Proceeds with purchase

## Configuration

### Required Environment Variables

Add to `.env.local`:

```bash
# Dynadot (primary - usually cheaper)
DYNADOT_API_KEY=your_api_key_here

# Porkbun (secondary)
PORKBUN_API_KEY=pk1_xxx
PORKBUN_API_SECRET=sk1_xxx
```

Get credentials:
- **Dynadot**: https://www.dynadot.com/community/developers
- **Porkbun**: https://porkbun.com/account/api

## Dynadot Integration

### API Details

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api3.xml?command=search` | GET | Check availability + pricing |
| `/api3.xml?command=register` | GET | Purchase domain |
| `/api3.xml?command=set_ns` | GET | Set nameservers |

### Response Structure (XML)

```xml
<SearchResponse>
  <SearchHeader>
    <Status>success</Status>
  </SearchHeader>
  <SearchResults>
    <SearchResult>
      <DomainName>example.com</DomainName>
      <Status>available</Status>
      <Price>10.88</Price>
    </SearchResult>
  </SearchResults>
</SearchResponse>
```

### Pricing

Standard .com domains: ~$10.88/year (typically cheapest)

## Porkbun Integration

### API Details

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/ping` | POST | Test connectivity |
| `/domain/checkDomain/{domain}` | POST | Check availability + pricing |
| `/domain/register/{domain}` | POST | Purchase domain |
| `/domain/updateNs/{domain}` | POST | Set nameservers |

### Rate Limiting

**Note**: Porkbun has stricter rate limits than Dynadot. The system handles this with delays between checks.

### Response Structure (JSON)

```json
{
  "status": "SUCCESS",
  "response": {
    "avail": "yes",
    "price": "11.08",
    "regularPrice": "11.08"
  }
}
```

### Pricing

Standard .com domains: ~$11.08/year (includes free WHOIS privacy)

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

## Price Checking

### Bulk Price Check

The "Check All Prices" button on the Procurement tab:
1. Fetches all candidate domains for the client
2. Calls both registrar APIs in parallel for each domain
3. Caches results to database
4. Updates UI with dual pricing display

### Background Price Checker

The `charm-price-checker` worker automatically refreshes stale prices:
- Runs every 12 hours (configurable via `CHECK_INTERVAL`)
- Re-checks domains where `price_checked_at` > 24 hours old
- Removes domains that become unavailable

## Known Issues

- Porkbun has stricter rate limits than Dynadot
- Some premium domains may have different pricing between registrars
- Price fluctuations can occur between check and purchase (mitigated by re-verification)

## Related

- [[domain-generation]] - AI domain name generation
- [[../architecture/api-endpoints]] - API documentation
- [[../database/schema]] - Database schema for domain records
