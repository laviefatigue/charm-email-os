---
title: EOD Reapply — Staging Integration Runbook (L5)
status: required-gate
created: 2026-04-29
---

# EOD Reapply — Staging Integration Runbook (L5)

**Purpose:** prove the tool works against the real EmailBison API before any
production workspace runs it. **L1–L4 unit/integration tests do not catch:**
EB API contract drift, eventual-consistency on attach/pause, rate limits,
or undefined-behavior cases (e.g. attaching an already-attached sender).

This runbook is an L5 gate, not a suggestion. Every step has a verification
step against the EB UI. Capture the outputs in `staging-results.md` (or a PR
description) so future operators can audit what was observed.

> **Run this against the `Charm` workspace, on a throwaway test campaign.**
> Do not run it against any client workspace until every section here is
> green and the unknowns are documented.

---

## 0. Pre-flight

Confirm before starting:

- [ ] You have `DATABASE_URL` for the production DB (read access to `workspaces`, `workspace_api_keys` is sufficient).
- [ ] The `Charm` workspace exists in `workspaces` and has an active row in `workspace_api_keys`.
- [ ] You can reach `https://spellcast.hirecharm.com/api` from the host running the CLI.
- [ ] You have a **dedicated test campaign** in the Charm workspace, with status `Active` or `Queued`, schedule M-F 8:00–17:00 in a known timezone, and at least 3 sender emails attached.
- [ ] At least 2 sender emails in the Charm workspace have the `live` tag (these are the candidates for the target set).
- [ ] The EmailBison UI is open in a browser, logged into the Charm workspace, ready to manually verify state at each step.
- [ ] You have the campaign's numeric `id` (visible in the EB URL when viewing the campaign).

If any of these are missing, stop. The runbook will not be valid.

---

## 1. Smoke: CLI starts, reads DB

```bash
cd apps/eod-reapply
pip install -e .            # one-time
export DATABASE_URL='postgresql://...'
export EMAILBISON_API_URL='https://spellcast.hirecharm.com/api'

# Invalid workspace name → expected: clean error, exit 2
eod-reapply reapply --workspace "DOES_NOT_EXIST" --campaign-id 0
echo "exit: $?"
```

**Expect:**
- `ERROR: workspace 'DOES_NOT_EXIST' not found, inactive, or missing API key`
- exit code `2`
- No HTTP calls made (DB lookup fails first)

**Capture:** that the message printed and the exit code matched.

---

## 2. Get-campaign sanity (read-only, no schedule)

Use `--skip-time-check` to bypass the gate for now. We're just probing the
EB API contract.

```bash
eod-reapply reapply \
  --workspace "Charm" \
  --campaign-id <TEST_CAMPAIGN_ID> \
  --skip-time-check
echo "exit: $?"
```

This is dry-run by default, so no mutation. The orchestrator will:
1. Fetch the campaign (assert status is in {Active, Queued, Sending}).
2. Resolve the `live` tag id.
3. Fetch the live-tagged senders (target set).
4. Fetch the campaign's currently attached senders (prior set).
5. Compute the diff and stop (dry-run).

**Verify by EB UI:**
- [ ] The campaign's status in EB UI matches what the JSON output reported (`status` field after fetch).
- [ ] The senders listed in `prior_set` match the EB UI's "Sender Emails" tab on the campaign.
- [ ] The senders listed in `target_set` match the result of filtering "Email Accounts → Tags = live" in the EB UI.

**Capture:**
- Exit code (expect 0 for no-diff or 1 for would-have-changed).
- The full JSON output (paste into staging-results).
- Whether `target_set` and `prior_set` match the EB UI counts.

> 🛑 **STOP if:** the JSON shape differs from what L2 mocks assumed (e.g.
> different field names, sender objects nested differently, pagination
> metadata in a different key). Document the actual shape and update
> `eb_client.py` + L2 tests before continuing.

---

## 3. Schedule pull

Without `--skip-time-check`, run the same command. The orchestrator will
additionally fetch the campaign's schedule and run it through `evaluate_window`.

```bash
eod-reapply reapply \
  --workspace "Charm" \
  --campaign-id <TEST_CAMPAIGN_ID>
```

