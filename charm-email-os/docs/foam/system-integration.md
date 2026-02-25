---
title: System Integration
created: 2026-01-28
updated: 2026-01-28
tags: [hub, architecture, integration, platform]
---

# System Integration

How Charm Email OS, the [[lead-refinery|Lead Refinery]], and [[infrastructure|EmailBison]] work together as a unified outbound platform.

## Platform Overview

Three systems form a closed loop:

```
┌─────────────────────────────────────────────────────────────────┐
│                     CHARM EMAIL OS                               │
│  Next.js SaaS Platform (charm-email-os/)                        │
│                                                                 │
│  [[clients]] → [[campaigns]] → [[infrastructure]]               │
│  Client strategy,    Campaign ideas,   Domains, inboxes,        │
│  onboarding,         approval,         sender names,            │
│  ICP definition      email sequences   health monitoring        │
└────────────────────────────┬────────────────────────────────────┘
                             │
            Campaign needs leads (ICP criteria)
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    LEAD REFINERY                                 │
│  Python Pipeline (linkedin-scanner/contract_refinery/)          │
│                                                                 │
│  DuckDB (75.4M)  → [[lead-refinery-gates|Gates 0-3]]           │
│  Lead reservoir      Validate, enrich, verify employment        │
│                                                                 │
│  [[lead-dispositions]] ← [[lead-tam-map|TAM Map]]              │
│  State machine,         Enrichment data + performance           │
│  cooldowns              data flow back to database              │
└────────────────────────────┬────────────────────────────────────┘
                             │
            Verified leads pushed to campaign
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                      EMAILBISON                                  │
│  Campaign Execution Engine (spellcast.hirecharm.com)            │
│                                                                 │
│  Workspaces → Campaigns → Sequences → Sends                    │
│  Mapped to     Loaded with  4-email     Warmup,                 │
│  clients       verified     sequences   deliverability,         │
│                leads                    tracking                 │
└────────────────────────────┬────────────────────────────────────┘
                             │
            Performance data (opens, replies, bounces)
                             │
                             ▼
                    Back to Lead Refinery
                    (dispositions + TAM map updated)
```

## System Responsibilities

| System | Owns | Doesn't Own |
|--------|------|-------------|
| **Charm Email OS** | Client profiles, strategy, campaign ideas, domain/inbox provisioning, health monitoring | Lead verification, email sending, deliverability |
| **Lead Refinery** | Lead validation, enrichment, dispositions, TAM map, DuckDB reservoir | Campaign strategy, inbox provisioning, email sending |
| **EmailBison** | Email sending, warmup, deliverability, campaign execution, performance tracking | Strategy generation, lead verification, client management |

## End-to-End Flow

### Phase 1: Client Setup (Charm OS)

```
Create Client → Onboarding Wizard → Comprehensive Form
                                     ↓
                              ICP Definition:
                              • Industry
                              • Target titles
                              • Company size
                              • Geography
                              • Buying signals
                              • Personas
```

The [[onboarding-form|comprehensive onboarding form]] at `onboard.laviefatigue.com` captures the deep client context that later drives lead selection from the DuckDB reservoir.

**Key data that flows to Lead Refinery:**
- Industry and segment (for DuckDB ICP query)
- Target job titles (for filtering contacts)
- Company size ranges (for ICP matching)
- Geography targets (for location filtering)

### Phase 2: Infrastructure Provisioning (Charm OS → Hypertide → EmailBison)

```
Domain Discovery → Purchase → NS Verification → Inbox Setup
                      ↓
              ┌───────────────────────────────────────────────┐
              │ Purchase Worker (Claude Code + Playwright)     │
              │ Autonomous browser automation on Hypertide     │
              │                                               │
              │ 1. Login to app2.hypertide.io                 │
              │ 2. Select provider (Entra/Google)             │
              │ 3. Enter domains (BYOD)                       │
              │ 4. Select EmailBison workspace via API key    │
              │ 5. Configure sender names                     │
              │ 6. Complete checkout                           │
              │                                               │
              │ Credentials: ENV vars on worker container     │
              │ Workspace: Per-job from database              │
              └───────────────────────────────────────────────┘
                      ↓
              Hypertide Provisioning
                      ↓
              EmailBison Upload
              (workspace + inboxes)
```

See [[purchase-worker]] for full architecture details.

[[infrastructure|Infrastructure]] is provisioned through Charm OS and registered in EmailBison:

