# 🗺️ Complete Infrastructure Process Map

## Client Onboarding → Infrastructure Management Lifecycle

---

## Overview

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                           PHASE 1: ONBOARDING                                │
│  ┌─────────┐   ┌─────────┐   ┌─────────┐   ┌─────────┐   ┌─────────┐        │
│  │ Client  │──▶│  Bison  │──▶│ Domain  │──▶│Hypertide│──▶│  DNS    │        │
│  │  Form   │   │Workspace│   │Sourcing │   │ BYOD    │   │  Setup  │        │
│  │ [HUMAN] │   │ [MANUAL]│   │ [AUTO]  │   │ [AUTO]  │   │ [AUTO]  │        │
│  └─────────┘   └─────────┘   └─────────┘   └─────────┘   └─────────┘        │
└──────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                           PHASE 2: WARMING                                   │
│  ┌─────────┐   ┌─────────┐   ┌─────────┐   ┌─────────┐                      │
│  │  Bison  │──▶│ Warmup  │──▶│ Health  │──▶│   AM    │                      │
│  │ Connect │   │ Ramp-up │   │ Monitor │   │ Handoff │                      │
│  │ [AUTO]  │   │[MONITOR]│   │[MONITOR]│   │ [HUMAN] │                      │
│  └─────────┘   └─────────┘   └─────────┘   └─────────┘                      │
└──────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                        PHASE 3: OPERATIONS                                   │
│  ┌─────────┐   ┌─────────┐   ┌─────────┐   ┌─────────┐                      │
│  │Campaign │──▶│ Inbox   │──▶│ Issue   │──▶│ Domain  │                      │
│  │ Launch  │   │ Health  │   │Response │   │ Renewal │                      │
│  │ [HUMAN] │   │[MONITOR]│   │ [ALERT] │   │ [ALERT] │                      │
│  └─────────┘   └─────────┘   └─────────┘   └─────────┘                      │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## Automation Levels

| Level | Symbol | Description | Human Involvement |
|-------|--------|-------------|-------------------|
| L0 | `[HUMAN]` | Fully manual step | Required |
| L1 | `[MANUAL]` | Manual with tooling assistance | Required with guidance |
| L2 | `[CHECKPOINT]` | Automated with human approval gate | Approval only |
| L3 | `[AUTO]` | Fully automated execution | None (unless error) |
| L4 | `[MONITOR]` | Automated with human monitoring | Periodic review |
| L5 | `[ALERT]` | Automated with exception alerts | On-demand response |

---

## Phase 1: Client Onboarding

### Step 1.1: Client Intake Form
**Level:** `[HUMAN]`
**Owner:** Sales/Account Manager
**Duration:** 10-30 minutes

```yaml
Inputs:
  - Client company name
  - Industry vertical
  - Target audience
  - Brand keywords
  - Inbox requirements (Entra count, Google count)
  - Budget approval status
  - Urgency level

Outputs:
  - Client record in database
  - Inbox target specification
  - Trigger for next step

Trigger: Sales closes deal / client signs contract
```

**Data Captured:**
| Field | Example | Used By |
|-------|---------|---------|
| `client_name` | "Acme Corp" | All steps |
| `industry` | "SaaS" | Domain generator |
| `brand_keywords` | ["outreach", "growth"] | Domain generator |
| `target_audience` | "Enterprise CTOs" | Domain generator |
| `entra_inbox_count` | 600 | Order calculation |
| `google_inbox_count` | 45 | Order calculation |
| `forwarding_domain` | "acme.com" | Hypertide purchase |

---

### Step 1.2: Bison Workspace Setup
**Level:** `[MANUAL]`
**Owner:** Infrastructure Team
**Duration:** 30 minutes

```yaml
Inputs:
  - Client name
  - Workspace naming convention

Actions:
  - Log into EmailBison admin panel
  - Create new workspace
  - Configure timezone
  - Set sending limits (warming phase)
  - Enable tracking (opens, clicks, replies)
  - Generate API keys (if needed)
  - Document workspace ID

Outputs:
  - Workspace ID
  - API credentials (if applicable)
  - Bison credentials for Hypertide

Dependencies: Step 1.1 complete
```

