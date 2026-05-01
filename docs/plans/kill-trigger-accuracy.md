---
title: Kill-Trigger Accuracy — Bounce Classification Improvement
created: 2026-05-01
updated: 2026-05-01 (Pass 1+2+4 shipped; Pass 3 + Pass 6 pending)
status: ACTIVE — 3 of 5 phases shipped
related-plans:
  - INBOX-INTEGRITY-PROGRAM.md (master tracker)
  - connection-state-machine.md (Plan B — sibling kill-state work)
related-adrs:
  - adr-009 (connection separated from kill state)
related-docs:
  - docs/concepts/kill-triggers.md (our spec — Pass 1 rewrites the SMTP table)
  - docs/work-logs/2026-04-30-deploy-outcome.md (today's deploy that surfaced this)
---

# Kill-Trigger Accuracy — Plan

## 1. Why this exists

A 2026-05-01 forensic on a fresh SKMR `spam_complaint` kill (`m.elzey@scalestablekernel.com`, killed at 11 sends, 2 bounces) traced the cause to a bounce-body text heuristic that fired on a Microsoft 365 mail-flow-rule NDR ("user no longer employed at SGMC, message refused"). Not a user-initiated spam complaint — a recipient admin policy block. Looking fleet-wide:

- **383 historical `spam_complaint` kills**
- **0** had `folder='spam'` evidence (the strongest signal)
- **361** had `hard_blocked` bounces (the heuristic path)
- **5/5 sampled** were the same false-positive pattern: recipient admin policy / connector restriction / IP-rep block being incorrectly classified as user-initiated spam complaint

The behavior is structurally wrong, not just edge-case wrong. **No SMTP error code from either Microsoft 365 or Google Workspace means "user reported as spam."** Real complaint signals route out-of-band:

- **Microsoft JMRP** — separate ARF-formatted emails to a registered FBL address (free, requires SNDS enrollment)
- **Gmail Postmaster Tools** — dashboard reports complaint rate (requires `Feedback-ID:` header on outbound)

Yahoo CFL exists but is irrelevant to Charm's B2B scope (Microsoft 365 + Google Workspace targets only).

## 2. Industry validation

Cold-email GTM platforms (Smartlead, Instantly, Lemlist, Mailshake, Outreach, Salesloft) do exactly what we do for steps 1–6:

| Step | Industry | Charm | Verdict |
|------|----------|-------|---------|
| Pull bounces from ESP API per folder | ✓ | ✓ via EB `/replies` | Standard |
| Regex SMTP code from body | ✓ | ✓ in `extract_bounce_reason` | Standard |
| Bucket into `hard_unknown` / `hard_blocked` / `soft_full` / `soft_temp` | ✓ | ✓ in `classify_bounce` | Standard |
| 24h / 7d rolling counters per inbox | ✓ | ✓ in `sender_accounts.hard_*_24h/7d` | Standard |
| Daily counter reset to prevent accumulation creep | ✓ | ✓ at midnight | Standard |
| Count-based kill thresholds (per-bucket) | ✓ | ✓ `hard_blocked_24h ≥ 2`, `hard_unknown_24h ≥ 3`, `hard_bounces_24h ≥ 2` | Standard, conservative |
| Rate-based kill thresholds (with min-volume floor) | 2% hard / 5% total / 100+ sends | `KILL_THRESHOLD_HARD_BOUNCE_RATE = 0.02`, `KILL_THRESHOLD_TOTAL_BOUNCE_RATE = 0.05`, `KILL_THRESHOLD_MIN_SENDS = 100` | **Already in place — matches industry exactly** |
| Detect spam complaints | Postmaster Tools / JMRP (out-of-band ARF) | **Heuristic on bounce body text** | ✗ The structural error |
| Watch sender-ban codes | Direct kill on Microsoft 5.7.501/.502/.503/.511/.705/.708 | Not watching | Gap, but rare |

The diagnosis: **the classifier and the counters are correct.** The error is bolted on top — a single inference path that maps "bounce body text contains spam-ish keywords" → `complaints_lifetime += 1` → instant kill via `KILL_THRESHOLD_SPAM = 1`.

## 3. What's working — leave it alone

- `extract_bounce_reason` regex extraction
- `classify_bounce` — keyword fallback already correctly handles 8 production codes that aren't explicitly documented (5.4.1, 5.4.14, 5.0.350, 5.1.10, 5.2.1, 5.4.317, 5.7.193, 5.7.350, 5.7.520). Verified — these all hit `hard_blocked` or `hard_unknown` correctly via the keyword path.
- `increment_inbox_bounces` — per-bucket counter increments
- `health_checks.py` count-based + rate-based threshold detection
- `kill_processor.py` flagging + EB tag application
- `KILL_THRESHOLD_SPAM = 1` for the *spec rule* (1 real complaint = death). Threshold is correct; problem is the input signal.

## 4. What's broken — the specific fix targets

### 4a. The bounce-FBL inference path (`sync_events.py:468-470`)

```python
elif folder == 'bounced' and bounce_type == 'hard_blocked':
    is_spam = self.is_spam_complaint(body, bounce_reason)
```

`is_spam_complaint` checks 15 FBL header patterns plus 3 SMTP codes (`550 5.7.1`, `550 5.7.51`, `550 5.7.511`) with complaint keywords (`'complaint', 'abuse', 'report', 'user'`). The word `'user'` appears in many legitimate non-complaint NDRs ("this user is no longer employed", "user not able to receive mail from unapproved senders"). The 5.7.x codes are policy/auth/IP-rep rejections — not user complaints. Microsoft's 2026 NDR catalog explicitly defines 5.7.51 as "TenantInboundAttribution / partner connector restriction" — a B2B configuration issue, not a complaint.

### 4b. Misclassified spec entry (`docs/concepts/kill-triggers.md:274`)

```
| 550 | 5.7.51 | hard_blocked + spam | spam_complaint |
```

Wrong per Microsoft's own documentation. Should say `hard_blocked / hard_blocked_24h` like other 5.7.x codes.

### 4c. Bounce body retention (`sync_events.py:385`)

```python
if folder == 'bounced':
    store_body_full = None
```

Bounce bodies are wiped at insert. Forensic post-hoc analysis impossible. Storage cost is trivial; capability gain is large.

## 5. What's missing — sender-side ban codes

Microsoft 5.7.x family has a set of codes that mean **Microsoft itself banned our sending account/IP/tenant for outbound abuse** — the strongest possible "this inbox is dead" signal:

| Code | Meaning |
|------|---------|
| 5.7.501 | "Access denied, spam abuse detected" — sending account banned |
| 5.7.502 / 5.7.503 | "Access denied, banned sender" |
| 5.7.508 | IPv6 send-rate exceeded |
| 5.7.511 | "Access denied, banned sender" — IP on Microsoft blocklist |
| 5.7.606–649 | Banned sending IP range |
| 5.7.703 | Recipient Tenant Allow/Block List blocked |
| 5.7.705 / 5.7.708 | Tenant exceeded outbound abuse threshold |
| 5.7.750 | Unregistered domain block |
| 5.7.800 | EHLO/P1/P2 sender domain banned |

Production has 0 hits in last 30 days for these specific codes — but when one fires, instant-kill is the right call. We currently miss them entirely; they fall through to the generic 5.7.x → `hard_blocked` bucket and only kill at `hard_blocked_24h ≥ 2`.

## 6. Phase plan

### Phase 1 — Documentation correction (zero behavior change) — ✅ SHIPPED 2026-05-01 (commit `a206da3`)

**Scope:**
- Replace 7-row SMTP table in `docs/concepts/kill-triggers.md` with full B2B-focused table (~25 rows) covering Microsoft 365 + Google Workspace
- Add `Provider` column, mark which codes are sender-side warnings vs recipient-side rejections
- Add explicit note: NO SMTP code from MS/Google means "user reported as spam"
- Document the out-of-band FBL channels (JMRP for MS, Postmaster Tools for Gmail)
- Remove the wrong row mapping `5.7.51 → spam_complaint`
- Add the 8 codes already in production but undocumented (5.4.1, 5.4.14, 5.0.350, 5.1.10, 5.2.1, 5.4.317, 5.7.193, 5.7.350, 5.7.520)

**Files touched:** `docs/concepts/kill-triggers.md` (one file, doc-only)

**Behavior change:** None.

**Risk:** Zero. Pure documentation.

**Acceptance criteria:**
- [ ] Operator reading the doc gets accurate code reference
- [ ] No code path references the doc's table (verified — table is human-reference only)

---

### Phase 2 — Disable bounce-FBL inference (one-line) — ✅ SHIPPED 2026-05-01 (commit `8dd3011`)

Verified production sample: 2/72 hard_blocked bounces (2.8%) were firing the false-positive heuristic — both fitnessintl.com Microsoft 365 mail-flow rule blocks ("user not able to receive mail from unapproved senders"), neither real complaints. 69-test parser suite at `tests/test_bounce_parsing.py` pins all 4 parser functions' behavior; 100/100 random production bounces classify identically to stored bounce_type after the change. Function preserved (not deleted) for forensic re-analysis once Pass 4 + Pass 5 land.



**Scope:**
- `sync_events.py:468-470`: change `is_spam = self.is_spam_complaint(body, bounce_reason)` to `is_spam = False` for `folder='bounced'` path
- Add code comment with reasoning + audit reference (this plan)
- Leave `is_spam_complaint` function in place (dormant — keeps git history readable, avoids deletion churn)

**Files touched:** `sync_events.py` (3 lines)

**Behavior change:**
- Inboxes hitting bounce-body text matches that previously incremented `complaints_lifetime` → no longer trigger instant-kill via `spam_complaint`
- Same inboxes still die from `hard_blocked_24h ≥ 2` after a second bounce within 24h (typical case for repeated policy rejection)
- Net effect: ~24h delay on death for false-positive cases (saves the 1-bounce false-positives entirely); zero protection lost on real reputation problems

**Risk:** Low. The rate-based and count-based safety net (already in production) catches the same inboxes via the correct signal.

**Acceptance criteria:**
- [ ] `complaints_lifetime` increments stop firing from bounce-body matches (monitor 7 days post-deploy)
- [ ] Total `hard_blocked_24h ≥ 2` kills stay roughly flat or slightly increase (we should now catch via the right rule what the heuristic was catching incorrectly)
- [ ] No drop in real reputation-based kills (rate-based logic still firing)

---

### Phase 3 — Add sender-ban code detection (additive, new capability)

**Scope:**
- Extend `extract_bounce_reason` to surface specific sender-ban codes (5.7.501/502/503/508/511/606-649/703/705/708/750/800)
- Add new `bounce_type='sender_banned'` (or new column `sender_ban_code`)
- Add `KILL_THRESHOLD_SENDER_BANNED = 1` (instant-kill, env-overridable)
- Add per-code Slack alert with framing: "Microsoft has banned this inbox/IP/tenant for outbound abuse"
- Add to `kill-triggers.md` table with severity flag

**Files touched:** `sync_events.py` (~10 lines), `health_checks.py` (~10 lines), `kill-triggers.md` (table row), env config

**Behavior change:** Net new capability. Production has 0 hits in last 30 days for these specific codes — so day-1 impact is 0 inboxes killed. When a real ban fires, instant-kill triggers at the source signal instead of waiting for `hard_blocked_24h ≥ 2`.

**Risk:** Low. Additive only — doesn't change existing classification. Worst case: a legit edge-case 5.7.501 doesn't actually mean banned (we haven't verified Microsoft never sends it for transient reasons). Mitigation: alert-first, kill-second (operator can review the first sender_banned trigger before automating).

**Acceptance criteria:**
- [ ] Slack alert fires within 5 min of a sender-ban code appearing in production
- [ ] Tagged kill `flagged_sender_banned` correctly applied in EB
- [ ] Operator can review per-code trigger before broad rollout (optional first-week shadow mode)

---

### Phase 4 — Keep `body_full` for bounces + silent-error fix — ✅ SHIPPED 2026-05-01 (commit `995cd74`)

Three coordinated changes:
1. `sync_events.py:382-389` — `store_body_full = None` removed for bounces. `body_full` now stored. 90-day retention via existing `cleanup_bounce_messages` already covers cleanup — no separate retention work needed.
2. `sync_campaign_replies` per-reply `print(...)` exception replaced with `audit.add_error()` when audit context is provided. Errors now reflected in `records_failed` + `error_log` instead of silently lost.
3. Same fix applied to per-folder fetch errors (when `get_all_campaign_replies` raises).

Backward-compat: `audit` is `Optional`; legacy callers (deprecated `sync_all_active_campaigns`) fall back to a `[silent-error-fallback]` print marker. 69-test parser suite still passes. Production audit confirmed `events` sync_type has 0 records_failed in 24h (clean).



**Scope:**
- `sync_events.py:382-389`: remove `store_body_full = None` for bounces; keep full body
- Add 90-day retention cleanup to `run_retention_cleanup` (drop `body_full` for bounces older than 90 days)

**Files touched:** `sync_events.py` (1 line removed), `emailbison_sync_worker.py` (~5 lines retention)

**Behavior change:** None at signal/kill level. Storage growth: ~10MB/month estimated based on current bounce volume × ~5KB avg body. Negligible.

**Risk:** Zero.

**Acceptance criteria:**
- [ ] New bounces have non-null `body_full`
- [ ] Forensic re-analysis of any new spam_complaint or sender_banned kill is possible

---

### Phase 3 — Sender-ban code detection — ✅ SHIPPED 2026-05-01 (commit `5688789`)

Detects 10 Microsoft sender-ban exact codes (5.7.501/502/503/508/511/703/705/708/750/800) plus 5.7.606-649 IP range. Fires Slack alert at critical level on first hit. NO kill behavior change yet — alert-first per the plan.

5.7.509 (DMARC reject) was considered but excluded after production sanity check showed 11 hits in 30 days — that's a DMARC alignment issue, not a Microsoft ban verdict. Continues to count via `hard_blocked_24h` instead.

23 unit tests cover all codes, IP range boundaries, and false-positive prevention against `5.7.1` / `5.7.193` / `5.7.350` / `5.7.51` / `5.1.1`. Production sanity: 0 alerts would have fired in the last 30 days. The alert path is dormant until a real ban event occurs.

After 7 days of clean alert observation, a follow-up commit will flip to alert + instant-kill behavior.

### Phase 6 — Apply silent-error pattern to sync_campaigns + sync_engagement

**Scope:**
Audit at 2026-05-01 evening surfaced two pre-existing observability gaps in modules NOT touched by Pass 4:

| Module | records_failed/24h | partial-status runs/24h | error_message populated? |
|--------|-------------------:|------------------------:|:------------------------:|
| `sync_modules/sync_campaigns.py` | 242 | 61 of 222 (27%) | ❌ null |
| `sync_modules/sync_engagement.py` | 1597 | 7 of 11 (64%) | ❌ null |

The COUNTS are tracked correctly (better than the pre-Pass-4 `events` situation where counts were also lost). The CAUSE is not — `error_message` is `null` on partial-status rows, so we know there are failures but not why. Apply the same `audit.add_error(record_id, error, details)` pattern to the per-record exception sites in both modules.

**Files touched:** `sync_modules/sync_campaigns.py` + `sync_modules/sync_engagement.py` — surface area is the per-record loop body.

**Behavior change:** None. `records_failed` count stays identical; `error_log` JSONB now populated.

**Risk:** Low. Same pattern Pass 4 used — proven to work, tests in place.

**Gating:** Should be done before any further extraction work that depends on these modules being trustworthy. Not blocking Pass 3 or Pass 5.

---

### Phase 5 (FUTURE) — Out-of-band FBL ingestion (separate project)

**Scope:**
- Register an FBL recipient address with Microsoft JMRP (enroll via SNDS at `https://sendersupport.olc.protection.outlook.com`)
- Add `Feedback-ID: <sender-id>:<campaign-id>:<workspace-id>` header to outbound mail (configure in EmailBison)
- Build `apps/fbl-consumer/` — small Python service that:
  - Polls the FBL inbox (or webhook receives ARF emails)
  - Parses ARF format (RFC 5965)
  - Increments `complaints_lifetime` on the matching sender
- Configure Gmail Postmaster Tools account; integrate with Gmail Postmaster Tools API (read-only) for daily complaint-rate signal

**Files touched:** New `apps/fbl-consumer/`, EB outbound config, separate ADR

**Behavior change:** Real spam complaints actually get detected. The `KILL_THRESHOLD_SPAM = 1` rule becomes safe to act on (was structurally unsafe before).

**Risk:** Medium — net new ingestion pipeline, ARF parsing, EB header injection.

**Sequencing:** Gated on Phase 1–4 stability. After 30 days of clean Phase 2 metrics, scope this as its own plan.

**Acceptance criteria:** N/A this sprint.

---

## 7. Impact analysis on existing records

This is the question the operator cares about most. Answer: **essentially zero retroactive impact, minimal forward impact.**

| Existing record | Impact |
|-----------------|--------|
| `inbox_state`, `kill_trigger`, `inventory_pool_status` on historical 383 spam_complaint kills | Unchanged. Not unwound. No restoration unless operator decides per-row. |
| Historical `bounce_type` values | Unchanged. Already correct via keyword fallback. |
| Historical `complaints_lifetime` counts | Unchanged. Frozen at current values. |
| New `complaints_lifetime` increments post-Phase 2 | Stop firing from bounce-body matches. Only fire from `folder='spam'` (rare — currently 0) or `folder='inbox'` reply phrase match (active-voice patterns, low FP rate). |
| New kills post-Phase 2 | Same inboxes still die — but via `hard_blocked_24h ≥ 2` (right reason) instead of `spam_complaint` (wrong reason). ~24h delay on death for false-positive cases. |
| New kills post-Phase 3 | Net new sender_banned kills will fire when codes appear. Production has 0 in last 30 days — day-1 impact = 0. |

### The honest tradeoff for Phase 2

Disabling the bounce-FBL inference means **inboxes that previously died on the first bounce-with-FBL-keywords will now wait for a second bounce (within 24h) before dying.**

This is the right tradeoff because:
1. The first-bounce trigger was misclassifying admin policy rejections as user complaints (5/5 sampled were FPs)
2. Real reputation problems generate multiple hard_blocked bounces in 24h naturally
3. Single-bounce admin policy block (recipient terminated, group config, etc.) does not represent reputation damage and shouldn't kill a healthy inbox

## 8. Sequencing within the program

This plan slots into `INBOX-INTEGRITY-PROGRAM.md` §3 status board as a new workstream:

```
TODAY → ship Pass 1 (docs)
THIS WEEK → ship Pass 2 (one-line disable) + Pass 4 (body_full retention)
NEXT WEEK → ship Pass 3 (sender-ban detection, alert-first mode)
NEXT SPRINT → scope Pass 5 (FBL ingestion as separate project)
```

Order rationale:
- Pass 1 is documentation correctness — operator-facing accuracy. No risk. Ship first.
- Pass 2 is the largest behavior change with the highest defensible benefit. Ship after Pass 1 so the operator has the corrected mental model.
- Pass 4 unlocks forensic capability for any kills that fire under the new logic.
- Pass 3 adds new capability — alert-first for one week to let operator review actual ban codes before auto-kill.

## 9. Open decisions

| # | Decision | Default if unanswered |
|:-:|----------|----------------------|
| KT-1 | Ship Pass 2 with retroactive "review" of historical 383 kills, OR leave them as-is? | Leave as-is — operator can audit any specific row on demand; bulk re-classification not warranted |
| KT-2 | Phase 3 alert-first window length | 7 days — operator reviews each sender_banned trigger; flips to auto-kill if all confirmed real |
| KT-3 | Phase 5 (FBL ingestion) — Microsoft JMRP first or Gmail Postmaster Tools first? | JMRP — easier to implement (ARF email parsing) than Postmaster Tools API integration |
| KT-4 | Should `KILL_THRESHOLD_SPAM` change from 1 once Phase 5 ships? | No — when real FBL signals arrive, 1 = death is the correct rule per industry standard (<0.3% complaint rate threshold from Google guidelines means single complaint on low-volume inboxes is severe) |

## 10. Sources

Authoritative 2026 references used in this plan:

- [Email nondelivery reports (NDRs) and SMTP errors in Exchange Online — Microsoft Learn (2026-04-03)](https://learn.microsoft.com/en-us/troubleshoot/exchange/email-delivery/ndr/non-delivery-reports-in-exchange-online)
- [Fix NDR error 550 5.0.350 in Exchange Online — Microsoft Learn](https://learn.microsoft.com/en-us/troubleshoot/exchange/email-delivery/ndr/fix-error-code-550-5-0-350-in-exchange-online)
- [Fix NDR error 5.4.6 through 5.4.20 in Exchange Online — Microsoft Learn](https://learn.microsoft.com/en-us/troubleshoot/exchange/email-delivery/ndr/fix-error-code-5-4-6-through-5-4-20-in-exchange-online)
- [Fix NDR error 550 5.1.1 through 5.1.20 in Exchange Online — Microsoft Learn](https://learn.microsoft.com/en-us/troubleshoot/exchange/email-delivery/ndr/fix-error-code-550-5-1-1-through-5-1-20-in-exchange-online)
- [550 5.7.51 TenantInboundAttribution — n-able Mail Assure KB](https://documentation.n-able.com/mail-assure/troubleshooting/Content/kb/ERROR-550-5-7-51-TenantInboundAttribution-domain-either-RestrictDomainsToIPAddresses-or-RestrictDomainsToCertificate-set.htm)
- [Microsoft delist portal (5.7.511) — Microsoft Defender for Office 365](https://learn.microsoft.com/en-us/defender-office-365/external-senders-use-the-delist-portal-to-unblock-yourself)
- [Gmail SMTP errors and codes — Google Workspace Admin Help](https://knowledge.workspace.google.com/admin/support/troubleshooting/gmail-smtp-errors-and-codes)
- [Email sender guidelines — Google Workspace Admin Help](https://support.google.com/a/answer/81126?hl=en)
- [How to set up the Gmail complaint feedback loop — InboxAlly](https://www.inboxally.com/docs/provider-deliverability-guides/gmail-complaint-feedback-loop-setup/)
- [Microsoft Junk Email Reporting Program (JMRP)](https://sendersupport.olc.protection.outlook.com/snds/JMRP.aspx)
- [Email Feedback Loop Explained 2026 — Mailtrap](https://mailtrap.io/blog/email-feedback-loop/)
- [RFC 5965 — Abuse Reporting Format (ARF)](https://datatracker.ietf.org/doc/html/rfc5965)

## 11. Production audit data (2026-05-01 evening)

Captured at plan-creation time for reference and Pass 2 acceptance baseline.

**Fleet-wide spam_complaint kills (all-time):** 383
- 0 had `folder='spam'` evidence (the strongest signal — currently inaccessible)
- 361 had hard_blocked bounces (the heuristic path)
- 273 had inbox-folder replies (active-voice path)

**Historical kill distribution by workspace:**

| Workspace | spam_complaint kills | First | Last |
|-----------|-------------------:|-------|------|
| Spout | 187 | 2026-02-14 | 2026-04-30 |
| Selery | 57 | 2026-03-09 | 2026-04-30 |
| Sammy | 45 | 2026-02-14 | 2026-03-01 |
| SPUI | 23 | 2026-02-14 | 2026-04-17 |
| Hello Hero | 21 | 2026-02-18 | 2026-04-22 |
| Search Atlas | 20 | 2026-03-10 | 2026-04-30 |
| Linkgraph | 11 | 2026-03-11 | 2026-04-28 |
| Charm | 6 | 2026-02-26 | 2026-03-06 |
| Stable Kernel | 5 | 2026-03-09 | 2026-04-28 |
| EventPanda | 4 | 2026-02-14 | 2026-02-18 |
| Barrena | 3 | 2026-04-14 | 2026-04-14 |
| SKMR | 1 | 2026-05-01 | 2026-05-01 |

**Sample 5/5 forensic recent kills — all false-positive pattern:**

| Inbox | bounce_reason | NDR meaning | Real spam complaint? |
|-------|---------------|-------------|---------------------|
| m.elzey@scalestablekernel.com | `550 \| blocked policy` | "User no longer employed" admin rule | ✗ |
| reuben_vollmer@gospoutwater.com | `550 5.7.51 \| blocked spam` | TenantInboundAttribution partner connector | ✗ |
| ryanwestberg_w@loveselery.com | `550 5.7.350 \| blocked spam` | Recipient external server filter (server, not user) | ✗ |
| reuben.vollmer@clearspoutwater.com | `550 5.7.1 \| blocked spam` | "Not able to receive from unapproved senders" admin rule | ✗ |
| sophia_s@advancesearchatlas.com | `550 5.7.193 \| blocked spam` | Group not configured for inbound | ✗ |

**Production bounce code coverage (last 30 days):**

| Code | Count | Documented? | Behavior correct? |
|------|------:|:-----------:|:-----------------:|
| 554 (no extended) | 223 | ❌ | ✓ (keyword fallback → hard_blocked) |
| 550 (no extended) | 132 | ❌ | ✓ (keyword fallback) |
| 550 5.4.1 | 195 | ❌ | ✓ (keyword fallback → hard_unknown) |
| 550 5.1.1 | 178 | ✓ | ✓ |
| 550 5.0.350 | 67 | ❌ | ✓ (keyword fallback → hard_blocked) |
| 554 5.4.14 | 65 | ❌ | ✓ (keyword fallback) |
| 550 5.1.10 | 83 | ❌ | ✓ (keyword fallback) |
| 550 5.7.350 | 49 | ❌ | ✓ (5.7.x rule) |
| 550 5.7.193 | 80 | ❌ | ✓ (5.7.x rule) |
| 550 5.2.1 | 29 | ❌ | ✓ (keyword fallback) |
| 550 5.4.317 | 17 | ❌ | ✓ (keyword fallback) |
| 550 5.7.520 | 16 | ❌ | ✓ (5.7.x rule) |
| 550 5.7.1 | 15 | ✓ | ✓ |
| 550 5.7.51 | (smaller sample) | ✓ but mislabeled as spam_complaint | ✗ Pass 1 fixes |

**Conclusion:** 8 production codes are undocumented but already-classified-correctly. The bug is the spam_complaint inference, not the bucket classification.
