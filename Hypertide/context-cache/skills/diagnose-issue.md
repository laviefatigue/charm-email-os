---
name: hypertide-diagnose-issue
description: Diagnose Hypertide infrastructure issues using decision trees
triggers:
  - "hypertide problem"
  - "bounce rate"
  - "warmup not working"
  - "inboxes disconnected"
  - "hypertide issue"
  - "warmup code"
  - "bison issue"
context_files:
  - ../decision-trees/troubleshooting.yaml
  - ../knowledge/thresholds.yaml
last_validated: "2025-12-10"
---

# Hypertide Issue Diagnosis Skill

**Primary Email Sequencer: EmailBison (Bison)**

## Quick Diagnostic Reference

| Symptom | Key Question | Threshold | Action |
|---------|--------------|-----------|--------|
| Bounce >5% | All from one domain? | - | Yes=Support, No=Change copy |
| Warmup code requests | % of inboxes affected? | 15% | Below=Normal, Above=Support |
| Not sending warmup | % of inboxes affected? | 80% | Below=Normal, Above=Support |
| Test emails missing | - | - | Use actual campaign to test |
| Disconnections | Bulk reconnect works? | - | Yes=Self-fix, No=Support |

---

## Decision Tree: High Bounce Rate (>5%)

```
Bounce rate > 5%?
│
├── Did you launch before 14-day warmup?
│   └── YES → This is the cause. Wait full warmup next time.
│
└── NO → Check bounce distribution:
    │
    ├── ALL bounces from ONE domain?
    │   └── YES → TENANT LOCKDOWN
    │       • Alert support@hypertide.io IMMEDIATELY
    │       • Support migrates to new tenant in 24h
    │       • This WILL fix the issue
    │
    └── NO (distributed across domains)
        └── COPY FLAGGED BY ESPs
            • Change campaign copy immediately
            • Increase warmup variability
            • Recovery: 1-6 months
            • Tenant change WON'T help
```

---

## Decision Tree: Warmup Code Requests

```
Inboxes requesting code for warmup re-enable?
│
├── < 15% of inboxes affected?
│   └── NORMAL - BY DESIGN
│       • Enterprise Entra throttles warmup (not campaigns)
│       • "Bounces" are not true bounces
│       • Domain reputation > Individual inbox
│       • Inboxes WILL send campaign emails fine
│       • NO action required
│
└── >= 15% of inboxes affected?
    └── PROBLEM → Contact support@hypertide.io
```

---

## Decision Tree: Warmup Not Sending

```
Inboxes not SENDING warmup emails?
│
├── < 80% of inboxes affected?
│   └── NORMAL - BY DESIGN
│       • Enterprise pattern: 80/20 receive/send ratio
│       • Intentional behavior mimicking enterprise
│       • Domain health > Individual inbox health
│       • Will still achieve strong deliverability
│       • NO action required
│
└── >= 80% of inboxes affected?
    └── PROBLEM → Contact support@hypertide.io
```

---

## Decision Tree: Disconnections

```
Inboxes getting disconnected?
│
├── Bulk reconnect works (no password)?
│   └── EASY FIX
│       • Use Bison reconnection feature
│       • Self-service resolution
│
└── Full reconnect required (needs password)?
    └── CONTACT SUPPORT
        • Email support@hypertide.io
        • Include list of affected inboxes
        • 24-hour turnaround
```

---

## Decision Tree: Test Emails Missing

```
Test emails not arriving?
│
└── EXPECTED BEHAVIOR
    • Test emails use different protocol
    • Doesn't work reliably with Entra
    │
    └── SOLUTION:
        1. Create actual campaign
        2. Add test addresses as leads
        3. Send via campaign
        4. This uses correct protocol
```

---

## Key Paradigm Reminder

> **Domain reputation ALWAYS supersedes individual inbox reputation**

This means:
- 15% warmup failures = Acceptable
- Some inboxes not sending warmup = Normal
- Focus on domain-level health, not individual inboxes

---

## When to Contact Support

Email: support@hypertide.io

Contact support when:
- [ ] >15% of inboxes failing warmup
- [ ] >=80% of inboxes not sending warmup
- [ ] All bounces from single domain (tenant issue)
- [ ] Full reconnect needed (password required)
- [ ] Forwarding URL change needed
- [ ] Inbox name changes needed
- [ ] Domain swap needed
