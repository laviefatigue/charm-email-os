# Charm Email OS Database Schema

## Overview

PostgreSQL 15 database with 90+ tables managing email infrastructure, clients, domains, and campaigns.

---

## Core Tables

### clients

Client accounts that own email infrastructure.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| id | uuid | NO | Primary key |
| name | varchar | NO | Client name |
| workspace_id | uuid | YES | Link to workspaces table |
| logo_url | text | YES | Client logo URL |
| onboarding_complete | boolean | YES | Onboarding status |
| onboarding_data | jsonb | YES | Onboarding configuration |
| contact_name | varchar | YES | Primary contact name |
| contact_email | varchar | YES | Primary contact email |
| website | varchar | YES | Client website |
| industry | varchar | YES | Industry category |
| domain_pattern | varchar | YES | Preferred domain pattern |
| created_at | timestamptz | YES | Created timestamp |
| updated_at | timestamptz | YES | Last updated |

**onboarding_data JSONB Structure:**
```json
{
  "primaryDomain": "example.com",
  "baseSenderNames": [
    {"firstName": "Chris", "lastName": "Booth", "isFounder": true}
  ],
  "preGeneratedSenderNames": [
    {"firstName": "Chris", "lastName": "Booth", "emailPrefix": "chris.booth", "source": "generated"}
  ],
  "variationPatterns": ["firstname.lastname", "f.lastname", ...],
  "senderNamePreferences": {
    "usePersonas": false,
    "nameCount": 52,
    "provider": "entra"
  }
}
```

---

### workspaces

EmailBison workspace connections.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| id | uuid | NO | Primary key |
| instance_id | uuid | NO | OwnRBL instance |
| workspace_name | varchar | NO | Workspace display name |
| emailbison_workspace_id | varchar | YES | EmailBison workspace ID |
| sender_account_count | integer | YES | Cached inbox count |
| is_active | boolean | YES | Sync enabled |
| automation_enabled | boolean | YES | Automation enabled |
| created_at | timestamptz | NO | Created timestamp |
| updated_at | timestamptz | NO | Last updated |

---

### domains

Email domains managed in the system.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| id | uuid | NO | Primary key |
| workspace_id | uuid | NO | Parent workspace |
| domain_name | varchar | NO | Domain name (e.g., example.com) |
| domain_state | enum | YES | 'live', 'dead', 'pending' |
| provider | varchar | YES | 'hypertide', 'manual' |
| approval_status | varchar | YES | 'pending', 'approved', 'purchased' |
| infrastructure_type | varchar | YES | 'entra', 'google' |
| sender_account_count | integer | NO | Inbox count on domain |
| live_inbox_count | integer | YES | Live inboxes |
| dead_inbox_count | integer | YES | Dead inboxes |
| health_percentage | numeric | YES | Domain health 0-100 |
| domain_bounce_rate_7d | numeric | YES | 7-day bounce rate |
| domain_complaint_count | integer | YES | Spam complaints |
| porkbun_price | numeric | YES | Porkbun price |
| dynadot_price | numeric | YES | Dynadot price |
| selected_provider | varchar | YES | Chosen registrar |
| purchased_at | timestamp | YES | Purchase timestamp |
| nameserver_status | varchar | YES | 'pending', 'verified' |
| registration_date | timestamptz | YES | WHOIS registration date |
| created_at | timestamptz | NO | Created timestamp |
| updated_at | timestamptz | NO | Last updated |

---

### sender_accounts

Email inboxes/sender accounts synced from EmailBison.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| id | uuid | NO | Primary key |
| workspace_id | uuid | NO | Parent workspace |
| domain_id | uuid | YES | Parent domain |
| email_address | varchar | NO | Email address |
| emailbison_account_id | text | YES | EmailBison account ID |
| display_name | varchar | YES | Display name |
| status | varchar | YES | 'Connected', 'Not connected', 'Disabled' |
| inbox_state | enum | YES | 'live', 'dead', 'incubating' |
| esp | enum | YES | 'gmail', 'microsoft', 'other' |
| health_score | integer | YES | Health score 0-100 |
| hard_bounces_24h | integer | YES | 24h hard bounces |
| hard_bounces_7d | integer | YES | 7d hard bounces |
| total_sends_7d | integer | YES | 7d total sends |
| complaints_lifetime | integer | YES | Lifetime spam complaints |
| warmup_started_at | timestamptz | YES | Warmup start date |
| sending_started_at | timestamptz | YES | Campaign start date |
| killed_at | timestamptz | YES | When killed |
| kill_reason | text | YES | Kill reason |
| kill_trigger | enum | YES | Trigger type |
| first_seen_at | timestamptz | NO | First sync |
| last_seen_at | timestamptz | NO | Last sync |
| last_synced_at | timestamptz | YES | Last full sync |
| is_active | boolean | NO | Active status |