**Future Automation Opportunity:**
```python
# Could be automated via EmailBison MCP
async def create_bison_workspace(client_name: str) -> BisonCredentials:
    workspace = await bison_mcp.create_workspace(
        name=f"{client_name} - Outbound",
        timezone="America/New_York",
        sending_limits={"daily": 50, "hourly": 10},  # Warming limits
    )
    return BisonCredentials(
        workspace=workspace.name,
        api_key=workspace.api_key,
    )
```

---

### Step 1.3: Domain Sourcing
**Level:** `[AUTO]` + `[CHECKPOINT]`
**Owner:** Infrastructure Team (approval only)
**Duration:** 5-10 minutes
**Tool:** `domain-source` CLI

```yaml
Inputs:
  - Client name
  - Industry
  - Brand keywords
  - Domain count requirements
  - Price constraints

Substeps:
  1.3.1 AI Domain Generation [AUTO]
    - Generate 3x required domain candidates
    - Score for legitimacy (0-1)
    - Apply brand alignment

  1.3.2 Multi-Registrar Search [AUTO]
    - Check Porkbun availability + pricing
    - Check DynaDot availability + pricing
    - Generate TLD and name variations
    - Calculate value scores

  1.3.3 Human Approval [CHECKPOINT]
    - Present ranked candidates
    - Human selects required count
    - Confirm purchase authorization

  1.3.4 Domain Purchase [AUTO]
    - Purchase from best-price registrar
    - Set Hypertide-compatible nameservers
    - Enable WHOIS privacy
    - Log purchase receipts

Outputs:
  - List of purchased domains
  - Registrar confirmations
  - DomainConfig objects for Hypertide

Dependencies: Step 1.2 complete (need Bison workspace ID)
```

**CLI Command:**
```bash
domain-source source \
  --client "Acme Corp" \
  --industry "SaaS" \
  --entra 6 \
  --google 5 \
  --keywords "outreach,growth,scale" \
  --target-price 8.00 \
  --max-price 15.00
```

**Detailed Flow:**
```
┌────────────────────┐
│   Client Context   │
│  (name, industry,  │
│   keywords, etc.)  │
└─────────┬──────────┘
          │
          ▼
┌────────────────────┐     ┌────────────────────┐
│   AI Generator     │────▶│   33 Candidates    │
│   (GPT-4/Claude)   │     │   with scores      │
└────────────────────┘     └─────────┬──────────┘
                                     │
          ┌──────────────────────────┼──────────────────────────┐
          ▼                          ▼                          ▼
┌──────────────────┐      ┌──────────────────┐      ┌──────────────────┐
│    Porkbun API   │      │   DynaDot API    │      │  Variation Gen   │
│  check + pricing │      │  check + pricing │      │  (TLDs, names)   │
└────────┬─────────┘      └────────┬─────────┘      └────────┬─────────┘
         │                         │                         │
         └─────────────────────────┼─────────────────────────┘
                                   │
                                   ▼
                    ┌────────────────────────────┐
                    │     Value Scoring          │
                    │  price + legitimacy + TLD  │
                    │       + deal bonus         │
                    └─────────────┬──────────────┘
                                  │
                                  ▼
                    ┌────────────────────────────┐
                    │   HUMAN APPROVAL GATE      │
                    │   Select 11 domains        │
                    └─────────────┬──────────────┘
                                  │
          ┌───────────────────────┼───────────────────────┐
          ▼                       ▼                       ▼
┌──────────────────┐   ┌──────────────────┐   ┌──────────────────┐
│ Porkbun Purchase │   │ DynaDot Purchase │   │  Set Nameservers │
│   (if cheapest)  │   │   (if cheapest)  │   │  (for Hypertide) │
└──────────────────┘   └──────────────────┘   └──────────────────┘
                                  │
                                  ▼
                    ┌────────────────────────────┐
                    │   11 Purchased Domains     │
                    │   with BYOD configs        │
                    └────────────────────────────┘
```

---

### Step 1.4: Hypertide BYOD Purchase
**Level:** `[AUTO]`
**Owner:** Infrastructure Team (monitoring)
**Duration:** 15-30 minutes per order
**Tool:** `hypertide-purchase` CLI

