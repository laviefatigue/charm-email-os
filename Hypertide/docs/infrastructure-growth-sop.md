# 📋 Infrastructure Growth SOP
## Cold Email Infrastructure Creation & Deployment

---

### Document Overview

| Field | Value |
|-------|-------|
| **Process Name** | Growth Infrastructure Creation |
| **Total Duration** | 4-6 hours (spread over 2-3 weeks for warming) |
| **Owner** | Growth/Sales Operations Team |
| **Last Updated** | Extracted from ClickUp Task #86abcqj5r |

---

## 🎯 Purpose & Scope

This SOP outlines the complete process for setting up cold email infrastructure, from domain acquisition through email account creation, warming, and handoff to Account Managers. The process ensures deliverability optimization and reputation protection.

---

## ✅ Prerequisites

Before beginning this process, ensure you have:

| Requirement | Details |
|-------------|---------|
| **Domain Names** | List of domains to purchase (checked for availability) |
| **Budget Approval** | $10-15 per domain approved |
| **Registrar Access** | Credentials for Porkbun and/or DynaDot |
| **EmailBison (Bison) Credentials** | Admin access to create workspaces |
| **Hypertide Access** | Login credentials for infrastructure provisioning |
| **Azure/Google Admin Access** | For Microsoft Entra and Google Workspace setup |

---

## 📊 Infrastructure Capacity Reference

| Provider | Domains per Order | Inboxes per Domain | Total per Order |
|----------|-------------------|-------------------|-----------------|
| **Microsoft Entra (Azure)** | 2 | 50 | 100 inboxes |
| **Google Workspace** | 5 | 3 | 15 inboxes |
| **Standard Build** | Mixed | Mixed | 5 Google + 6 Azure = 11 accounts |

---

## 🔄 Process Overview

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  Step 1: Bison  │───▶│  Step 2: Domain │───▶│  Step 3:        │
│  Workspace      │    │  Sourcing       │    │  Hypertide      │
│  (30 min)       │    │  (AUTOMATED)    │    │  Setup (AUTO)   │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                                      │
                                                      ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  Step 6:        │◀───│  Step 5: AM     │◀───│  Step 4:        │
│  Campaign       │    │  Verification   │    │  Warming        │
│  Launch         │    │  (20 min)       │    │  (14-21 days)   │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

### Automation Level Legend
- **AUTOMATED**: Fully automated via Python scripts
- **HUMAN CHECKPOINT**: Requires human approval before proceeding
- **MONITORING**: Automated monitoring with human alerts

---

## Step 1: ⚡ Bison Workspace Registration & Setup

**Duration:** 30 minutes
**Owner:** Infrastructure Team

### 1.1 Create New Workspace
- [ ] Log into EmailBison (Bison) admin panel
- [ ] Navigate to Workspace Management
- [ ] Create new workspace with client/campaign naming convention
- [ ] Document workspace ID and access URL

### 1.2 Configure Workspace Settings
- [ ] Set sending limits appropriate for warming phase
- [ ] Configure timezone settings
- [ ] Set up notification preferences
- [ ] Enable tracking settings (opens, clicks, replies)

### 1.3 Prepare for Integration
- [ ] Generate API keys if needed for automation
- [ ] Document integration endpoints
- [ ] Test workspace connectivity

### 1.4 Plan Account Distribution
- [ ] Determine number of Google vs Azure accounts needed
- [ ] Plan inbox naming conventions
- [ ] Allocate domains to account types

**Output:** Workspace ID, access credentials, distribution plan

---

## Step 2: 🤖 Automated Domain Sourcing (AUTOMATED + HUMAN CHECKPOINT)

**Duration:** 5-10 minutes (mostly automated)
**Owner:** Infrastructure Team
**Automation:** `domain-source` CLI tool

### 2.1 Run Domain Sourcing Workflow

```bash
# Full automated workflow with interactive approval
domain-source source \
    --client "Acme Corp" \
    --industry "SaaS" \
    --entra 6 \
    --google 5 \
    --keywords "outreach,growth,scale" \
    --target-price 8.00 \
    --max-price 15.00
```

**What happens automatically:**
1. **AI Domain Generation**: GPT-4/Claude generates brand-appropriate domain candidates
2. **Multi-Registrar Search**: Checks Porkbun and DynaDot for availability & pricing
3. **Variation Expansion**: Generates TLD and name variations to find deals
4. **Value Ranking**: Scores domains by price, legitimacy, and promotional status

### 2.2 Human Approval Checkpoint

The CLI presents top candidates sorted by value:
```
============================================================
DOMAIN APPROVAL - Need 11 domains
============================================================

Top Available Domains (sorted by value):
------------------------------------------------------------
  1. outreach-acme.com           $  6.99 (porkbun) [DEAL!]
  2. growthforge.io              $  8.49 (porkbun)
  3. acme-connect.co             $  7.99 (dynadot) [DEAL!]
  4. scale-acme.com              $  9.73 (porkbun)
  ...
------------------------------------------------------------

Enter domain numbers to approve (comma-separated, need 11):
Example: 1,3,5,7,9,11 or 'all' for first N or 'q' to quit
> 1,2,3,4,5,6,7,8,9,10,11
```