---

### client_subscriptions

Package/subscription assignments for clients.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| id | uuid | NO | Primary key |
| client_id | uuid | NO | Parent client |
| package_template_id | uuid | YES | Template used |
| status | varchar | YES | 'active', 'inactive' |
| entra_packages | integer | YES | Entra order count |
| google_packages | integer | YES | Google order count |
| entra_domains_per_package | integer | YES | Domains per Entra order |
| google_domains_per_package | integer | YES | Domains per Google order |
| entra_inboxes_per_domain | integer | YES | Inboxes per Entra domain |
| google_inboxes_per_domain | integer | YES | Inboxes per Google domain |
| spare_ratio | numeric | YES | Target spare capacity |
| notes | text | YES | Subscription notes |
| created_at | timestamptz | NO | Created timestamp |
| updated_at | timestamptz | NO | Last updated |

---

### package_templates

Predefined package configurations.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| id | uuid | NO | Primary key |
| name | varchar | NO | Template name (e.g., "Starter", "Growth") |
| entra_packages | integer | NO | Default Entra orders |
| google_packages | integer | NO | Default Google orders |
| total_domains | integer | YES | Calculated total domains |
| total_inboxes | integer | YES | Calculated total inboxes |
| is_active | boolean | YES | Template available |

---

### emailbison_campaigns

Campaign metadata synced from EmailBison.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| id | uuid | NO | Primary key |
| workspace_id | uuid | NO | Parent workspace |
| emailbison_campaign_id | varchar | NO | EmailBison campaign ID |
| campaign_name | varchar | YES | Campaign name |
| status | varchar | YES | Campaign status |
| leads_count | integer | YES | Total leads |
| created_at | timestamptz | NO | Created timestamp |
| updated_at | timestamptz | NO | Last updated |

---

### kill_queue

Inbox kill tracking for rotation.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| id | uuid | NO | Primary key |
| sender_account_id | uuid | NO | Inbox to kill |
| trigger | varchar | YES | Kill trigger type |
| reason | text | YES | Kill reason |
| scheduled_at | timestamptz | YES | Scheduled kill time |
| executed_at | timestamptz | YES | Actual kill time |
| status | varchar | YES | 'pending', 'executed', 'cancelled' |

---

### domain_purchase_jobs

Domain purchase job queue.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| id | uuid | NO | Primary key |
| client_id | uuid | NO | Parent client |
| status | varchar | YES | Job status |
| domains | jsonb | YES | Domains to purchase |
| registrar | varchar | YES | Target registrar |
| created_at | timestamptz | NO | Created timestamp |
| completed_at | timestamptz | YES | Completion timestamp |

---

### inbox_purchase_jobs

HyperTide order job queue.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| id | uuid | NO | Primary key |
| client_id | uuid | NO | Parent client |
| workspace_id | uuid | YES | Target workspace |
| provider | varchar | YES | 'entra' or 'google' |
| status | varchar | YES | Job status |
| domain_ids | jsonb | YES | Domains for order |
| order_count | integer | YES | Number of orders |
| created_at | timestamptz | NO | Created timestamp |
| completed_at | timestamptz | YES | Completion timestamp |

---

## Entity Relationships

```
clients
  ├── workspaces (1:1)
  │     ├── domains (1:N)
  │     │     └── sender_accounts (1:N)
  │     └── emailbison_campaigns (1:N)
  └── client_subscriptions (1:1)
        └── package_templates (N:1)

Domain Purchase Flow:
  clients → domain_purchase_jobs → domains

HyperTide Order Flow:
  clients → inbox_purchase_jobs → domains → sender_accounts
```

---

## Current Data (as of deployment)

| Table | Row Count |
|-------|-----------|
| clients | 15 |
| workspaces | 16 |
| domains | 512 |
| sender_accounts | 6,979 |
| emailbison_campaigns | 113 |
| kill_queue | 1,960 |
| package_templates | 2 |
| client_subscriptions | 2 |

---

## Migration History

Migrations are stored in `migrations/` directory and tracked in `_migrations` table.

Key migrations:
- `045_infrastructure_waterfall.sql` - Infrastructure views
- `052_add_connection_status_tracking.sql` - Connection status
- `053_fix_warmup_bounce_pollution.sql` - Bounce tracking fix
- `054_populate_total_sends_7d.sql` - Send tracking
- `058_operational_capacity_connection_status.sql` - Capacity views

Run migrations with:
```bash
python run_migrations.py
```