```yaml
Inputs:
  - Purchased domains (from Step 1.3)
  - Bison credentials (from Step 1.2)
  - Forwarding domain
  - Inbox target counts

Substeps:
  1.4.1 Calculate Order Quantities [AUTO]
    - Entra orders = ceil(entra_inboxes / 100)
    - Google orders = ceil(google_inboxes / 15)

  1.4.2 Execute Entra Purchase [AUTO]
    - Navigate to Hypertide
    - Select Entra plan
    - Enter quantity
    - Add BYOD domains
    - Configure settings (Bison integration)
    - Complete payment

  1.4.3 Execute Google Purchase [AUTO]
    - Same flow for Google Workspace
    - Different domain allocation

  1.4.4 Capture Order Details [AUTO]
    - Order confirmation IDs
    - Created domain list
    - Inbox credentials

Outputs:
  - Order confirmation IDs
  - List of created inboxes
  - DNS records to configure
  - Inbox credentials

Dependencies: Step 1.3 complete (purchased domains)
```

**Order Calculation:**
```
Target: 600 Entra inboxes, 45 Google inboxes

Entra:
  - 100 inboxes per order (2 domains × 50 inboxes)
  - Orders needed: ceil(600/100) = 6
  - Domains needed: 6 × 2 = 12

Google:
  - 15 inboxes per order (5 domains × 3 inboxes)
  - Orders needed: ceil(45/15) = 3
  - Domains needed: 3 × 5 = 15

Total: 27 domains, 9 orders, $450/month
```

---

### Step 1.5: DNS Configuration
**Level:** `[AUTO]` (via Hypertide)
**Owner:** Hypertide (automatic)
**Duration:** Included in Step 1.4

```yaml
Inputs:
  - Domains from Step 1.4
  - Hypertide DNS requirements

Records Configured:
  - MX records (email delivery)
  - SPF records (sender policy)
  - DKIM records (signing)
  - DMARC records (policy)

Verification:
  - Automatic propagation check
  - 24-48 hour window for propagation
  - MXToolbox verification recommended

Outputs:
  - DNS configuration complete
  - Records propagated
  - Ready for email sending

Dependencies: Step 1.4 complete
```

---

## Phase 2: Warming & Activation

### Step 2.1: Bison Inbox Connection
**Level:** `[AUTO]` (via Hypertide)
**Owner:** Hypertide (automatic)
**Duration:** Automatic during purchase

```yaml
Inputs:
  - Bison credentials (from Step 1.2)
  - Created inboxes (from Step 1.4)

Actions:
  - Connect each inbox to Bison workspace
  - Enable warmup protocols
  - Set initial sending volumes

Outputs:
  - All inboxes connected to Bison
  - Warmup initiated

Dependencies: Step 1.4 complete
```

---

### Step 2.2: Warmup Ramp-up
**Level:** `[MONITOR]`
**Owner:** Infrastructure Team (monitoring)
**Duration:** 14-21 days

```yaml
Timeline:
  Days 1-3:   5-10 emails/account/day
  Days 4-7:   15-25 emails/account/day
  Days 8-14:  30-50 emails/account/day
  Days 15-21: 50-75 emails/account/day
  Days 21+:   75-100 emails/account/day (campaign ready)

Monitoring Points:
  - Bounce rate (target: <2%)
  - Spam complaints (target: <0.1%)
  - Open rates (healthy: >20%)
  - Sender reputation scores

Alerts:
  - High bounce rate detected
  - Spam complaint spike
  - Account suspension
  - Health score drop

Dependencies: Step 2.1 complete
```

**Monitoring Integration (EmailBison MCP):**
```bash
# Check warmup status across all inboxes
emailbison get_warmup_status_dashboard --workspace "Acme Corp"

# Detect anomalies
emailbison detect_infrastructure_anomalies --workspace "Acme Corp"
```

---

### Step 2.3: Health Monitoring
**Level:** `[MONITOR]` + `[ALERT]`
**Owner:** Infrastructure Team
**Duration:** Ongoing

```yaml
Metrics Tracked:
  - Inbox health scores (0-100)
  - Provider distribution (Entra vs Google)
  - Connection status (connected/disconnected)
  - Sending velocity
  - Deliverability rates

Alert Thresholds:
  - Health score < 50: Warning
  - Health score < 30: Critical
  - Disconnection: Immediate alert
  - Bounce rate > 5%: Warning
  - Bounce rate > 10%: Critical

Tools:
  - EmailBison MCP for real-time monitoring
  - Daily health checks (automated)
  - Weekly reports (automated)

Dependencies: Step 2.2 ongoing
```

