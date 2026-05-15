---
title: ESP-Aware Data Interpretation
created: 2026-05-15
updated: 2026-05-15
tags: [concept, esp, google, microsoft, entra, data-interpretation, handoff]
related-docs:
  - kill-triggers.md (kill-rule + domain-burn thresholds)
  - domain-lifecycle.md (burn semantics)
  - ../plans/INBOX-INTEGRITY-PROGRAM.md (master tracker)
---

# ESP-Aware Data Interpretation

> **READ THIS BEFORE ANALYZING ANY RATE-OR-RATIO METRIC FROM `sender_accounts`,
> `domains`, OR `event_log`.** Google and Microsoft are structurally
> different. Treating them uniformly produces wrong conclusions —
> wrong-enough to miss real problems and wrong-enough to invent
> imaginary ones.

## The single most important fact

| ESP | Inboxes per domain (typical) | 1 inbox-level event = how much domain-level signal? |
|---|---:|---|
| **Google (gmail)** | **3** | 33% of the domain — a strong signal |
| **Microsoft (entra)** | **52** | 1.9% of the domain — statistical noise |

This shapes every rate-based decision in the system. Operating on the
same threshold for both ESPs gives you either: noise-burning the MSFT
fleet, or under-protecting Google domains.

## Strategic context (as of 2026-05-15)

- **Microsoft / Entra is being deprecated** — "ride-to-death" mode.
  No new MSFT domains; existing fleet winds down through attrition.
- **Google is the future.** All new provisioning, all new tag rules,
  all new investment is Google-first.
- **Don't build elaborate MSFT-specific logic.** Effort spent on
  MSFT-only rules is decay. Fix bugs that affect existing MSFT fleet
  during ride-to-death; don't invent new MSFT-specific behavior.

## ESP value conventions — known footgun

The same logical concept ("this is a Microsoft inbox") has two different
string values in the DB depending on which table you're reading from:

| Table | Column | MSFT value | Google value |
|---|---|---|---|
| `sender_accounts` | `esp` | `'microsoft'` | `'gmail'` |
| `domains` | `infrastructure_type` | `'entra'` | `'google'` |

The `set_tag_sync.py` mapping at line 685 / 700 translates between them:
`CASE WHEN sa.esp = 'microsoft' THEN 'entra' ELSE 'google' END`.

When you grep code for `'entra'` or `'microsoft'` looking for a bug,
**always check which column the surrounding code is reading from.**
Both spellings are correct in their respective contexts. A mismatch
between the dict-key spelling and the column-read spelling is exactly
the bug class that almost wasted an hour during the 2026-05-15
domain-burn investigation.

## Schema fields with ESP-skewed meaning

These columns are valid for any ESP but mean different things at scale:

| Field | What it counts | Why ESP matters |
|---|---|---|
| `domains.domain_complaints_7d` | total **complaint events** on the domain in 7d | Google: 1 event = strong; MSFT: needs 3+ to be signal |
| `domains.domain_complaint_rate_7d` | `events / inboxes` | Google denominator ~3, MSFT ~52 — same numerator, very different rate |
| `domains.inboxes_with_complaints` | distinct **inbox count**, not event count | 1 inbox with 10 complaints still counts as 1 here. Always cross-check against `burn_breakdown` for the event count. |
| `domains.burn_breakdown` | JSON `{trigger_type → event_count}` at burn time | Authoritative event count at the moment of burn (the 7d columns roll forward and age out). |
| `domains.domain_bounce_rate_7d` | `bounces / inboxes` | Same denominator skew as complaint rate |
| `sender_accounts.emails_sent_all_time` | per-inbox lifetime sends | Drives the kill-rule rate denominator. Equal across ESPs in spirit, but MSFT inboxes typically have more total sends because they live longer. |

## Specific misinterpretations to avoid

These are real mistakes that have happened during analysis sessions.
Don't repeat them.

### 1. `inboxes_with_complaints = 1` is **not** "domain burned on 1 complaint"

`inboxes_with_complaints` is a count of *distinct inboxes that had
≥1 complaint*. A domain showing `inboxes_with_complaints = 1` could
have had **10 complaint events** all from a single inbox spamming
hard. Always cross-check `burn_breakdown.spam_complaint` for the
event count at burn time, since the 7d columns roll forward.

Real example (2026-05-15): `growwithkernel.com` showed
`inboxes_with_complaints = 1`. Looked like "noise burn." Actually
had 10 spam-complaint events — a real burn signal.

