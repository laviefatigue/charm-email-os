# Hypertide Prefect Flows

Google Sheets-driven automation for domain purchasing and inbox provisioning.

## Overview

This PoC uses Google Sheets as the checkpoint/data source instead of direct database queries:

```
┌─────────────────────────────────────────────────────────────────────┐
│                    GOOGLE SHEETS PIPELINE                          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌─────────────────┐                                               │
│  │  Google Sheet   │ ◄── You manage this                           │
│  │  - Domains Tab  │                                               │
│  │  - Inboxes Tab  │                                               │
│  │  - Config Tab   │                                               │
│  └────────┬────────┘                                               │
│           │                                                         │
│           ▼                                                         │
│  ┌────────────────────────┐                                        │
│  │ domain_purchase_flow   │  Reads "approved" → purchases → "purchased" │
│  └────────────────────────┘                                        │
│           │                                                         │
│           ▼                                                         │
│  ┌────────────────────────┐                                        │
│  │ inbox_provision_flow   │  Generates inboxes → verifies → uploads │
│  └────────────────────────┘                                        │
│           │                                                         │
│           ▼                                                         │
│  ┌────────────────────────┐                                        │
│  │   Email Bison          │  Inboxes ready for warmup              │
│  └────────────────────────┘                                        │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

## Google Sheet Setup

Create a Google Sheet with 3 tabs:

### Domains Tab
| domain | provider | status | hypertide_id | purchased_at | error |
|--------|----------|--------|--------------|--------------|-------|
| outreach-acme.com | entra | approved | | | |
| sales-acme.com | google | pending | | | |

**Status values:** `pending` → `approved` → `purchasing` → `purchased` / `failed`

### Inboxes Tab
| email | first_name | last_name | domain | provider | status | workspace | uploaded_at | error |
|-------|------------|-----------|--------|----------|--------|-----------|-------------|-------|
| (auto-generated) | | | | | | | | |

**Status values:** `pending` → `provisioning` → `provisioned` → `uploaded` / `failed`

### Config Tab
| key | value |
|-----|-------|
| client_name | Acme Corp |
| forwarding_domain | acme.com |
| emailbison_workspace | acme-workspace |

## Prerequisites

### 1. Google Service Account
```bash
# Create service account at https://console.cloud.google.com/
# Download JSON key file
export GOOGLE_CREDENTIALS_PATH=~/.config/gcloud/service-account.json

# Share your Google Sheet with the service account email
```

### 2. Environment Variables
```bash
export HYPERTIDE_SHEET_ID="your-google-sheet-id-from-url"
export GOOGLE_CREDENTIALS_PATH="/path/to/service-account.json"
export PREFECT_API_URL="http://localhost:4200/api"

# Optional
export EMAILBISON_API_KEY="your-api-key"
export EMAILBISON_BASE_URL="https://api.emailbison.com"
```

### 3. Install Dependencies
```bash
cd D:\BrainOn\Hypertide\automation
pip install -e .
```

## Usage

### Manual Testing (Dry Run)
```bash
# Test domain purchase flow
ht-flow-domains
# or
python -m hypertide_automation.flows.domain_purchase_flow

# Test inbox provision flow
ht-flow-inboxes

# Test full pipeline
ht-flow-pipeline
```

### Deploy to Prefect
```bash
# Set Prefect API URL
set PREFECT_API_URL=http://localhost:4200/api

# Deploy all flows
cd D:\BrainOn\Hypertide\automation
prefect deploy --all

# Or deploy individually
prefect deploy -n domain-purchase-manual
prefect deploy -n inbox-provision-manual
```

### Run Deployed Flows
```bash
# From Prefect UI
# http://localhost:4200

# Or CLI
prefect deployment run "domain-purchase-flow/domain-purchase-manual"
prefect deployment run "inbox-provision-flow/inbox-provision-manual"
```

## Flow Parameters

### domain_purchase_flow
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| sheet_id | str | env var | Google Sheet ID |
| headless | bool | False | Run browser headless |
| dry_run | bool | True | Simulate without purchasing |
| max_domains | int | 10 | Safety limit per run |

### inbox_provision_flow
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| sheet_id | str | env var | Google Sheet ID |
| headless | bool | False | Run browser headless |
| dry_run | bool | True | Simulate without changes |
| skip_emailbison | bool | False | Skip Email Bison upload |
| generate_new | bool | True | Generate from domains vs process pending |

## Workflow

1. **Add domains to sheet** with status `pending`
2. **Mark as `approved`** when ready to purchase
3. **Run domain_purchase_flow** → status becomes `purchased`
4. **Run inbox_provision_flow** → generates inboxes, uploads to Email Bison
5. **Monitor results** in sheet columns

## Files

```
flows/
├── __init__.py              # Package exports
├── README.md                # This file
├── sheets.py                # Google Sheets client (gspread)
├── domain_purchase_flow.py  # Prefect flow for domain purchases
├── inbox_provision_flow.py  # Prefect flow for inbox provisioning
└── pipeline.py              # Combined end-to-end flow
```

## Troubleshooting

### "Sheet ID required"
Set `HYPERTIDE_SHEET_ID` environment variable with the ID from your Google Sheet URL:
`https://docs.google.com/spreadsheets/d/YOUR_SHEET_ID_HERE/edit`

### "Credentials not found"
Ensure `GOOGLE_CREDENTIALS_PATH` points to your service account JSON file.

### "Worksheet not found"
Create the required tabs in your sheet: `Domains`, `Inboxes`, `Config`

### "Permission denied"
Share your Google Sheet with the service account email address (found in the JSON key file).