- **Client → Workspace**: Each Charm OS client maps to an EmailBison workspace via `workspaceId`
- **Domains → Sending domains**: Purchased domains (Entra or Google) become sending infrastructure
- **Inboxes → Sender accounts**: Provisioned inboxes become EmailBison sender accounts via `emailbisonAccountId`
- **Sender Names**: Generated from [[sender-names|base names]] with 10+ pattern variations

### Phase 3: Campaign Strategy (Charm OS)

```
Onboarding Data → Strategy AI Container → 4-Email Sequences
                   (Claude Code)              ↓
                                        Review & Approve
                                              ↓
                                        Apply Spintax
                                              ↓
                                        Push to EmailBison
```

The [[strategy-ai-container]] uses client onboarding data to autonomously generate campaign sequences. Approved sequences are pushed to EmailBison as campaigns, ready for leads.

### Phase 4: Campaign Fill (Lead Refinery → EmailBison)

This is where the [[lead-refinery]] connects to Charm OS campaigns:

```
EmailBison Campaign (needs leads)
    ↓
Extract ICP from campaign strategy goals
    ↓
Query DuckDB reservoir (75.4M leads)
    WHERE industry MATCHES campaign.industry
    AND title MATCHES campaign.titles
    AND company_size >= campaign.min_size
    AND disposition_status IN ('fresh', 'retouch_eligible')
    ↓
[[lead-refinery-gates|Waterfall Validation]]
    Gate 0: Pre-validation (FREE)
    Gate 1: Email verification ($0.005)
    Gate 2: AI-ARK employment check ($0.005)
    Gate 3: Spider+Jina rescue ($0.002)
    ↓
Push verified leads INTO EmailBison campaign
    ↓
Campaign executes sequence sends
```

See [[lead-tam-map]] for the full closed-loop flow.

### Phase 5: Performance Tracking (EmailBison → Lead Refinery)

```
EmailBison tracks engagement
    ↓
Performance data synced back:
    • Delivered → disposition: in_sequence
    • Opened → engaged signal
    • Replied positive → replied_positive (sales pipeline)
    • Replied negative → replied_negative (180-day cooldown)
    • Bounced → bounced (permanent email suppress)
    • Unsubscribed → unsubscribed (CAN-SPAM suppress)
    ↓
[[lead-dispositions]] updated in DuckDB
    ↓
[[lead-tam-map|TAM map]] evolves
    ↓
Next campaign pull is smarter and cheaper
```

### Phase 6: Health Monitoring (Charm OS ← EmailBison)

```
EmailBison reports:
    • Bounce rates per inbox
    • Spam complaints
    • Warmup progress
    ↓
Charm OS [[health-monitoring]] evaluates:
    • Kill triggers (instant or confirming)
    • Domain lifecycle phase
    • ESP reputation (Gmail, Microsoft)
    • Backup capacity ratio
    ↓
Actions:
    • Kill dead inboxes
    • Flag/kill domains
    • Rotate aging domains
    • Quarantine bad campaigns
```

## Data Flow Map

### Client Identity

```
Charm OS Client
    ├── client.id ──────────→ Lead Refinery (client_contract_id)
    ├── client.workspaceId ─→ EmailBison Workspace
    ├── client.domain ──────→ Primary domain for variations
    └── client.onboardingData
         ├── industry ──────→ DuckDB ICP query filter
         ├── titles ────────→ DuckDB title matching
         └── personas ──────→ Campaign angle selection
```

### Infrastructure Identity

```
Charm OS Domain
    ├── domain.id ──────────→ Charm OS tracking
    ├── domain.domainName ──→ EmailBison sending domain
    └── domain.healthState ─→ Health monitoring (live/flagged/dead)

Charm OS Inbox
    ├── inbox.id ───────────→ Charm OS tracking
    ├── inbox.emailbisonAccountId → EmailBison sender account
    ├── inbox.email ────────→ From address for sends
    └── inbox.healthState ──→ Kill trigger evaluation
```

### Campaign Identity

```
Charm OS Campaign Idea
    ├── idea.industry ──────→ DuckDB ICP query
    ├── idea.segment ───────→ DuckDB segment filter
    ├── idea.angle ─────────→ Email sequence strategy
    └── idea.email1 + followUps → EmailBison 4-email sequence

Charm OS Campaign
    ├── campaign.emailbisonCampaignId → EmailBison campaign
    ├── campaign.leadsTotal ──────────→ Filled by Lead Refinery
    └── campaign.repliesCount ────────→ Performance from EmailBison
```

### Lead Identity