---

### Step 2.4: Account Manager Handoff
**Level:** `[HUMAN]`
**Owner:** Infrastructure Team → Account Manager
**Duration:** 20 minutes

```yaml
Inputs:
  - All accounts verified accessible
  - DNS fully propagated
  - Warmup complete (or on track)
  - Health scores acceptable

Handoff Package:
  - Bison workspace access
  - Email account credentials
  - DNS configuration summary
  - Warmup status report
  - Troubleshooting contacts
  - SLA expectations

Sign-off:
  - AM confirms access
  - AM understands timeline
  - Documentation complete
  - Task marked complete

Outputs:
  - Signed-off infrastructure
  - AM has full control
  - Infrastructure team on standby

Dependencies: Steps 2.1-2.3 satisfactory
```

---

## Phase 3: Operations & Maintenance

### Step 3.1: Campaign Launch
**Level:** `[HUMAN]`
**Owner:** Account Manager
**Duration:** Ongoing

```yaml
Actions:
  - Create campaigns in Bison
  - Upload lead lists
  - Configure sequences
  - Set sending schedules
  - Monitor performance

Tools:
  - EmailBison workspace
  - Lead list management
  - A/B testing

Guardrails:
  - Respect sending limits
  - Quality lead lists
  - Compliance (CAN-SPAM, GDPR)
```

---

### Step 3.2: Inbox Health Monitoring
**Level:** `[MONITOR]`
**Owner:** Infrastructure Team (automated)
**Duration:** Ongoing

```yaml
Automated Checks:
  - Daily health score snapshot
  - Weekly trend analysis
  - Anomaly detection

Integration:
  - EmailBison MCP monitoring tools
  - Slack alerts for issues
  - Dashboard for visibility

Actions on Alert:
  - Investigate root cause
  - Pause affected campaigns
  - Remediate issues
  - Resume when healthy
```

**Monitoring Commands:**
```bash
# Infrastructure overview
emailbison get_infrastructure_overview --workspace "Acme Corp"

# Capacity analysis
emailbison get_capacity_analysis --workspace "Acme Corp"

# Send velocity
emailbison get_send_velocity_realtime --workspace "Acme Corp"
```

---

### Step 3.3: Issue Response
**Level:** `[ALERT]`
**Owner:** Infrastructure Team
**Duration:** As needed

```yaml
Issue Types:
  1. Account Suspension
     - Pause sending immediately
     - Investigate cause
     - Re-warm if needed
     - Update procedures

  2. Deliverability Drop
     - Check reputation
     - Review list quality
     - Adjust sending patterns
     - Consider domain rotation

  3. High Bounce Rate
     - Verify email list
     - Check domain reputation
     - Investigate blocks

  4. Provider Issues
     - Microsoft/Google outages
     - API rate limits
     - Authentication problems

Escalation Path:
  1. Infrastructure Team (first response)
  2. Hypertide Support
  3. EmailBison Support
  4. Provider support (Microsoft/Google)
```

---

### Step 3.4: Domain Renewal
**Level:** `[ALERT]`
**Owner:** Infrastructure Team
**Duration:** Annual

```yaml
Tracking:
  - Domain expiration dates
  - Registrar account status
  - Auto-renewal settings

Alerts:
  - 60 days before expiration: Reminder
  - 30 days before expiration: Warning
  - 7 days before expiration: Critical

Actions:
  - Verify payment methods
  - Confirm auto-renewal
  - Manual renewal if needed
  - Update tracking records
```

---

## Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              DATA STORES                                    │
│                                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │
│  │   Client     │  │   Domain     │  │   Inbox      │  │   Campaign   │    │
│  │   Records    │  │   Inventory  │  │   Inventory  │  │   Data       │    │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘    │
│         │                 │                 │                 │             │
└─────────┼─────────────────┼─────────────────┼─────────────────┼─────────────┘
          │                 │                 │                 │
          ▼                 ▼                 ▼                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              TOOLS & SYSTEMS                                │
