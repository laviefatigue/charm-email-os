# L5 Staging Results — Test-Campaign 271 (Charm workspace)

Status: **ATTACH path validated end-to-end against production EB. Two latent bugs discovered + fixed mid-staging. REMOVE path still pending operator action.**

Date: 2026-05-13

---

## Setup

- **Workspace**: Charm (production EB workspace at `https://spellcast.hirecharm.com/api`)
- **Campaign**: `Test-Campaign`, EB id `271`, DB UUID `a1c5a16e-57d1-4818-83e4-fa65abde4bd5`
- **Leads**: 5 fake leads from `sample-contacts.csv` (Marvel-character emails). Operator action: archive the campaign before the next morning's send window to prevent sends.
- **Tag under test**: `live` (tag id `341` in Charm workspace)
- **Auth**: workspace-scoped EB key via `workspace_api_keys` per ADR-006.

Staging script lived at `d:\tmp\eod_reapply_test271.py` — a hand-rolled imitation of `apps/eod-reapply/src/eod_reapply/reapply.py` orchestration that paginated correctly and gated mutations behind the same pause/finally-resume invariants.

---

## What was validated

1. ✅ Workspace-scoped EB key resolves via `workspace_api_keys.key_token` for `Charm`.
2. ✅ Campaign 271 reachable via `GET /api/campaigns/271`. Status transitions observed: `active` → `paused` (after PATCH `/pause`) → `queued` (after PATCH `/resume`).
3. ✅ Campaign-attached set fetched via paginated `GET /api/campaigns/271/sender-emails`.
4. ✅ Pause-before-mutate + resume-in-finally invariant held across all runs.
5. ✅ Attach via `POST /api/campaigns/271/attach-sender-emails`.
6. ✅ Detach via `DELETE /api/campaigns/271/remove-sender-emails` (with body — non-standard but works).
7. ✅ Final state `attached == target` (set equality, 280 == 280) — verified after settle wait.

---

## Bugs discovered during staging

### Bug 1 — EB silently ignores `filters[tag_ids][]` filter shape

**Symptom**: First reapply attached **437** senders to Test-Campaign 271 when only **280** carry the `live` tag (per EB UI screenshot: "280 email accounts selected").

**Root cause**: The hand-rolled staging script used `GET /api/sender-emails?filters[tag_ids][]=<id>`. EB returns `200 OK` and the entire workspace (437 rows) regardless of the tag id, silently ignoring the filter param.

**Probe results** (all queries returned `meta.total = 437`, the workspace total):

| Filter shape | meta.total |
|---|---|
| `filters[tag_ids][]=341` | 437 ❌ |
| `filters[tag_id]=341` | 437 ❌ |
| `filter[tag_ids][]=341` | 437 ❌ |
| `tag_ids[]=341` | **280 ✅** |
| `tag_ids[0]=341` | **280 ✅** (canonical) |
| `tag_id=341` | 437 ❌ |
| `tags[]=341` | 437 ❌ |
| `filters[tags][]=341` | 437 ❌ |
| `with_tag=341` | 437 ❌ |
| (no filter, baseline) | 437 |

Only top-level `tag_ids[N]=...` (no `filters[]` wrapper) is honored.

**Verification**: each row in a honored response carries the requested tag in its `tags[]` array. Spot-checked `chrisbb@usehirecharm.com` (eb_id 5560), one of the over-attached senders: actual tags `[Outlook, flagged_disconnected_timeout, OLD]` — no `live` tag. So the "filter" was clearly never applied during the buggy run.

**Fix shipped** (`apps/eod-reapply/src/eod_reapply/eb_client.py:list_senders_with_tag`):
1. The CLI was already using the correct `tag_ids[0]=` shape — production tool was never broken; only the hand-rolled staging script was wrong.
2. Defense-in-depth guard added: after fetch, assert every returned sender carries the requested tag in `tags[]`. If any doesn't, raise `EmailBisonAPIError("the tag filter was silently ignored by EB")`. Test: `test_filter_silently_ignored_raises` in `tests/test_eb_client.py`.

**Doc updates**: `apps/eod-reapply/docs/eb-api-deep-dive.md` §2.6 + `docs/plans/eod-campaign-reapply.md` L372 + L496.

---

### Bug 2 — `/remove-sender-emails` is async; immediate verify can false-negative

**Symptom**: After detaching 157 over-attached senders from Test-Campaign 271 (revert run), the immediate verify reported `attached == 280` (matching the expected count) but the **membership** differed — 20+ ids on each side of the symmetric diff. After re-fetching 15 seconds later, the sets agreed exactly.

**Root cause**: EB's response message for the DELETE call is `"Sender emails sent for deletion. This may take a moment."` — the deletion is async. A single immediate verify catches an intermediate state.

**Fix shipped** (`apps/eod-reapply/src/eod_reapply/reapply.py:reapply_campaign`):
- Replaced single-shot verify with a retry-with-settle-wait loop.
- New parameters: `verify_settle_attempts: int = 4`, `verify_settle_seconds: float = 5.0`.
- Loop exits early on convergence (no sleep on first-try success).
- Only escalates to `FAILED_POST_RESUME` if mismatch persists across all attempts.
- Resume still always attempted in `finally`.
- Tests: `test_verify_settle_converges_on_retry`, `test_verify_settle_succeeds_first_try_no_sleep` in `tests/test_reapply.py`.

