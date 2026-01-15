# Hypertide Operations - Agent Integration

## Important: No API Access

Hypertide does **NOT** have API connections. It is a **web-only interface** for:
- Managing purchases and subscriptions
- Account management
- Inbox configuration

**Primary Email Sequencer: EmailBison (Bison)**

> Note: Smartlead/Instantly bulk tools exist for reference but are not actively used:
> - https://smartlead.hypertide.io (Reference only)
> - https://instantly.hypertide.io (Reference only)

There is no programmatic API for inbox management, campaign control, or metrics retrieval.

---

## Core Paradigm
> **Domain reputation ALWAYS supersedes individual inbox reputation**

- 15% warmup failures = ACCEPTABLE
- 80/20 receive/send ratio = BY DESIGN
- Scale horizontally (add orders) not vertically

## Context Cache Structure
```
context-cache/
├── hypertide-manifest.yaml
├── knowledge/
│   ├── warmup-config.yaml
│   ├── campaign-rules.yaml
│   ├── outbound-settings.yaml
│   ├── thresholds.yaml
│   └── domain-strategy.yaml
├── decision-trees/
│   └── troubleshooting.yaml
└── skills/
    ├── configure-order.md
    ├── diagnose-issue.md
    ├── audit-campaign.md
    └── recommend-settings.md
```

## Critical Quick Reference

### 🎯 Bison Warmup Settings (PRIMARY)

| Inbox Type | Emails/Day | Reply to Inbound | Warmup Days |
|------------|------------|------------------|-------------|
| **Entra** | 5 | **3** | 14 |
| **Google** | 10 | **6** | 14 |

> **Key**: Bison uses "Reply to Inbound" count, NOT reply rate percentage

### Reference Only: Other Platforms
| Platform | Entra Reply Rate |
|----------|-----------------|
| Smartlead | 60% (not used) |
| Instantly | 100% (not used) |
| Bison | N/A (uses inbound: 3) |

### Thresholds
| Metric | OK | Problem |
|--------|-----|---------
| Bounce rate | <5% | >=5% |
| Warmup failures | <15% | >15% |
| Not sending warmup | <80% | >=80% |

### Non-Negotiable Rules
1. NO open/link tracking
2. NO MX/ESP matching
3. NO lead list splitting
4. Safe/Valid emails ONLY
5. NO images or links
6. Use BOTH domains
7. 14-day warmup minimum

## Support: support@hypertide.io