### 2.3 Automatic Purchase

After approval, domains are purchased automatically from their respective registrars:
- Nameservers pre-configured for Hypertide
- WHOIS privacy enabled (where included)
- Purchase receipts logged

### 2.4 Alternative: Quick Fuzzy Search

For specific domain ideas:
```bash
# Search for variations of a specific domain
domain-source fuzzy "acme-growth.com" --max-price 10
```

### 2.5 Alternative: Manual Generation + Search

For more control:
```bash
# Step 1: Generate candidates
domain-source generate \
    --client "Acme Corp" \
    --industry "SaaS" \
    --keywords "outreach,growth" \
    --output candidates.json

# Step 2: Search registrars
domain-source search candidates.json \
    --max-price 10 \
    --output results.json
```

### 2.6 Configuration Check

Before first use:
```bash
# Verify registrar and AI API keys
domain-source registrars
```

Required environment variables:
- `PORKBUN_API_KEY` + `PORKBUN_API_SECRET`
- `DYNADOT_API_KEY` (optional, additional registrar)
- `OPENAI_API_KEY` (optional, for AI domain generation)

**Output:** Purchased domains with Hypertide-compatible nameservers

---

### Legacy: Manual Domain Research (Deprecated)

<details>
<summary>Click to expand manual process (use only if automation fails)</summary>

