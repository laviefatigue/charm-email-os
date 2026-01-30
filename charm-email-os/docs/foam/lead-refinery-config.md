---
title: Lead Refinery Configuration
created: 2026-01-27
updated: 2026-01-27
tags: [reference, lead-refinery, config]
---

# Lead Refinery Configuration

Client contract configuration for the [[lead-refinery]] pipeline.

## Config File Format

```json
{
  "client_id": "client_acme_001",
  "target": 5000,
  "raw_multiplier": 2.5,
  "filters": {
    "industries": ["Software", "Information Technology"],
    "company_sizes": ["51-200", "201-500"],
    "seniority": ["executive", "director"],
    "states": ["California", "New York"],
    "job_titles": ["CEO", "CTO", "VP"],
    "exclude_companies": ["Competitor Inc"]
  },
  "skip_email_check": false,
  "skip_rescue_layer": false,
  "export_dir": "./exports"
}
```

## Filter Options

### industries
Match any industry containing these terms:
- `"Software"`
- `"Hospital & Health Care"`
- `"Financial Services"`

### company_sizes
Exact match from LinkedIn values:
- `"1-10"`, `"11-50"`, `"51-200"`
- `"201-500"`, `"501-1000"`, `"1001-5000"`
- `"5001-10000"`, `"10001+"`

### salary (Inferred)
- `"$0-50K"`, `"$50K-100K"`
- `"$100K-150K"`, `"$150K+"`

### seniority
Maps to job title patterns:

| Level | Matches |
|-------|---------|
| `executive` | CEO, CTO, CFO, Chief, President, Founder |
| `director` | Director, VP, Vice President, Head of |
| `manager` | Manager, Lead, Supervisor |
| `senior` | Senior, Sr., Principal, Staff |
| `entry` | Associate, Junior, Jr., Intern |

### states
US state names for geographic targeting:
- `"California"`, `"New York"`, `"Texas"`

### exclude_companies
Companies to exclude (partial match):
- `"Competitor Inc"` excludes "Competitor Inc" and "Competitor Inc USA"

### exclude_domains
Email domains to exclude:
- `"gmail.com"`, `"yahoo.com"` (filter personal emails)

## CLI Usage

```bash
# Run full contract
python -m contract_refinery --config client_config.json

# Dry run (simulate, no DB updates)
python -m contract_refinery --config client_config.json --dry-run

# Override target
python -m contract_refinery --config client_config.json --target 1000

# Skip specific gates
python -m contract_refinery --config client_config.json --skip-email-check
python -m contract_refinery --config client_config.json --skip-rescue

# Export only (skip validation)
python -m contract_refinery --config client_config.json --export-only

# View statistics
python -m contract_refinery --stats
```

## API Usage

```bash
# Create and run contract
curl -X POST http://localhost:8000/contracts/create \
  -H "X-API-Key: your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "client_id": "client_acme_001",
    "target": 5000,
    "filters": {
      "industries": ["Software"],
      "seniority": ["executive"]
    }
  }'

# Check status
curl http://localhost:8000/contracts/client_acme_001/status \
  -H "X-API-Key: your-key"

# Export verified leads
curl http://localhost:8000/contracts/client_acme_001/export?format=csv \
  -H "X-API-Key: your-key" \
  -o verified_leads.csv
```

## Core Constraints

These conditions are ALWAYS applied:
- Must have email: `Emails IS NOT NULL`
- Not already used: `client_contract_id IS NULL`
- Not already validated: `validation_status IS NULL OR 'pending'`
- Not dead: `validation_status != 'dead'`

## Raw Pull Calculation

```
raw_needed = target × raw_multiplier
```

Default: 5,000 × 2.5 = 12,500 raw leads

This accounts for ~40% global yield through all gates.

## Related

- [[lead-refinery]] - Main hub
- [[lead-refinery-gates]] - Gate-by-gate details

---
Tags: #reference #lead-refinery #config #cli
