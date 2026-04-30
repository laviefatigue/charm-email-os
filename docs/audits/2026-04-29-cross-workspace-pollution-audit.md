---
title: Cross-Workspace Inbox Pollution — Fleet Audit
date: 2026-04-29
author: Claude (audit), elliott@laviefatigue.com (commissioning)
status: action-required
severity: high (one workspace has 22 foreign-tenant inboxes currently tagged 'live')
methodology: per-workspace EB API query (workspace-scoped Sanctum tokens) cross-referenced with `domains` table ownership
related: docs/work-logs/2026-04-27-tagging-kill-overhaul-plan.md (notes earlier 17 cross-workspace mismatches in Sammy)
---

# Cross-Workspace Inbox Pollution — Fleet Audit

## TL;DR

Of **3,242 EB-side senders across 11 active workspaces**, **82 are registered in the wrong workspace** (their domain belongs to a different client per our `domains` table). Of those 82, **22 are currently tagged `live` in Sammy's EB workspace and would be activated by the EOD reapply tool — these are SPUI mailboxes**, sending Sammy outbound through SPUI's actual Google infrastructure.

Cross-workspace API key isolation is working correctly; the pollution is at the **inbox-creation layer**, where mailboxes are being registered into the wrong EB workspace at provisioning time.

**DO NOT run `eod-reapply --apply` against Sammy or Stable Kernel Market Research until this is reconciled.**

## Summary table

Each workspace queried with its own Sanctum token (`workspace_api_keys.key_token`). "Foreign" means the inbox's domain (per our `domains.workspace_id`) doesn't match the workspace it's registered in.

| Workspace | EB total senders | live | Legitimate | Foreign | Foreign+live | Status |
|---|---|---|---|---|---|---|
| Barrena | 39 | 0 | 39 | 0 | 0 | ✓ clean |
| Charm | 437 | 15 | 437 | 0 | 0 | ✓ clean |
| Hello Hero | 520 | 322 | 520 | 0 | 0 | ✓ clean |
| Linkgraph | 238 | 76 | 238 | 0 | 0 | ✓ clean |
| SPUI | 95 | 84 | 95 | 0 | 0 | ✓ clean |
| **Sammy** | 691 | 22 | 639 | **52** | **22** | 🚨 immediate risk |
| Search Atlas | 667 | 346 | 667 | 0 | 0 | ✓ clean |
| Selery | 732 | 338 | 732 | 0 | 0 | ✓ clean |
| Spout | 548 | 98 | 546 | 2 | 0 | ⚠ minor |
| Stable Kernel | 175 | 10 | 175 | 0 | 0 | ✓ clean |
| **Stable Kernel Market Research** | 100 | 0 | 72 | **28** | 0 | ⚠ latent |

## Mismatch detail by pair

### 🚨 IMMEDIATE risk: Sammy ← SPUI (22 senders, all live)

**SPUI's `growspui.com` mailboxes are registered as Sammy senders, all tagged `live`.**

```
Sender workspace (in EB): Sammy
Domain owner (per DB):    SPUI
Count:                    22
Domain:                   growspui.com (single domain)
EB sender ids:            9206 .. 9227 (consecutive — batch creation)
Created in DB:            2026-03-31 (single day, all 22 at once)
Pool status:              live (in Sammy)
Connection status:        Connected (all 22)
```