│                                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │
│  │  Domain      │  │  Hypertide   │  │  EmailBison  │  │  Monitoring  │    │
│  │  Sourcing    │  │  Automation  │  │     MCP      │  │  Dashboard   │    │
│  │    CLI       │  │     CLI      │  │              │  │              │    │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
          │                 │                 │                 │
          ▼                 ▼                 ▼                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           EXTERNAL SERVICES                                 │
│                                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │
│  │   Porkbun    │  │   Hypertide  │  │  Microsoft   │  │   Google     │    │
│  │   DynaDot    │  │   Platform   │  │    Entra     │  │  Workspace   │    │
│  │  (Domains)   │  │   (Infra)    │  │   (Email)    │  │   (Email)    │    │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## State Machine

```
                              ┌─────────────────┐
                              │     START       │
                              └────────┬────────┘
                                       │
                                       ▼
                              ┌─────────────────┐
                              │  INTAKE_PENDING │
                              └────────┬────────┘
                                       │ Client form submitted
                                       ▼
                              ┌─────────────────┐
                              │ WORKSPACE_SETUP │
                              └────────┬────────┘
                                       │ Bison workspace created
                                       ▼
                              ┌─────────────────┐
                              │ DOMAIN_SOURCING │◀──────────────┐
                              └────────┬────────┘               │
                                       │ Domains approved       │ Need more domains
                                       ▼                        │
                              ┌─────────────────┐               │
                              │ DOMAINS_PURCHASED│──────────────┘
                              └────────┬────────┘
                                       │ Purchase complete
                                       ▼
                              ┌─────────────────┐
                              │ HYPERTIDE_SETUP │
                              └────────┬────────┘
                                       │ Accounts created
                                       ▼
                              ┌─────────────────┐
                              │    WARMING      │
                              └────────┬────────┘
                                       │ 14-21 days
                                       ▼
                              ┌─────────────────┐
                              │  AM_HANDOFF     │
                              └────────┬────────┘
                                       │ Signed off
                                       ▼
                              ┌─────────────────┐
                              │   OPERATIONAL   │◀──────────────┐
                              └────────┬────────┘               │
                                       │                        │
                    ┌──────────────────┼──────────────────┐     │
                    ▼                  ▼                  ▼     │
           ┌─────────────┐    ┌─────────────┐    ┌─────────────┐│
           │ ISSUE_ALERT │    │  EXPANSION  │    │  RENEWAL    ││
           └──────┬──────┘    └──────┬──────┘    └──────┬──────┘│
                  │                  │                  │       │
                  └──────────────────┴──────────────────┴───────┘
                              Resolved/Complete
```

---

## Tool Summary

| Tool | Purpose | Phase | Automation Level |
|------|---------|-------|------------------|
| `domain-source source` | Full domain sourcing workflow | 1.3 | AUTO + CHECKPOINT |
| `domain-source fuzzy` | Quick domain search | 1.3 | AUTO |
| `domain-source generate` | AI domain generation only | 1.3 | AUTO |
| `domain-source search` | Registrar search only | 1.3 | AUTO |
| `domain-source registrars` | Check API configuration | Setup | INFO |
| `hypertide-purchase` | Hypertide browser automation | 1.4 | AUTO |
| EmailBison MCP | Workspace/inbox management | 2.x, 3.x | AUTO/MONITOR |

---

## Metrics & KPIs

### Onboarding Metrics
| Metric | Target | Measured At |
|--------|--------|-------------|
| Onboarding time (total) | < 4 hours active | End of Phase 1 |
| Domain cost per domain | < $8 average | Step 1.3 |
| Domain sourcing time | < 10 minutes | Step 1.3 |
| Hypertide setup time | < 30 min/order | Step 1.4 |

### Operational Metrics
| Metric | Target | Measured At |
|--------|--------|-------------|
| Inbox health score | > 70 average | Daily |
| Deliverability rate | > 95% | Weekly |
| Bounce rate | < 2% | Per campaign |
| Warmup completion | 21 days | Step 2.2 |

### Efficiency Metrics
| Metric | Before Automation | After Automation |
|--------|-------------------|------------------|
| Domain research | 30 min manual | 5 min auto |
| Domain purchase | 15 min/domain | 30 sec/domain |
| Total onboarding | 6+ hours | < 2 hours active |
| Human approval points | Many | 1 checkpoint |

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | December 2024 | Initial process map |