**Two outcomes are valid:**
- exit `0` with `status: skipped_time_gate` — outside the window, the
  predicate is gating correctly. Note the `reason` field; it should match
  one of:
  - `"too early: now_local=... < trigger_at=..."` (before EOD + buffer)
  - `"today (...) is not a sending day"` (weekend)
- exit `1` with `status: skipped_dry_run` — inside the window, the dry-run
  shows the diff that would be applied.

**Verify by EB UI:**
- [ ] The schedule's `start_time`, `end_time`, `timezone` shown in the
  output match the EB UI's "Sending Schedule" tab.

**Capture:**
- The full schedule JSON (use `--json-only` for clean copy-paste).
- Whether the predicate's decision matches your expectation given the
  current time and the schedule.

> 🛑 **STOP if:** schedule timezone is returned as a non-IANA string
> (e.g. `"GMT+10"`, `"EST"`, an offset). The L1 predicate rejects these.
> Document the actual format and decide whether to adapt `_build_schedule_from_eb`
> or treat as a hard error.

---

## 4. Pause/resume bracket (no other mutation)

We need to know whether pause is observably synchronous and whether resume
restores the campaign to a sending state. This is the test L3 cannot do.

**Manually pause and resume the test campaign once via direct curl** (not
through the CLI), then verify in the EB UI:

```bash
EB_KEY='<workspace api key from workspace_api_keys.key_token>'
EB_BASE='https://spellcast.hirecharm.com/api'
CAMPAIGN_ID='<TEST_CAMPAIGN_ID>'

# Pause
curl -X PATCH \
  -H "Authorization: Bearer $EB_KEY" \
  "$EB_BASE/campaigns/$CAMPAIGN_ID/pause"
# → expect 200 with {"data": {..., "status": "Paused"}}
```

**Verify by EB UI immediately:**
- [ ] Campaign status shows `Paused` in the UI within 5 seconds.

```bash
# Now resume
curl -X PATCH \
  -H "Authorization: Bearer $EB_KEY" \
  "$EB_BASE/campaigns/$CAMPAIGN_ID/resume"
# → expect 200 with {"data": {..., "status": "Queued"}} or "Active"
```

**Verify by EB UI:**
- [ ] Campaign status shows `Queued` (or `Active`) within 5 seconds.

**Capture:**
- The exact `status` value EB returned on each call (case-sensitive).
- How long until the EB UI reflected the change (subjective; "instant" is fine).

> 🛑 **STOP if:** the returned status is something other than what L3 mocks
> assumed (`"Paused"` for pause, anything-else for resume). Update the
> `_ACTIVE_STATUSES` set in `reapply.py` if EB uses a different label
> (e.g. `"Sending"` vs `"Active"`).

---

## 5. Attach idempotency / over-attach behavior

The OpenAPI doesn't say whether attaching an already-attached sender is a
silent no-op, an error, or a duplicate. We must observe.

```bash
SENDER_ID='<an id already in prior_set from step 2>'

curl -X POST \
  -H "Authorization: Bearer $EB_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"sender_email_ids\": [$SENDER_ID]}" \
  "$EB_BASE/campaigns/$CAMPAIGN_ID/attach-sender-emails"
```

