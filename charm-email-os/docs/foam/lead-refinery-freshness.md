---
title: Lead Freshness System
created: 2026-01-27
updated: 2026-01-27
tags: [concept, lead-refinery, freshness, maintenance]
---

# Lead Freshness System

Continuous lead database maintenance through freshness scoring and prioritized validation.

## Philosophy

> Treat lead data like inventory with expiration dates.
> Fresh leads are worth more. Stale leads decay in value.

Rather than only validating leads on-demand for contracts, the freshness system proactively maintains data quality across the entire 75M lead database.

## Freshness Tiers

| Tier | Age | Score | Description |
|------|-----|-------|-------------|
| **Fresh** | < 30 days | 85-100 | Recently validated, high confidence |
| **Recent** | 30-90 days | 50-85 | Still usable, validation recommended |
| **Stale** | 90-180 days | 25-50 | Job changes likely, validate before use |
| **Expired** | > 180 days | 10-25 | High risk of outdated data |
| **Never** | N/A | 0 | Never validated |

## Freshness Decay Model

Leads decay in value over time as people change jobs, companies, and contact info:

```
Days Since Validation → Freshness Score
       0 days → 100 (just validated)
       7 days → 95
      30 days → 85
      60 days → 70
      90 days → 50  (typical job change window)
     180 days → 25
     365 days → 10
```

## Priority Queue

The system prioritizes validation based on lead value and staleness:

1. **Never validated with email** (priority: 1000)
   - Highest priority - unknown data quality

2. **Verified but expired** (priority: 800)
   - Was good data, now at risk

3. **Verified but stale** (priority: 600)
   - Still likely good, proactive maintenance

4. **Previously unverifiable** (priority: 400)
   - Retry with updated sources

5. **Verified but getting stale** (priority: 200)
   - Preventive validation

## Priority Multipliers

High-value leads get validation priority:

### By Company Size
Larger companies = more stable employment

| Size | Multiplier |
|------|------------|
| 10,001+ | 1.2x |
| 5,001-10,000 | 1.15x |
| 1,001-5,000 | 1.1x |
| 201-500 | 1.0x |
| 1-10 | 0.8x |

### By Seniority
Executives change jobs less frequently

| Level | Multiplier |
|-------|------------|
| CEO/CTO/CFO | 1.2x |
| President | 1.15x |
| Director/VP | 1.1x |
| Manager | 1.0x |

## CLI Usage

```bash
# View freshness stats
py contract_refinery/freshness.py stats

# View validation queue size
py contract_refinery/freshness.py queue

# Estimate cost to achieve 80% freshness
py contract_refinery/freshness.py estimate

# Get 10 stale leads needing validation
py contract_refinery/freshness.py stale 10
```

## Continuous Worker

Background worker for maintaining freshness:

```bash
# Run continuously (100 leads/batch, 60s intervals)
py -m contract_refinery.freshness_worker

# Custom batch size and interval
py -m contract_refinery.freshness_worker --batch-size 50 --interval 120

# Run single batch (for cron jobs)
py -m contract_refinery.freshness_worker --once

# Filter to specific industries
py -m contract_refinery.freshness_worker --industries "Software,SaaS"

# Dry run (no database updates)
py -m contract_refinery.freshness_worker --dry-run
```

The worker:
1. Pulls stale leads from priority queue
2. Runs through [[lead-refinery-gates|validation waterfall]]
3. Updates freshness timestamps
4. Sleeps between batches to control API costs

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/freshness/stats` | GET | Database-wide freshness statistics |
| `/freshness/queue` | GET | Validation queue sizes by priority |
| `/freshness/estimate` | GET | Cost estimate for target freshness |
| `/freshness/stale-leads` | GET | Get prioritized leads for validation |
| `/freshness/get-batch` | POST | Get validation batch with filters |

## Integration with [[lead-refinery-gates|Validation Gates]]

The freshness system feeds leads into the same waterfall pipeline:

```
Freshness Queue (prioritized)
  → [[lead-refinery-gates|Gate 1: Reoon]] (email check)
  → [[lead-refinery-gates|Gate 2: AI-ARK]] (employment verify)
  → [[lead-refinery-gates|Gate 3: Spider+Jina]] (rescue layer)
  → Update freshness timestamp
```

## Cost Considerations

For a database of 30M leads with email:

| Scenario | Leads to Validate | Est. Cost |
|----------|-------------------|-----------|
| Validate all never-checked | 30,267,158 | $184,630 |
| Maintain 80% fresh | ~1M/month | ~$6,100/month |
| Contract-based only | 12,500/contract | $59.50/contract |

**Recommendation**: Use contract-based validation for immediate needs, freshness system for background maintenance on high-value segments.

## Related

- [[lead-refinery]] - Main hub
- [[lead-tam-map]] - Enrichment data builds a living TAM map
- [[lead-refinery-gates]] - Validation pipeline
- [[lead-refinery-config]] - Configuration options

---
Tags: #concept #lead-refinery #freshness #maintenance #continuous
