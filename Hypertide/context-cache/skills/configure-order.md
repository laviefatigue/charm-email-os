---
name: hypertide-configure-order
description: Configure a new Hypertide order with correct warmup and campaign settings
triggers:
  - "new hypertide order"
  - "setup hypertide"
  - "configure hypertide inboxes"
  - "hypertide warmup settings"
  - "bison warmup"
context_files:
  - ../knowledge/warmup-config.yaml
  - ../knowledge/campaign-rules.yaml
  - ../knowledge/outbound-settings.yaml
last_validated: "2025-12-10"
---

# Hypertide Order Configuration Skill

**Primary Email Sequencer: EmailBison (Bison)**

When configuring a new Hypertide order, follow this checklist:

## Step 1: Confirm Platform and Inbox Type

1. **Platform**: Bison (EmailBison) - Our primary email sequencer
2. **Inbox Types**: Confirm whether Entra (Microsoft) or Google

> Note: Smartlead/Instantly settings are available for reference but Bison is our standard platform.

## Step 2: Apply Bison Warmup Settings

### 🎯 For Bison + Entra (PRIMARY CONFIGURATION):
- Emails per day: **5**
- Warmup duration: **14 days**
- Reply to inbound: **3** ← Key Bison setting
- No reply rate percentage (Bison uses inbound count)

### For Bison + Google:
- Emails per day: **10**
- Warmup duration: **14 days**
- Reply to inbound: **6** ← Higher for Google

---

## Reference Only: Other Platforms

<details>
<summary>Smartlead Settings (Not actively used)</summary>

### For Smartlead + Entra:
- Emails per day: **5**
- Reply rate: **60%** (NOT 100!)
- Ramp up: **1 per day**
- Warmup duration: **14 days**
- Reply to inbound warmup: **8**
- Auto-adjust: **OFF** (never enable)

### For Smartlead + Google:
- Emails per day: **10**
- Reply rate: **30%**

**Bulk tool:** https://smartlead.hypertide.io
</details>

<details>
<summary>Instantly Settings (Not actively used)</summary>

### For Instantly + Entra:
- Emails per day: **5**
- Reply rate: **100%** (different from Smartlead!)
- Ramp up: **1 per day**
- Warmup duration: **14 days**
- Auto-adjust: **OFF**

### For Instantly + Google:
- Emails per day: **10**
- Reply rate: **30%**

**Bulk tool:** https://instantly.hypertide.io
</details>

---

## Step 3: Pre-Launch Checklist (After 14 Days)

Before launching campaigns, verify:

- [ ] Open tracking: **DISABLED**
- [ ] Link tracking: **DISABLED**
- [ ] MX/ESP matching: **DISABLED**
- [ ] Lead list splitting by ESP: **DISABLED**
- [ ] Lead list: **Safe/Valid emails ONLY**
- [ ] Email content: **No images, no links**
- [ ] Domains: **Both Hypertide domains in campaign**

## Step 4: Outbound Settings (Post-Warmup)

For Entra inboxes:
- Start at **2 emails/day/inbox**
- Wait time: **60 minutes** between emails
- Scale to 3-4 only if performing well

For Google inboxes:
- Start at **20 emails/day/inbox**
- Wait time: **35 minutes** between emails

## Common Mistakes to Prevent

1. ❌ Using reply rate % for Bison → Use "Reply to Inbound" count instead
2. ❌ Using 3 for Google → Use 6 for Google (3 is for Entra)
3. ❌ Launching before 14 days → Always wait full warmup
4. ❌ Using only one domain per campaign → Use both domains
5. ❌ Enabling any tracking → All tracking must be disabled

## Quick Reference Card

| Setting | Bison Entra | Bison Google |
|---------|-------------|--------------|
| Emails/Day | 5 | 10 |
| Reply to Inbound | **3** | **6** |
| Warmup Days | 14 | 14 |