**Document the response.** Possible outcomes:
- `200 {"success": true, ...}` — silent dedup (EB's job, our orchestrator is fine)
- `409` or `422` — error on duplicate
- `200` but `GET /sender-emails` shows the sender twice — duplicate state

**Verify by EB UI:**
- [ ] Sender list on the campaign shows the same count as before (silent dedup) or has the sender duplicated.

**Capture the answer.** This determines whether our `attached_ids` logic
needs to filter out IDs that are already in `prior_set` (currently it does,
via set arithmetic — so we should always be safe — but the staging test
proves it).

---

## 6. Remove non-attached behavior

Same probe in the other direction:

```bash
NONEXISTENT_ID=999999  # high enough to definitely not be in this campaign

curl -X DELETE \
  -H "Authorization: Bearer $EB_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"sender_email_ids\": [$NONEXISTENT_ID]}" \
  "$EB_BASE/campaigns/$CAMPAIGN_ID/remove-sender-emails"
```

**Document the response.** Possible outcomes:
- `200 {"success": true, ...}` — silent no-op
- `404` or `422` — error

**Capture.** If EB raises, our orchestrator's remove step would fail and
trigger the resume-on-finally path. That's safe but operationally
disruptive — we'd want to filter `to_remove` to only IDs we know are in
prior_set first. Currently we already do (it's a set difference).

---

## 7. End-to-end dry-run (the real shape)

Re-run step 2 with verbose output:

```bash
eod-reapply reapply \
  --workspace "Charm" \
  --campaign-id <TEST_CAMPAIGN_ID> \
  --skip-time-check
```

**Verify:**
- [ ] `status` is `skipped_dry_run` if there's a diff, or `skipped_no_diff` if not.
- [ ] `is_dry_run` is `true`.
- [ ] No status change visible in the EB UI (campaign was never paused).
- [ ] The diff makes sense given what you see in the UI.

**Capture the full JSON.**

---

## 8. End-to-end --apply (the real run)

> Only proceed if steps 1–7 are all green and any unknowns are documented.

Pick a moment when the test campaign's window is open (or use
`--skip-time-check` if you've manually verified the schedule).

```bash
eod-reapply reapply \
  --workspace "Charm" \
  --campaign-id <TEST_CAMPAIGN_ID> \
  --apply
```

**Watch the EB UI in real-time during this run.** Expect:

1. Campaign status flips to `Paused`.
2. Sender list updates (additions appear, removals disappear).
3. Campaign status returns to `Queued` or `Active`.

**Verify after exit:**
- [ ] Exit code `0`.
- [ ] `status: succeeded` in JSON.
- [ ] `verify_passed: true`.
- [ ] Final EB UI sender list matches the JSON `final_set` exactly.
- [ ] Campaign is sending again (or queued for next slot).

**Capture:**
- Total wall-clock duration of the run (subjective ok).
- Whether you observed any unexpected campaign state at any point.
- Full JSON output.

> 🛑 **STOP if:** verify_passed is false, OR exit code is anything other
> than 0, OR the campaign is left paused. Capture the full state and
> resume the campaign manually if needed before any other action.

---

## 9. Failure scenario — manual interrupt

This is the test the L3 invariant suite simulates but can't actually prove
in a live environment.

1. Start a fresh `--apply` run.
2. As soon as the EB UI shows the campaign as `Paused`, **Ctrl-C the CLI**.
3. Observe the EB UI.

**Expected:** the `finally` clause in `reapply.py` runs the resume call
even on cancellation, so the campaign should return to `Queued`/`Active`
within a few seconds.

**Verify:**
- [ ] Campaign status returns to non-paused within ~10 seconds of Ctrl-C.

**If not:** the campaign is stuck paused. Manually resume via the EB UI or
the curl in step 4. **This is the FAILED_LEFT_PAUSED scenario in the wild.**
Document the behavior. v1 documentation must call this out as a known
failure mode requiring operator vigilance.

---

## 10. Time-gate edge cases

Worth exercising once even though L1 covers them in principle.

- [ ] Run during the campaign's active window (e.g. 14:00 local) — expect `skipped_time_gate` with reason "too early".
- [ ] Run after the campaign's `end_time` + buffer in its local timezone — expect either `skipped_dry_run` (with diff) or `skipped_no_diff`.
- [ ] Run on a Saturday (or whatever non-sending day the schedule has) — expect `skipped_time_gate` with reason mentioning the weekday.
- [ ] Run with `--skip-time-check` on a Saturday — expect the time gate to be bypassed and the orchestrator to proceed.

---

## 11. Capture & gate criteria

Before this tool is allowed to run against any client workspace:

- [ ] All sections 1–10 completed and captured in writing.
- [ ] Any deviations from the assumed JSON shapes documented and code updated to match.
- [ ] At least one successful `--apply` run on a Charm test campaign with `verify_passed: true`.
- [ ] Section 9 (Ctrl-C scenario) verified — either the resume-on-finally works as designed, OR the limitation is documented in operator-facing docs.
- [ ] No unresolved `FAILED_LEFT_PAUSED` runs.

When all of the above is true, the tool can be promoted to L6 (production
canary) — operator-driven runs against a real (small) workspace under
direct supervision.

---

## Appendix A — Setting up a throwaway test campaign

For sections 7–9, you need a dedicated low-risk test campaign with a known sender shape so the diff is deterministic. Recipe:

### Pick 5 sender accounts in the Charm workspace

Label them A, B, C, D, E (use real emails — these are existing senders, not new ones). Apply the following state via the EB UI:

| Sender | Attach to test campaign? | Apply `live` tag? |
|---|---|---|
| A | yes | yes |
| B | yes | yes |
| C | yes | **no** |
| D | no | yes |
| E | no | yes |

This gives:
- `prior_set = {A, B, C}` (currently attached to the campaign)
- `target_set = {A, B, D, E}` (have the `live` tag)
- Diff: **attach D and E**, **remove C** — 33% removal (passes the 50% guard)
- Final after reapply: `{A, B, D, E}` (matches target — verify-equality target)

This shape exercises both attach and remove in one run, with realistic but small numbers.

### EB UI walkthrough

1. **Apply tags** — *Email Accounts* tab → multi-select A, B, D, E → "Add tag" → `live`. Verify C does NOT have `live`.
2. **Create the test campaign** — *Campaigns* → new outbound campaign. Schedule M-F 8am-5pm in `Australia/Sydney` (validates Sammy/Sydney path live). Add a single trivial sequence step. **Add zero leads** if EB allows; otherwise add 1–2 dummy addresses you own (e.g. `eod-test+1@yourdomain.com`).
3. **Attach senders** — On the new campaign → *Sender Emails* tab → attach A, B, C only. Detach anything else.
4. **Confirm status** — Campaign should be `Active` or `Queued`. If it's stuck in `Draft`, EB requires at least one lead and one sequence step; check both.

### Sanity-verify with `check`

Before any `--apply`, run pre-flight:

```bash
eod-reapply check --workspace Charm --campaign-id <TEST_CAMPAIGN_ID>
```

You should see all checks `[ OK  ]` with `expected_diff` showing `would attach 2 [D_id, E_id], remove 1 [C_id] (33% of currently-attached)`. If the diff doesn't match the recipe, the EB UI state diverged from what you set — fix before proceeding.

### After staging is complete — clean up

- Detach all senders from the test campaign.
- Either archive the test campaign or rename it to `EOD-REAPPLY-TEST-DONE-YYYYMMDD` so it's clear it's not active.
- Decide whether to leave the `live` tags on D and E (they were already part of your normal pool) or remove the manual additions.

---

## Appendix B — Running staging via Docker (alternative to local install)

If you don't want to install Python locally on the host running staging, use the included Dockerfile.

```bash
# Build once on the host (or pull from your registry)
cd apps/eod-reapply
docker build -t eod-reapply:staging .

# Pre-flight check
docker run --rm \
  -e DATABASE_URL="$DATABASE_URL" \
  -e EMAILBISON_API_URL="$EMAILBISON_API_URL" \
  eod-reapply:staging check --workspace Charm --campaign-id <TEST_CAMPAIGN_ID>

# Dry-run reapply
docker run --rm \
  -e DATABASE_URL="$DATABASE_URL" \
  -e EMAILBISON_API_URL="$EMAILBISON_API_URL" \
  eod-reapply:staging reapply --workspace Charm --campaign-id <TEST_CAMPAIGN_ID> --skip-time-check

# Apply (only after dry-run + EB UI verification)
docker run --rm \
  -e DATABASE_URL="$DATABASE_URL" \
  -e EMAILBISON_API_URL="$EMAILBISON_API_URL" \
  eod-reapply:staging reapply --workspace Charm --campaign-id <TEST_CAMPAIGN_ID> --apply --skip-time-check
```

Same `eod-reapply` exit codes; same `--json-only` flag for log capture.

---

## Known v1 limitations (operator-facing)

- One campaign per invocation. To handle N campaigns, run N times.
- No DB-side idempotency (`last_run_local_date` is always None in v1). An
  operator who runs the tool twice in a row on the same campaign will
  attempt the reapply twice; the second run should be a `skipped_no_diff`
  if nothing changed in between, but it does pause/resume regardless.
  v2 (the scheduler) introduces persistent idempotency.
- No automatic recovery from FAILED_LEFT_PAUSED. Operator must verify in
  EB UI. Exit code 3 is the load-bearing signal for the future scheduler
  to alert.
- The `live` tag is hardcoded as the default; `--live-tag` overrides.
  Workspace tag mapping is the operator's responsibility.
- No rate-limit handling beyond what httpx provides. Repeated rapid
  invocations may hit EB's limits; back off manually.