**Sleep injection**: `sleep_func` parameter for tests; defaults to `asyncio.sleep`.

**Doc updates**: `apps/eod-reapply/docs/eb-api-deep-dive.md` §2.8 ("Mitigation shipped in v1").

---

## Sequence — revert run after Bug 1 detection

Test-Campaign 271 state before revert: 437 senders attached (over-attached by 157). Target = 280 (correct live-tagged set, confirmed against EB UI).

```
[15:04:38] --- REVERT over-attach on campaign 271 ---
[15:04:39] campaign status: active
[15:04:59] step 1: attached count: 437
[15:05:13] step 2: target count: 280
[15:05:13]   to detach: 157
[15:05:13] step 3: PATCH /campaigns/271/pause → paused
[15:05:16] step 4 (batch 1): DELETE 100 senders
[15:05:16] step 4 (batch 2): DELETE 57 senders
[15:05:30] step 5: verify final == target
[15:05:30]   final attached count: 280  (count match)
[15:05:30]   VERIFY: FAIL  (set membership mismatch — async-delete race)
[15:05:30] step 6 (finally): PATCH /campaigns/271/resume → queued

[15:05:45] re-check after 15s settle
[15:05:45]   attached count: 280
[15:05:45]   target count:   280
[15:05:45]   match:          True ✅
```

The false-negative VERIFY at 15:05:30 is what motivated Bug 2's fix.

---

## Validation coverage

| Path | Status | How |
|---|---|---|
| ATTACH | ✅ Validated | Test-Campaign 271 went from 0 attached to 437 (buggy reapply) then 280 (corrected) — both happy-path attaches against prod EB. |
| Pause/resume | ✅ Validated | Two complete pause→mutate→resume cycles; status transitions confirmed. |
| Pagination | ✅ Validated | Multi-page fetches of both target set (280, 3 pages) and prior set (437→280, 5→3 pages). |
| Workspace-scoped key | ✅ Validated | `workspace_api_keys.key_token` lookup → EB requests succeeded scope-correctly. |
| REMOVE | ⚠️ Partial | Detach path exercised by the revert (157 detached). Not yet exercised by a "real" reapply (operator-driven flagged-tag flow). Awaits operator action. |
| No-diff fast path | ⏳ Pending | Re-run CLI against Test-Campaign 271 in current state — expect `SKIPPED_NO_DIFF` since attached==target. |
| Filter-honored guard | ✅ Tested | Unit test mocks a row with the wrong tag; orchestrator raises `EmailBisonAPIError`. |
| Settle-wait loop | ✅ Tested | Unit test scripts a 2-attempt convergence; verifies single sleep was incurred and final status is `SUCCEEDED`. |

---

## Open items

1. ~~**Operator: archive Test-Campaign 271 in EB UI**~~ — ✅ **Done** (verified 2026-05-13 via `GET /campaigns?per_page=200`; status `archived`). No leads will be contacted.

2. **REMOVE path validation**: pending. Operator strips the `live` tag from one currently-attached sender; re-run reapply against a fresh active test campaign; expect that sender to be removed. **Blocked**: no active Charm campaign currently exists for re-validation (all 15 charm campaigns in workspace are `draft` or `archived`). Either operator launches a new Test-Campaign or we accept the unit-test coverage as sufficient for REMOVE.

3. **L5 production-code-path smoke through the deployed CLI**: ran via `d:\tmp\eod_real_cli_test271.py` (thin driver that calls the production `reapply_campaign()` orchestrator directly with EB key from admin-SQL endpoint). Result: orchestrator correctly returned `failed_pre_pause` with `error_step=get_campaign` and `error=GET /api/campaigns/271 returned 404` — fail-closed behavior on archived campaign, **no mutation attempted**. ✅ This is a valid passing case for "what does the tool do when given a non-active campaign id" — the orchestrator's first-step guard works.

4. **L5 full active-flow smoke**: blocked by no active campaign in workspace. Options: (a) operator launches a fresh test campaign with the live tag; (b) accept the existing coverage (unit tests at L2 + the ATTACH happy path validated by the revert run + the no-active-campaign code-path validated by the post-archive run).

---

## What this exercise taught us

1. **"It accepts your request" ≠ "it honored your request."** EB returns `200 OK` with a wrong-but-plausible payload for unknown filter params. The defense is a per-response semantic check that the response matches the intent (every row carries the filter tag), not a contract test against a frozen mock.

2. **`200` on async endpoints is a promise, not a fact.** When EB says "this may take a moment", verify must be retried, not assumed. The L1/L2 mocks all return synchronous state — only L5 against prod uncovered this.

3. **Hand-rolled probe scripts ≠ production code.** The CLI uses the right filter. The reason the bug surfaced is that I rewrote the orchestration in `d:\tmp\eod_reapply_test271.py` to work around a missing DB tunnel. Cost: 157 over-attached senders + a revert run. Going forward, drive L5 through the actual CLI binary (even if it means setting up a DB tunnel or container exec path) rather than reproducing logic.