### 2. "We're burning MSFT domains too quickly" — check `burn_breakdown`, not 7d columns

When investigating whether the burn rate is too aggressive, the
`*_7d` columns are **historical leftovers** that age out. For a
domain burned 30+ days ago, `domain_complaints_7d` is almost always
0 because the 7d window has passed. The authoritative record is
`burn_breakdown` — a JSON snapshot at burn time.

Real example (2026-05-15): All 29 burned MSFT domains showed
`domain_complaints_7d = 0`. Looked like "burned on 0 complaints."
Actually had 8–130 complaint events each at burn time, per
`burn_breakdown`. Legitimate burns.

### 3. Don't aggregate ESP-mixed counts into a single rate

A workspace with 100 inboxes on Google domains and 1,000 on MSFT
domains will be dominated by MSFT in any aggregate metric. If you
want to assess fleet health, **split by ESP first**, then interpret.
Combined rates obscure both signals.

Example query to keep handy:
```sql
SELECT sa.esp, COUNT(*) AS n, ...
FROM sender_accounts sa
WHERE ...
GROUP BY sa.esp
```

### 4. Burn rules are ESP-specific by design — not a bug

The domain-burn decision in [sync_modules/kill_processor.py][kp] uses
different thresholds per ESP:

```python
ESP_BURN_MIN_COMPLAINTS = {
    'google': 1,   # 1 complaint = 33% domain rate = burn
    'entra':  3,   # Require pattern of 3+ before burning a 52-inbox domain
}
```

If you see "MSFT domain burned on N complaints," check `N ≥ 3` AND
domain complaint rate ≥ 1%. If `N < 3` or rate < 1%, it shouldn't
have burned under the intended MSFT rule — that's a real bug.
**But** the threshold maps via `domains.infrastructure_type` (which
is `'entra'`), not `sender_accounts.esp` (which is `'microsoft'`).

[kp]: ../../sync_modules/kill_processor.py

## Operational drift expectations

Because MSFT is winding down, expect:

- **Burned-domain inbox count is overwhelmingly MSFT.** As of
  2026-05-15: 1,337 MSFT vs 6 Google inboxes are attached to
  campaigns but on burned domains. Don't read this as "MSFT-burns
  are accelerating" — it's the inverse: MSFT domains burned during
  active use, and the residue persists in EB campaign attachments
  while the fleet sunsets.
- **EOD reapply's 50% safety guard will fire on MSFT-heavy campaigns**
  whose attached senders are mostly on now-burned domains. This is
  the daemon working correctly, refusing to mass-detach. The fix
  is operational (retire those campaigns OR a one-shot bulk-detach),
  not a code change.
- **Google should rarely hit the 50% guard.** If it does, that's a
  real signal worth investigating — Google domains are small enough
  that burning many inboxes from a campaign means something is
  genuinely wrong upstream.

## Quick reference: ESP-split queries

When in doubt, split. Standard patterns:

**Inbox counts by ESP:**
```sql
SELECT esp, COUNT(*) FROM sender_accounts WHERE is_active GROUP BY 1;
-- microsoft: 4058 | gmail: 915 | other: 52  (typical 2026-05)
```

**Burned domains by ESP:**
```sql
SELECT
  (SELECT esp FROM sender_accounts WHERE domain_id=d.id LIMIT 1) AS esp,
  COUNT(*)
FROM domains d
WHERE pool_status='burned'
GROUP BY 1;
```

**Operational drift (campaign-attached + burned-domain) by ESP:**
```sql
SELECT sa.esp, COUNT(*)
FROM sender_accounts sa
JOIN domains d ON d.id = sa.domain_id AND d.pool_status = 'burned'
WHERE sa.is_active
GROUP BY 1;
```

## Handoff checklist

When picking up this codebase or this domain knowledge:

- [ ] Read this doc end-to-end before running any rate-based query
- [ ] Default to ESP-split queries; combined-rate queries should be
      a deliberate choice, not the default
- [ ] When reading domain-burn data, prefer `burn_breakdown` (snapshot)
      over `*_7d` (rolling, ages out)
- [ ] When investigating MSFT-specific issues, calibrate effort to the
      deprecation timeline — don't build elaborate MSFT-only rules
- [ ] Google is the canonical / future ESP — new logic should default
      to Google semantics (3-inbox-per-domain math, 1-complaint-burn)