```
DuckDB Contact (75.4M reservoir)
    ├── contact.email ──────→ EmailBison lead
    ├── contact.disposition → State machine (fresh/in_sequence/etc.)
    ├── contact.enriched_* ─→ AI-ARK enrichment data
    ├── contact.freshness_score → Priority for campaign fill
    └── contact.client_contract_id → Which client consumed this lead

EmailBison Lead (in campaign)
    ├── lead.email ─────────→ Sends to this address
    ├── lead.status ────────→ Performance tracking
    └── lead.engagement ────→ Synced back to DuckDB disposition
```

## Database Architecture

```
┌──────────────────────┐     ┌──────────────────────┐
│   Supabase PostgreSQL │     │     DuckDB            │
│   (Charm OS + OwnRBL)│     │  (Lead Refinery)      │
│                      │     │                      │
│  clients             │     │  contacts (75.4M)    │
│  domains             │     │    ├── email         │
│  sender_accounts     │     │    ├── disposition   │
│  campaigns           │     │    ├── enriched_*    │
│  strategy_jobs       │     │    ├── freshness     │
│  onboarding_*        │     │    └── client_id     │
│  health_metrics      │     │                      │
└──────────┬───────────┘     └──────────┬───────────┘
           │                            │
           │   ┌────────────────────┐   │
           └──→│    EmailBison API   │←──┘
               │  (Execution Engine) │
               │                    │
               │  workspaces        │
               │  campaigns         │
               │  sender_accounts   │
               │  warmup_data       │
               │  performance_data  │
               └────────────────────┘
```

## Integration Points (API Level)

### Charm OS → EmailBison

| Action | Charm OS Trigger | EmailBison Effect |
|--------|-----------------|-------------------|
| Inbox provisioning | Hypertide creates inbox | Sender account registered |
| Campaign push | Approve + push sequence | Campaign created with 4 emails |
| Warmup control | Enable/disable warmup | Warmup schedule adjusted |
| Health response | Kill inbox | Sender account deactivated |

### Lead Refinery → EmailBison

| Action | Refinery Trigger | EmailBison Effect |
|--------|-----------------|-------------------|
| Campaign fill | ICP query + validation | Leads loaded into campaign |
| Lead refresh | Freshness worker | Updated contact data |

### EmailBison → Lead Refinery

| Action | EmailBison Event | Refinery Effect |
|--------|-----------------|-----------------|
| Delivery confirmed | Email delivered | Disposition: `in_sequence` |
| Engagement | Email opened/clicked | Engagement signal logged |
| Positive reply | Reply with interest | Disposition: `replied_positive` |
| Bounce | Email bounced | Disposition: `bounced`, email suppressed |
| Unsubscribe | Opt-out clicked | Disposition: `unsubscribed`, CAN-SPAM |

### EmailBison → Charm OS

| Action | EmailBison Event | Charm OS Effect |
|--------|-----------------|-----------------|
| Bounce spike | Hard bounces > threshold | Kill trigger: inbox flagged/dead |
| Spam complaint | Complaint reported | Kill trigger: instant action |
| Warmup progress | Daily warmup stats | Health dashboard updated |
| Campaign stats | Opens/replies/bounces | Campaign performance view |

## Repository Structure

```
D:\Work\
├── charm-email-os/charm-email-os/     # Charm Email OS (Next.js)
│   ├── app/                            #   Pages and routes
│   ├── components/                     #   React components
│   ├── lib/                            #   API, stores, types
│   └── docs/foam/                      #   This documentation
│
├── linkedin-scanner/                   # Lead Refinery (Python)
│   ├── contract_refinery/              #   Pipeline modules
│   │   ├── gate0_prevalidation.py      #     Gate 0 (FREE)
│   │   ├── email_verifier.py           #     Gate 1 (email check)
│   │   ├── refinery.py                 #     Orchestrator
│   │   └── freshness_worker.py         #     Background maintenance
│   ├── aiark_client.py                 #   Gate 2 (AI-ARK)
│   └── linkedin.duckdb                 #   75.4M lead reservoir
│
└── Email-Bison MCP/                    # EmailBison MCP Server
    └── (MCP tools for campaign management)
```

## Related

- [[architecture]] - Charm OS internal architecture
- [[clients]] - Client entity and onboarding
- [[campaigns]] - Campaign ideas and execution
- [[leads]] - Lead management in Charm OS
- [[lead-refinery]] - Lead verification pipeline
- [[lead-tam-map]] - Closed-loop TAM map
- [[lead-dispositions]] - Lead state machine
- [[infrastructure]] - Domain and inbox provisioning
- [[health-monitoring]] - Health tracking and kill triggers
- [[workflows]] - User workflows

---
Tags: #hub #architecture #integration #platform #emailbison #lead-refinery
