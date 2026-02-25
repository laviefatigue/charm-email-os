---
name: hypertide-audit-campaign
description: Audit Hypertide campaign settings against best practices
triggers:
  - "check my campaign"
  - "audit hypertide"
  - "review settings"
  - "campaign compliance"
  - "hypertide best practices"
  - "bison audit"
context_files:
  - ../knowledge/campaign-rules.yaml
  - ../knowledge/thresholds.yaml
  - ../knowledge/outbound-settings.yaml
last_validated: "2025-12-10"
---

# Hypertide Campaign Audit Skill

**Primary Email Sequencer: EmailBison (Bison)**

## Campaign Compliance Checklist

Use this checklist to audit any Hypertide campaign:

### Critical Rules (Violations = Major Risk)

| # | Check | Expected | Status |
|---|-------|----------|--------|
| 1 | Open tracking | **DISABLED** | ⬜ |
| 2 | Link tracking | **DISABLED** | ⬜ |
| 3 | MX/ESP matching | **DISABLED** | ⬜ |
| 4 | Lead list split by ESP | **NOT SPLIT** | ⬜ |
| 5 | Email validation | **Safe/Valid only** | ⬜ |
| 6 | Images in copy | **NONE** | ⬜ |
| 7 | Links in copy | **NONE** | ⬜ |
| 8 | Domains used | **BOTH domains** | ⬜ |

### 🎯 Bison Warmup Settings Audit (PRIMARY)

#### Bison + Entra
| Setting | Expected | Actual | Status |
|---------|----------|--------|--------|
| Emails/day | 5 | | ⬜ |
| Reply to Inbound | **3** | | ⬜ |
| Warmup days | 14 | | ⬜ |

#### Bison + Google
| Setting | Expected | Actual | Status |
|---------|----------|--------|--------|
| Emails/day | 10 | | ⬜ |
| Reply to Inbound | **6** | | ⬜ |
| Warmup days | 14 | | ⬜ |

---

### Reference Only: Other Platforms

<details>
<summary>Smartlead + Entra (Not actively used)</summary>

| Setting | Expected | Actual | Status |
|---------|----------|--------|--------|
| Emails/day | 5 | | ⬜ |
| Reply rate | 60% | | ⬜ |
| Ramp up | 1/day | | ⬜ |
| Warmup days | 14 | | ⬜ |
| Inbound replies | 8 | | ⬜ |
| Auto-adjust | OFF | | ⬜ |
| Domain-Level Rate Limiting | ENABLED | | ⬜ |
</details>

<details>
<summary>Instantly + Entra (Not actively used)</summary>

| Setting | Expected | Actual | Status |
|---------|----------|--------|--------|
| Emails/day | 5 | | ⬜ |
| Reply rate | 100% | | ⬜ |
| Ramp up | 1/day | | ⬜ |
| Warmup days | 14 | | ⬜ |
| Auto-adjust | OFF | | ⬜ |
</details>

---

### Outbound Settings Audit (Post-Warmup)

| Setting | Entra Expected | Google Expected | Status |
|---------|---------------|-----------------|--------|
| Emails/inbox/day | 2 (max 4) | 20 | ⬜ |
| Wait between emails | 60 min | 35 min | ⬜ |

### Health Metrics

| Metric | Healthy | Warning | Critical | Current |
|--------|---------|---------|----------|---------|
| Bounce rate | <2% | 2-5% | >5% | |
| Warmup compliance | >90% | 85-90% | <85% | |
| Copy age | <1 mo | 1-2 mo | >2 mo | |

---

## Common Violations Found

### 1. Wrong Bison Settings
**Symptom:** Poor warmup performance
**Check:**
- Bison Entra should use Reply to Inbound: **3** (not reply rate %)
- Bison Google should use Reply to Inbound: **6**

### 2. Tracking Enabled
**Symptom:** Deliverability issues, spam placement
**Check:** Both open AND link tracking must be disabled

### 3. Single Domain in Campaign
**Symptom:** Faster domain flagging
**Check:** Verify BOTH Hypertide domains are in campaign

### 4. Lead List Issues
**Symptom:** High bounce rate
**Check:**
- No catchall emails
- No invalid emails
- Not split by ESP

### 5. Copy Staleness
**Symptom:** Gradual deliverability decline
**Check:** Copy should rotate every 1.5-2 months

---

## Audit Report Template

```
HYPERTIDE CAMPAIGN AUDIT REPORT
================================
Date: [DATE]
Campaign: [NAME]
Platform: Bison (EmailBison)
Inbox Type: [Entra/Google]

COMPLIANCE STATUS: [PASS/FAIL/WARNINGS]

BISON SETTINGS CHECK:
- Reply to Inbound: [X] (Expected: 3 for Entra, 6 for Google)
- Emails/Day: [X] (Expected: 5 for Entra, 10 for Google)
- Warmup Days: [X] (Expected: 14)

CRITICAL ISSUES:
- [ ] Issue 1
- [ ] Issue 2

WARNINGS:
- [ ] Warning 1

RECOMMENDATIONS:
1. [Action item]
2. [Action item]

METRICS:
- Bounce Rate: X%
- Warmup Compliance: X%
- Copy Age: X months
```

---

## Scoring Guide

| Score | Status | Description |
|-------|--------|-------------|
| 100% | ✅ EXCELLENT | All checks pass, optimal configuration |
| 90-99% | ✅ GOOD | Minor optimizations possible |
| 80-89% | ⚠️ WARNING | Some issues need attention |
| <80% | ❌ CRITICAL | Major violations, fix immediately |

**Automatic FAIL triggers:**
- Any tracking enabled
- Bounce rate >5%
- Missing domain in campaign
- Catchalls/invalids in lead list
- Wrong Reply to Inbound value for Bison