**What would happen if EOD reapply runs on a Sammy active campaign**: these 22 are Sammy's entire current `live` set. The reapply tool would attach them to Sammy campaigns. When those campaigns send, the email physically routes through SPUI's actual Google mailboxes (the OAuth tokens point at SPUI's infrastructure). SPUI's "Sent" folder shows Sammy's outbound. **Cross-tenant data leak via shared underlying mailbox.**

The `eod-reapply` tool's existing `max_removal_pct=50` guard happens to block this (Sammy #63 would trip the 100% removal guard), but only by accident — if Sammy had partial overlap between its real attached set and these 22, the guard wouldn't trip and the leak would happen.

### ⚠ Latent risk #1: Sammy ← Spout (30 senders, all reserve/dead)

**Spout's `discoverspoutwater.com` mailboxes registered in Sammy's EB workspace.**

```
Sender workspace (in EB): Sammy
Domain owner (per DB):    Spout
Count:                    30
Domain:                   discoverspoutwater.com
EB sender ids:            ~9329..9358 (consecutive — batch creation)
Pool status:              not currently live (would be if promoted)
Risk:                     would become live after lifecycle promotion → next reapply triggers cross-tenant
```

These are NOT in our DB sender_accounts table at all (or are inactive there). The DB-side mismatch query missed them. Only the per-workspace EB scan caught them.

### ⚠ Latent risk #2: Stable Kernel Market Research ← Sammy (28 senders, all reserve)

**Sammy-domain mailboxes registered in SKMR's EB workspace.**

```
Sender workspace (in EB): Stable Kernel Market Research
Domain owner (per DB):    Sammy
Count:                    28 (DB shows 22 active; EB has 28 total)
Domains:                  11 distinct: analyzestablekernel.com, examinestablekernel.com,
                          forecaststablekernel.com, insightstablekernel.com, managestablekernel.com,
                          modelstablekernel.com, powerstablekernel.com, quantifystablekernel.com,
                          revealstablekernel.com, scalestablekernel.com, processstablekernel.com
Wait — those domains have "stablekernel" in them but are owned by Sammy?
```

This case is interesting: the domains have `stablekernel` in their names but `domains.workspace_id` points to **Sammy**. Either:
- (a) The domains were misregistered to Sammy when they should've been to SKMR. Names suggest they're SKMR's.
- (b) Sammy legitimately owns these stablekernel-themed domains (test/marketing domains), and SKMR is using them.

**Both interpretations are problems.** Either the `domains` table is wrong for these 11 entries, or SKMR is registering mailboxes against another workspace's domains. Needs human judgment from ops to determine which.

```
Created in DB:            2026-04-14 (single day batch)
Pool status:              reserve
```

### ⚠ Minor: Spout ← SPUI (2 senders, dead)

```
Sender workspace (in EB): Spout
Domain owner (per DB):    SPUI
Count:                    2
Emails:                   b.sheth@setspui.com, bhoumik@setspui.com
EB sender ids:            8859, 8860 (consecutive)
State:                    not live; not in any active campaign
```

Old residue. Low priority.

### Stale DB-only records (not in EB anymore)

The DB-side query also surfaced these, but they're already gone from EB:

- 7 Linkgraph rows pointing at `*searchatlas.com` domains (created 2026-03-11, `is_active=False`, not in Linkgraph's EB workspace anymore — already cleaned up at EB layer, DB just has stale rows).
- 4 Sammy rows pointing at `*selery.com` / `*spoutwater.com` (created 2026-02-26 / 2026-04-02, `is_active=False`).

These need a DB cleanup but pose no operational risk.

## Temporal pattern — strong signal of batch provisioning bugs

| Date | Mismatches created | Pair | Likely cause |
|---|---|---|---|
| 2026-03-11 | 7 | Linkgraph ← Search Atlas | Hypertide batch — wrong workspace_id at provisioning |
| 2026-02-26 | 1 | Sammy ← Spout (mistspoutwater) | One-off |
| 2026-03-31 | 22 | **Sammy ← SPUI (growspui)** | Hypertide batch — 22 inboxes, single domain, single day |
| 2026-04-02 | 3 | Sammy ← Selery | Smaller batch |
| 2026-04-14 | 22+28 | SKMR ← Sammy + others | **Largest batch — 22 inboxes per pair, single day** |

**Each pollution event is a clean batch on a single day.** Random pollution would be spread across time. These are batches → almost certainly originate from automated provisioning. Hypertide is the prime suspect.

We could not directly link the implicated `sender_accounts` rows to `inbox_purchase_jobs` records (the JOIN returned 0 matches in our test). Possible reasons:
- Hypertide writes to a different table for newly-provisioned inboxes
- The provisioning path doesn't go through `inbox_purchase_jobs` for some workspace types
- Schema we expected doesn't exist

Worth a follow-up: trace which provisioning code path was used for the 22 SPUI inboxes registered into Sammy on 2026-03-31.

## Why the API key isolation is NOT the bug

The user's intuition is right — workspace API keys are correctly scoped. EB Sanctum tokens are bound to a specific team_id at creation; they can't read or write across workspaces.

The bug is **upstream of the API key**, at the moment a sender is being CREATED in EB:

1. Provisioning code (likely Hypertide) holds an admin key OR a workspace-scoped key.
2. It calls `POST /api/sender-emails` with a workspace selector / context.
3. **The workspace context being passed is wrong** — the inbox gets created in `Sammy`'s team, even though the OAuth target is SPUI's mailbox.

Once the inbox is wrongly registered, any later interaction (reading senders, applying tags, attaching to campaigns) goes through whatever workspace key is in scope. The pollution propagates.

EB itself has no concept of "this domain belongs to SPUI" — domain-to-workspace ownership exists only in our DB. So EB doesn't reject the registration. **It's our job to enforce this constraint.**

## Recommendations

### Immediate (before any reapply runs against Sammy)

1. **Block Sammy from reapply until the 22 SPUI inboxes are off Sammy's `live` tag.**
   - Either remove them from Sammy's EB workspace entirely (operator via EB UI or scripted DELETE), or strip the `live` tag from them so the reapply target_set is clean.
2. **Investigate SKMR/Sammy 28-row mismatch** to determine whether the domains are misowned (fix domains table) or the senders are misregistered (fix sender_accounts and EB).

### Code-level (eod-reapply tool)

3. **Add cross-workspace tenant guard to `eod-reapply`.** Both subcommands:
   - `check`: report any foreign-domain senders in the target_set as a `[FAIL]`.
   - `reapply --apply`: refuse if any sender in `to_attach` has `domain_owner != campaign_workspace`. New status `SKIPPED_CROSS_WORKSPACE_TENANT`, exit code 2.

   This makes the EOD reapply tool incapable of triggering a cross-tenant leak even if pollution exists.

   The check is one DB join: for each sender in target_set, look up the domain's workspace_id and compare to the campaign's workspace_id. ~30 minutes of work plus tests.

### Process-level (ongoing monitoring)

4. **Productionize this audit as a recurring check.** Schedule the per-workspace EB scan to run daily. Alert (Slack) on any non-zero foreign count. Same SQL + EB query pattern as this report.
   - Suggested location: a new `scripts/audit_cross_workspace_pollution.py` that runs in a Coolify cron worker or as a hook in `emailbison-sync`.
   - Output goes to `audit_logs` table or Slack channel.

5. **Add a database CHECK constraint or trigger** to enforce `sender_accounts.workspace_id = (domains where domain_name = SPLIT_PART(email_address,'@',2)).workspace_id`. PostgreSQL can enforce this:
   ```sql
   CREATE OR REPLACE FUNCTION sender_account_workspace_matches_domain()
   RETURNS TRIGGER AS $$
   DECLARE expected_ws UUID;
   BEGIN
     SELECT workspace_id INTO expected_ws FROM domains
     WHERE domain_name = SPLIT_PART(NEW.email_address, '@', 2);
     IF expected_ws IS NOT NULL AND expected_ws != NEW.workspace_id THEN
       RAISE EXCEPTION 'sender_account workspace mismatch: email % belongs to ws %, got %',
         NEW.email_address, expected_ws, NEW.workspace_id;
     END IF;
     RETURN NEW;
   END $$ LANGUAGE plpgsql;

   CREATE TRIGGER trg_sender_account_workspace_check
   BEFORE INSERT OR UPDATE OF workspace_id, email_address ON sender_accounts
   FOR EACH ROW EXECUTE FUNCTION sender_account_workspace_matches_domain();
   ```
   This stops the bleeding at the DB write boundary. Existing rows are not affected; the trigger only fires on INSERT/UPDATE going forward. Hypertide bugs would surface immediately as a constraint violation rather than silent pollution.

### On the user's question — "should we add a domain pattern to the client record?"

**The `domains.workspace_id` IS the domain pattern** — it's per-domain workspace ownership, fully explicit, no regex needed. We should USE it more, not add a parallel system.

That said, **a `clients.domain_pattern` regex field could be a useful second defense at provisioning time** — when Hypertide creates a new domain, validate that the new domain matches the client's pattern before assigning. This catches the upstream provisioning bug before a domain even gets created with the wrong workspace_id.

Recommendation: don't add domain_pattern to clients yet. **First land the trigger (rec 5)** which uses what we already have. If the trigger fires often during provisioning, then add the pattern as a Hypertide-side validation to prevent the trigger from firing.

### Hypertide investigation (out of scope for this audit)

- Find the code path that created EB sender_email records on 2026-03-31 (22 SPUI inboxes into Sammy) and 2026-04-14 (50+ inboxes across two pairs).
- Look for: a workspace_id parameter being passed wrong, a default falling back to Sammy when the actual target was SPUI/SKMR, an admin key being used with the wrong context.
- Likely files: `Hypertide/automation/src/hypertide_automation/emailbison.py` and any provisioning scripts that POST to EB's sender-emails endpoint.

## Appendix A — Raw mismatch list (82 inboxes)

Stored in `audit_per_ws_full.json` next to this audit (not committed, contains real emails).

## Appendix B — How to reproduce this audit

```bash
# Required:
# - ws_keys.json (workspace API keys) — pulled from ws_keys.json or workspace_api_keys table
# - admin SQL endpoint key (from scripts/db_vs_eb_comparison.py)

# Per-workspace EB-side scan:
# For each workspace:
#   GET /api/sender-emails (paginated) — using that workspace's scoped key
#   For each sender email:
#     domain = email.split('@')[1]
#     query: SELECT workspace_name FROM domains JOIN workspaces WHERE domain_name = domain
#     if workspace_name != current_workspace_name: FOREIGN
#
# This is the workspace-by-workspace check the user requested.
# Implementation pattern: see scripts/db_vs_eb_comparison.py (DB side) and apps/eod-reapply (EB client).
```

The check could be implemented as a script in ~80 lines. Recommend putting it under `scripts/audit_cross_workspace_pollution.py` and wiring it as a Slack-alerting cron job.
