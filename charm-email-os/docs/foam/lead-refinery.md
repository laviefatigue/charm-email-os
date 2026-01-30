---
title: Lead Refinery
created: 2026-01-27
updated: 2026-01-27
tags: [hub, lead-refinery, verification, jit, pipeline]
---

# Lead Refinery

JIT (Just-In-Time) lead verification system for cold email contracts.

## Overview

The ContractRefinery processes raw leads through a cost-efficient waterfall pipeline to deliver verified contact lists for [[campaigns]].

- **Target**: 5,000 verified leads per contract
- **Source**: 75.4M leads in DuckDB
- **Cost**: ~$0.012/verified lead

## Pipeline Architecture

```
DuckDB (12.5K raw)
  → [[lead-refinery-gates|Gate 0: Pre-Validation]] (FREE, classify + select best email)
  → [[lead-refinery-gates|Gate 1: LeadMagic]] (70% pass, $0.005)
  → [[lead-refinery-gates|Gate 2: AI-ARK]] (60% match, $0.005)
  → [[lead-refinery-gates|Gate 3: Spider+Jina]] (30% rescue, $0.002)
  → Export CSV
```

## Quick Start

```bash
# View current stats
python -m contract_refinery --stats

# Run a contract
python -m contract_refinery --config client_config.json

# Dry run (no DB updates)
python -m contract_refinery --config client_config.json --dry-run
```

## Concepts

- [[lead-refinery-gates]] - Gate-by-gate verification logic
- [[lead-refinery-config]] - Client configuration format
- [[lead-refinery-freshness]] - Continuous freshness maintenance

## Operational Modes

### Contract-Based (On-Demand)
Pull and validate leads for specific client contracts. Most cost-efficient.

```bash
python -m contract_refinery --config client_config.json
```

### Continuous Freshness
Background maintenance to keep high-value segments up-to-date. See [[lead-refinery-freshness]].

```bash
# View freshness stats
py contract_refinery/freshness.py stats
```

## Cost Summary (per 5,000 leads)

| Gate | Provider | Cost |
|------|----------|------|
| Gate 0 (Pre-Check) | Python + DNS | **$0.00** |
| Gate 1 (Email) | LeadMagic | ~$25* |
| Gate 2 (Employment) | AI-ARK | $43.75 |
| Gate 3 (Rescue) | Spider+Jina | $7.00 |
| **Total** | | **~$76** |

*LeadMagic catch_all/unknown results are FREE, reducing actual cost.
Gate 0 filters disposable/dead emails and selects business over personal emails for free.

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/contracts/create` | POST | Create and run contract |
| `/contracts/{id}/status` | GET | Get contract status |
| `/contracts/{id}/export` | GET | Export verified leads |
| `/contracts/list` | GET | List all contracts |

## File Structure

```
linkedin-scanner/
├── contract_refinery/
│   ├── gate0_prevalidation.py  # Gate 0 (FREE)
│   ├── email_verifier.py       # Gate 1 (LeadMagic)
│   ├── refinery.py             # Main orchestrator
│   ├── freshness.py            # Freshness scoring
│   ├── freshness_worker.py     # Background worker
│   ├── ingestion.py            # Bulk lead import
│   ├── spider_client.py        # Gate 3
│   ├── jina_client.py          # Gate 3
│   ├── rescue_layer.py         # Gate 3 orchestrator
│   ├── matching.py             # Fuzzy matching
│   ├── config.py               # ContractConfig model
│   └── models.py               # Data models
├── aiark_client.py             # Gate 2 (AI-ARK)
└── linkedin.duckdb             # 75.4M leads
```

## Environment Variables

| Variable | Purpose | Required |
|----------|---------|----------|
| `LEADMAGIC_API_KEY` | Gate 1 email verification (default) | Yes |
| `AIARK_API_KEY` | Gate 2 employment verification | Yes |
| `SPIDER_API_KEY` | Gate 3 web search | Recommended |
| `JINA_API_KEY` | Gate 3 content extraction | Optional |

### Provider Swapping

```bash
# Switch email verification provider
export EMAIL_VERIFIER_PROVIDER=reoon  # or zerobounce
export REOON_API_KEY=xxx
```

## Connection to Charm Email OS

The Lead Refinery is the bridge between [[clients|client strategy]] in Charm OS and campaign execution in EmailBison:

```
Charm OS                    Lead Refinery              EmailBison
─────────                   ─────────────              ──────────
Client onboarding    →  ICP criteria for DuckDB query
Campaign strategy    →  Industry/title/geo filters
                         DuckDB reservoir (75.4M)
                         Gates 0-3 validation
                         Verified leads            →  Campaign loaded
                                                      Sequence sends
                         Dispositions updated      ←  Performance data
                         TAM map evolves           ←  Opens/replies/bounces
```

- **ICP criteria** come from [[clients|client onboarding]] data (industry, titles, company size, geography)
- **Campaign fill** triggers when an EmailBison campaign (pushed from Charm OS [[campaigns|strategy approval]]) needs leads
- **Performance sync** updates [[lead-dispositions]] in DuckDB, teaching the system which segments respond
- **Infrastructure** ([[infrastructure|domains and inboxes]]) provisioned in Charm OS sends the emails

See [[system-integration]] for the full platform architecture.

## Related

- [[system-integration]] - How all three systems connect
- [[lead-tam-map]] - AI-ARK enrichment builds a living TAM map
- [[lead-dispositions]] - Lead state machine and cooldowns
- [[leads]] - Leads consumed by campaigns
- [[campaigns]] - Email campaigns using verified leads
- [[clients]] - Client ICP drives lead selection
- [[workflows]] - Integration with email workflows
- [[infrastructure]] - Sending infrastructure

---
Tags: #hub #lead-refinery #verification #pipeline #jit