#### Check Promotions
- [ ] Visit [Porkbun](https://porkbun.com) - check current sales/promotions
- [ ] Visit [DynaDot](https://dynadot.com) - check current sales/promotions
- [ ] Compare pricing between registrars
- [ ] Note any bulk discount opportunities

#### Domain Availability Check
- [ ] Prepare list of desired domain names
- [ ] Check availability on both registrars
- [ ] Verify domains are not blacklisted (check MXToolbox)
- [ ] Ensure domains have clean history (check archive.org)

#### Cost Analysis
| Domain | Registrar | Regular Price | Sale Price | Notes |
|--------|-----------|--------------|------------|-------|
| | | | | |

**Target Budget:** $3-8 per domain (promotional), $10-15 max

#### Get Approval
- [ ] Compile domain list with total cost
- [ ] Submit for budget approval
- [ ] Document approval in ticket/task

</details>

---

## Step 3: 📧 Hypertide Email Infrastructure Setup

**Duration:** 2 hours
**Owner:** Infrastructure Team

### 3.1 Pre-Setup Checklist
- [ ] Approved domain list ready
- [ ] Payment method configured in Hypertide
- [ ] Bison workspace prepared
- [ ] DNS management access confirmed

### 3.2 Domain Purchase & DNS Configuration
- [ ] Purchase approved domains through selected registrar
- [ ] Configure nameservers as required by Hypertide
- [ ] Set up MX records for email delivery
- [ ] Configure SPF records
- [ ] Configure DKIM records
- [ ] Configure DMARC records

### 3.3 Email Account Provisioning

#### Google Workspace Accounts (5 accounts)
- [ ] Create Google Workspace subscription
- [ ] Add domains to workspace
- [ ] Create user accounts (3 per domain)
- [ ] Configure 2FA/security settings
- [ ] Document credentials securely

#### Microsoft Entra/Azure Accounts (6 accounts)
- [ ] Create Microsoft 365 subscription
- [ ] Add domains to tenant
- [ ] Create user accounts
- [ ] Configure security settings
- [ ] Document credentials securely

### 3.4 Warming Integration Setup
- [ ] Connect all accounts to Bison workspace
- [ ] Enable warming protocols
- [ ] Set initial sending volumes (low)
- [ ] Configure gradual ramp-up schedule

### 3.5 Deliverables Checklist
- [ ] 5 Google Workspace accounts active
- [ ] 6 Azure/Microsoft accounts active
- [ ] All DNS records propagated and verified
- [ ] All accounts connected to warming system
- [ ] Credentials documented and stored securely

**Output:** 11 active email accounts, DNS configured, warming initiated

---

## Step 4: 📖 Follow Hypertide Setup Documentation

**Duration:** Included in Step 3
**Reference:** [Hypertide Latest and Greatest Recommendation](https://docs.google.com/document/d/1jitFpnsXzJlPyKM-mHQpWLMPxFEHEE5WgHQ_YTq9dRk/edit?tab=t.0) (Google Doc)

### Key Configuration Points
- [ ] Follow latest Hypertide best practices
- [ ] Apply recommended sending configurations
- [ ] Use suggested DNS settings
- [ ] Implement security recommendations

---

## Step 5: ✅ Account Manager Verification & Handoff

**Duration:** 20 minutes
**Owner:** Infrastructure Team + Account Manager

### 5.1 Pre-Verification Checklist
- [ ] All email accounts accessible and functional
- [ ] DNS records fully propagated (use MXToolbox to verify)
- [ ] Warming progress on track (check Bison dashboard)
- [ ] No deliverability issues flagged
- [ ] Credentials organized and ready for transfer

### 5.2 Account Manager Review
- [ ] Schedule brief handoff meeting with AM
- [ ] Walk through infrastructure setup
- [ ] Demonstrate Bison workspace access
- [ ] Review warming status and timeline
- [ ] Answer any AM questions

### 5.3 Documentation Handoff
Provide AM with:
- [ ] Workspace access credentials
- [ ] List of all email accounts with login details
- [ ] DNS configuration summary
- [ ] Warming schedule and current status
- [ ] Troubleshooting contacts

### 5.4 Sign-Off
- [ ] AM confirms access to all systems
- [ ] AM confirms understanding of warming timeline
- [ ] Document handoff completion in ClickUp task
- [ ] Update task status to complete

**Output:** Signed-off infrastructure ready for campaign use

---

## 🕐 Warming Period (14-21 Days)

### Warming Timeline
| Days | Daily Volume | Activity |
|------|--------------|----------|
| 1-3 | 5-10 emails/account | Initial warm-up, internal sends |
| 4-7 | 15-25 emails/account | Gradual increase, engagement focus |
| 8-14 | 30-50 emails/account | Building reputation |
| 15-21 | 50-75 emails/account | Near full capacity |
| 21+ | 75-100 emails/account | Ready for campaigns |

### Monitoring During Warming
- [ ] Check bounce rates daily (target: <2%)
- [ ] Monitor spam complaints (target: <0.1%)
- [ ] Track open rates (healthy: >20%)
- [ ] Review sender reputation scores weekly

---

## 📅 Post-Handoff Responsibilities

### Infrastructure Team
- Weekly monitoring of account health
- Respond to deliverability issues
- Manage domain renewals

### Account Manager
- Campaign creation and management
- Lead list quality control
- Performance reporting
- Escalate deliverability issues

---

## 🚨 Troubleshooting Quick Reference

| Issue | Likely Cause | Solution |
|-------|--------------|----------|
| High bounce rate | Bad list data | Clean list, verify emails |
| Low open rates | Poor subject lines or spam folder | A/B test subjects, check reputation |
| Account suspended | Volume spike or complaints | Reduce volume, warm again |
| DNS issues | Propagation delay | Wait 24-48 hrs, verify settings |

---

## 📞 Escalation Contacts

| Role | Contact | For Issues |
|------|---------|------------|
| Infrastructure Lead | [TBD] | Account setup, DNS issues |
| Bison Support | support@emailbison.com | Platform issues |
| Hypertide Support | [TBD] | Provisioning issues |

---

## 📝 Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | December 2024 | Initial SOP compilation from ClickUp | Claude |
| 2.0 | December 2024 | Added automated domain sourcing workflow, replaced manual Step 2 | Claude |

---

## Related Components

### Hypertide Automation Tool
**Location:** `D:\BrainOn\Hypertide\automation\`
**Description:** Python/Playwright automation for Hypertide web UI

Includes:
- **Purchase Automation** (`hypertide-purchase`): Browser automation for Hypertide purchases
- **Domain Sourcing** (`domain-source`): AI-powered domain discovery and purchase automation

Installation:
```bash
cd D:\BrainOn\Hypertide\automation
pip install -e ".[ai]"  # Include AI generation support
playwright install chromium
```

### Domain Sourcing Module
**Location:** `D:\BrainOn\Hypertide\automation\src\hypertide_automation\domain_sourcing\`
**Description:** Event-driven domain sourcing with AI generation and multi-registrar search

Key components:
- `models.py` - Data models for requests, candidates, and results
- `registrars.py` - Porkbun/DynaDot API integrations
- `generator.py` - AI-powered domain name generation
- `search.py` - Fuzzy search and variation engine
- `workflow.py` - Orchestration and approval workflow
- `cli.py` - Command-line interface

### EmailBison MCP
**Description:** API integration for workspace and campaign management

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    Client Onboarding Form                       │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Domain Sourcing CLI                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │
│  │ AI Domain   │  │ Registrar   │  │   Search    │              │
│  │ Generator   │──│   APIs      │──│   Engine    │              │
│  │ (GPT-4)     │  │(Porkbun/    │  │ (Fuzzy +    │              │
│  │             │  │ Dynadot)    │  │  Ranking)   │              │
│  └─────────────┘  └─────────────┘  └─────────────┘              │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │  Human Approval     │
                    │    Checkpoint       │
                    └──────────┬──────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│              Automatic Domain Purchase                           │
│  - Purchase from best-price registrar                           │
│  - Configure Hypertide-compatible nameservers                   │
│  - Enable WHOIS privacy                                         │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│              Hypertide BYOD Purchase                             │
│  - Use pre-purchased domains (BYOD mode)                        │
│  - Provision Entra/Google accounts                              │
│  - Configure DNS (SPF, DKIM, DMARC)                             │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│              EmailBison Integration                              │
│  - Connect inboxes to workspace                                 │
│  - Enable warming protocols                                     │
│  - Configure gradual ramp-up                                    │
└─────────────────────────────────────────────────────────────────┘
```
