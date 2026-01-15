---
name: hypertide-recommend-settings
description: Recommend optimal Hypertide settings based on platform and use case
triggers:
  - "what settings"
  - "how should I configure"
  - "best practices"
  - "recommended settings"
  - "hypertide setup"
  - "bison settings"
context_files:
  - ../knowledge/warmup-config.yaml
  - ../knowledge/outbound-settings.yaml
  - ../knowledge/domain-strategy.yaml
last_validated: "2025-12-10"
---

# Hypertide Settings Recommendation Skill

**Primary Email Sequencer: EmailBison (Bison)**

## Quick Recommendation - Bison Settings

### 🎯 Primary Configuration: Bison Warmup Settings

| Inbox Type | Emails/Day | Reply to Inbound | Warmup Days |
|------------|------------|------------------|-------------|
| **Entra** | 5 | **3** | 14 |
| **Google** | 10 | **6** | 14 |

> **Key Difference**: Bison uses "Reply to Inbound" count, NOT reply rate percentage

### Outbound Settings (Post-Warmup)

| Inbox Type | Emails/Day | Wait Time | Max Safe Volume |
|------------|------------|-----------|-----------------|
| **Entra** | 2 (start) | 60 min | 3-4 (with monitoring) |
| **Google** | 20 | 35 min | Higher tolerance |

---

## Scenario-Based Recommendations

### Scenario 1: New Hypertide Order - Bison (PRIMARY)

**Warmup Phase (14 days):**
```yaml
# For Entra inboxes
emails_per_day: 5
warmup_days: 14
reply_to_inbound: 3  # KEY BISON SETTING
```

```yaml
# For Google inboxes
emails_per_day: 10
warmup_days: 14
reply_to_inbound: 6  # Higher for Google
```

**Post-Warmup Outbound:**
```yaml
# For Entra
emails_per_inbox_per_day: 2
wait_between_emails: 60 minutes

# For Google
emails_per_inbox_per_day: 20
wait_between_emails: 35 minutes
```

---

### Scenario 2: Scaling Up (Good Performance)

If your campaign is performing well after baseline period:

| Current | Can Scale To | Risk Level |
|---------|--------------|------------|
| 2/day | 3/day | Moderate - monitor |
| 3/day | 4/day | Elevated - close monitoring |
| 4/day | STOP | High risk - add orders instead |

**Recommendation:** Scale horizontally (more orders) not vertically (more per inbox)

---

### Scenario 3: Domain Selection

**Recommended:**
- TLD: `.com` (primary) or `.co` (secondary)
- Age: Domains older than 1 month
- Source: Hypertide-provided ($15.50) or BYOD

**Avoid:**
- Newly registered domains (<2-4 weeks old)
- Obscure TLDs
- Domains with poor history

---

## Campaign Settings Checklist

For ANY Hypertide campaign, ensure:

### Must Be DISABLED:
- [ ] Open tracking
- [ ] Link tracking
- [ ] MX/ESP matching
- [ ] Lead list splitting by ESP

### Must Be ENABLED:
- [ ] Both Hypertide domains in campaign

### Content Rules:
- [ ] Plain text only
- [ ] No images
- [ ] No links
- [ ] Spintax for variation
- [ ] Rotate copy every 1.5-2 months

### Lead List Rules:
- [ ] Safe/Valid emails only
- [ ] No catchalls
- [ ] No invalids

---

## Recommendation Decision Flow

```
Setting up Hypertide?
│
└── Using Bison (default)
    │
    ├── Entra inbox?
    │   └── Reply to Inbound: 3, Emails/day: 5
    │
    └── Google inbox?
        └── Reply to Inbound: 6, Emails/day: 10
```

---

## Red Flags to Avoid

| Setting | Wrong Approach | Correct Approach |
|---------|----------------|------------------|
| Bison warmup | Using reply rate % | **Reply to Inbound: 3 (Entra), 6 (Google)** |
| Warmup duration | <14 days | **14 days minimum** |
| Tracking | Enabled | **Disabled (all types)** |
| Emails/day (Entra) | >4 | **2-4 max** |
| Domain usage | Single domain | **Both Hypertide domains** |

---

## Reference: Other Platforms (Not Actively Used)

<details>
<summary>Smartlead Settings (Reference Only)</summary>

| Platform | Inbox | Emails/Day | Reply Rate | Ramp | Days | Inbound |
|----------|-------|------------|------------|------|------|---------|
| Smartlead | Entra | 5 | **60%** | 1 | 14 | 8 |
| Smartlead | Google | 10 | 30% | 1 | 14 | - |

**Bulk tool:** https://smartlead.hypertide.io
</details>

<details>
<summary>Instantly Settings (Reference Only)</summary>

| Platform | Inbox | Emails/Day | Reply Rate | Ramp | Days |
|----------|-------|------------|------------|------|------|
| Instantly | Entra | 5 | **100%** | 1 | 14 |
| Instantly | Google | 10 | 30% | 1 | 14 |

**Bulk tool:** https://instantly.hypertide.io
</details>
