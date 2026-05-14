#!/usr/bin/env python3
"""
Fleet-wide tag audit: compare DB authority vs EB tag state for all
active workspaces.

Read-only. Reports tag mismatches by category, per workspace and rolled
up across the fleet.

Invariants checked (post-2026-04-27 overhaul, updated ADR-007 2026-04-29):

    DB inventory_pool_status='deployed'   →  EB has 'live', no 'reserve'
    DB inventory_pool_status='reserve'    →  EB has 'reserve', no 'live'
    DB inventory_pool_status=NULL         →  EB has neither
    DB inventory_lifecycle_status='active'→  EB has no 'incubating'
    DB inventory_lifecycle_status='incubating' → EB has 'incubating'

ESP-specific:
    Microsoft → always 'live' (per CEO pin), never 'reserve'

Note: 'warning' and 'quarantined' pool states were removed per ADR-007.
Migration 098 drains existing rows; if this audit finds any, the
migration didn't fully apply.
"""
import json
import os
import sys
import time
from collections import Counter, defaultdict

import requests

ADMIN_API = "https://api.wizardgrimoire.cloud/api/admin/run-sql"
ADMIN_KEY = "098c0ee5901b50d93b251d29e57bdd979f5aee899a3dd5d0b39c7935119e60aa"
EB_BASE_URL = os.environ.get("EMAILBISON_API_URL", "https://spellcast.hirecharm.com").rstrip("/")
# Support both EMAILBISON_API_URL=base and =base/api forms
if not EB_BASE_URL.endswith("/api"):
    EB_BASE_URL = EB_BASE_URL + "/api"

POOL_TAGS = {"live", "reserve"}
LIFECYCLE_TAGS = {"incubating"}
KILL_TAG_PREFIX = "flagged_"


def run_sql(sql):
    r = requests.post(ADMIN_API, params={"key": ADMIN_KEY, "sql": sql}, timeout=60)
    if r.status_code != 200:
        print(f"  SQL ERROR: {r.status_code} - {r.text[:300]}")
        return []
    data = r.json()
    return data.get("result", [])


def fetch_eb_accounts(api_key, workspace_name):
    """Page through /sender-emails using the workspace-scoped key."""
    accounts = []
    page = 1
    consecutive_empty = 0
    while True:
        r = requests.get(
            f"{EB_BASE_URL}/sender-emails",
            params={"page": page, "per_page": 100},
            headers={
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
            },
            timeout=60,
        )
        if r.status_code != 200:
            print(f"  [{workspace_name}] EB error page {page}: {r.status_code} {r.text[:200]}")
            break
        body = r.json()
        if isinstance(body, list):
            accounts.extend(body)
            break
        chunk = body.get("data", [])
        meta = body.get("meta", {})
        last_page = meta.get("last_page")
        if chunk:
            accounts.extend(chunk)
            consecutive_empty = 0
        else:
            consecutive_empty += 1
            if consecutive_empty >= 3:
                break
        if last_page is not None and page >= last_page:
            break
        page += 1
    return accounts


def categorize(db_row, eb_tags_list):
    """Return list of issue codes for this inbox.

    Skips tag-drift checks for disconnected inboxes — pool membership
    and connection status are orthogonal axes (the inbox keeps its
    pool_status across disconnects so it can resume role on reconnect),
    and `set_tag_sync` deliberately doesn't push tag changes to
    disconnected inboxes (line 467 of set_tag_sync.py: "we cannot tag
    them in EB"). Reporting those as drift produces unactionable noise.

    Returns a single-element list ['_disconnected_skip'] for connection-
    health bucketing; caller routes those to a separate summary.
    """
    conn_status = db_row.get("conn_status")
    if conn_status != "Connected":
        return ["_disconnected_skip"]

    issues = []
    tags = set(eb_tags_list)
    pool = db_row["inventory_pool_status"]
    lifecycle = db_row["inventory_lifecycle_status"]
    esp = db_row.get("esp")
    domain_pool = db_row.get("domain_pool")

    has_live = "live" in tags
    has_reserve = "reserve" in tags
    has_incubating = "incubating" in tags

    # Pool-tag invariants
    if pool == "live":
        if not has_live:
            issues.append("missing_live_tag")
        if has_reserve:
            issues.append("dual_pool_tag_deployed_plus_reserve")
    elif pool == "reserve":
        if not has_reserve:
            issues.append("missing_reserve_tag")
        if has_live:
            issues.append("dual_pool_tag_reserve_plus_live")
    elif pool in ("warning", "quarantined"):
        # Pre-ADR-007 states; migration 098 should have drained these.
        # If we still see them, flag as state drift.
        issues.append(f"legacy_pool_state_{pool}_after_migration_098")
        if has_live or has_reserve:
            issues.append(f"pool_{pool}_should_have_no_pool_tag")
    elif pool is None:
        if has_live or has_reserve:
            issues.append("null_pool_but_has_pool_tag")

    # Lifecycle-tag invariants
    if lifecycle == "active" and has_incubating:
        issues.append("active_lifecycle_still_has_incubating_tag")
    if lifecycle == "incubating" and not has_incubating:
        issues.append("incubating_lifecycle_missing_incubating_tag")

    # ESP-specific
    if esp == "microsoft":
        if has_reserve:
            issues.append("microsoft_should_never_have_reserve")

    # Burned/cancelled domain
    if domain_pool in ("burned", "cancelled") and (has_live or has_reserve):
        issues.append(f"{domain_pool}_domain_still_has_pool_tag")

    return issues


def main():
    print("=" * 80)
    print("FLEET-WIDE TAG AUDIT — DB authority vs EB tag state")
    print("=" * 80)

    workspaces = run_sql("""
        SELECT w.id::text AS id, w.workspace_name, w.emailbison_workspace_id, k.key_token
        FROM workspaces w
        JOIN workspace_api_keys k ON k.workspace_id = w.id AND k.is_active = TRUE
        WHERE w.is_active = TRUE
        ORDER BY w.workspace_name
    """)
    print(f"\nActive workspaces with keys: {len(workspaces)}\n")

    fleet_summary = Counter()
    per_workspace_summary = []
    all_mismatches = []

    for ws in workspaces:
        ws_name = ws["workspace_name"]
        ws_id = ws["id"]
        api_key = ws["key_token"]

        print(f"--- [{ws_name}] (eb_ws={ws['emailbison_workspace_id']}) ---")

        # DB state for this workspace
        db_rows = run_sql(f"""
            SELECT
                sa.id::text AS id,
                sa.email_address,
                sa.emailbison_account_id,
                sa.esp,
                sa.inventory_pool_status,
                sa.inventory_lifecycle_status,
                sa.is_active,
                sa.inbox_state,
                sa.status AS conn_status,
                d.pool_status AS domain_pool,
                d.domain_name
            FROM sender_accounts sa
            JOIN domains d ON d.id = sa.domain_id
            WHERE sa.workspace_id = '{ws_id}'
              AND sa.is_active = TRUE
              AND sa.inbox_state = 'live'
              AND sa.emailbison_account_id IS NOT NULL
        """)
        db_by_eb_id = {int(r["emailbison_account_id"]): r for r in db_rows if r["emailbison_account_id"]}
        print(f"  DB: {len(db_by_eb_id)} active+live inboxes")

        # EB state
        try:
            eb_accounts = fetch_eb_accounts(api_key, ws_name)
        except Exception as e:
            print(f"  EB fetch failed: {e}")
            continue
        print(f"  EB: {len(eb_accounts)} sender accounts returned")

        ws_issues = Counter()
        ws_mismatches = []

        eb_ids_seen = set()
        for eb_acc in eb_accounts:
            eb_id = eb_acc.get("id")
            if eb_id is None:
                continue
            eb_ids_seen.add(eb_id)
            tags = [t.get("name") for t in (eb_acc.get("tags") or []) if t.get("name")]
            db_row = db_by_eb_id.get(eb_id)
            if db_row is None:
                ws_issues["eb_only_no_db_record"] += 1
                continue

            issues = categorize(db_row, tags)

            # Disconnected inboxes are bucketed separately as connection-
            # health info, not drift. set_tag_sync deliberately skips
            # them; pool membership stays valid across disconnects so the
            # inbox can resume role on reconnect (EB triggers reconnect
            # automatically).
            if issues == ["_disconnected_skip"]:
                pool_label = db_row["inventory_pool_status"] or "null"
                ws_issues[f"_disconnected_{pool_label}"] += 1
                fleet_summary[f"_disconnected_{pool_label}"] += 1
                continue

            for code in issues:
                ws_issues[code] += 1
                fleet_summary[code] += 1
            if issues:
                ws_mismatches.append({
                    "email": db_row["email_address"],
                    "eb_id": eb_id,
                    "esp": db_row["esp"],
                    "pool": db_row["inventory_pool_status"],
                    "lifecycle": db_row["inventory_lifecycle_status"],
                    "domain_pool": db_row["domain_pool"],
                    "tags": sorted(tags),
                    "issues": issues,
                })

        # DB rows that were active+live but EB didn't return them
        db_only = set(db_by_eb_id.keys()) - eb_ids_seen
        if db_only:
            ws_issues["db_only_no_eb_record"] = len(db_only)
            fleet_summary["db_only_no_eb_record"] += len(db_only)

        per_workspace_summary.append({
            "workspace": ws_name,
            "db_count": len(db_by_eb_id),
            "eb_count": len(eb_accounts),
            "issues": dict(ws_issues),
        })
        all_mismatches.extend([{**m, "workspace": ws_name} for m in ws_mismatches])

        if ws_issues:
            print(f"  ISSUES: {dict(ws_issues)}")
        else:
            print("  CLEAN ✓")
        time.sleep(0.5)  # be polite to EB

    # Final report
    print("\n" + "=" * 80)
    print("PER-WORKSPACE SUMMARY")
    print("=" * 80)
    for w in per_workspace_summary:
        print(f"\n{w['workspace']:30s} db={w['db_count']:5d}  eb={w['eb_count']:5d}")
        for code, n in sorted(w["issues"].items(), key=lambda x: -x[1]):
            print(f"    {code:50s} {n}")

    # Split the fleet summary into real drift vs connection-health info.
    # Connection health is bucketed under codes starting with "_disconnected_"
    # — these are NOT tag drift, they're just inboxes EB can't reach right
    # now. set_tag_sync correctly skips them; pool membership is preserved
    # for resume-on-reconnect.
    drift_summary = {k: v for k, v in fleet_summary.items() if not k.startswith("_disconnected_")}
    conn_summary = {k: v for k, v in fleet_summary.items() if k.startswith("_disconnected_")}

    print("\n" + "=" * 80)
    print("FLEET TAG DRIFT (Connected inboxes only — actionable)")
    print("=" * 80)
    if not drift_summary:
        print("  CLEAN — no tag drift on connected inboxes ✓")
    else:
        for code, n in sorted(drift_summary.items(), key=lambda x: -x[1]):
            print(f"  {code:55s} {n}")

    print("\n" + "=" * 80)
    print("CONNECTION HEALTH (informational — disconnected inboxes by pool)")
    print("=" * 80)
    if not conn_summary:
        print("  All inboxes Connected ✓")
    else:
        for code, n in sorted(conn_summary.items(), key=lambda x: -x[1]):
            label = code.replace("_disconnected_", "disconnected pool=")
            print(f"  {label:55s} {n}")
        print("  (these inboxes will resume role on reconnect — EB triggers")
        print("   reconnect automatically; investigate only if persistent)")

    # Sample 10 mismatches per category to disk for review
    out_path = "scripts/backfill_snapshots/2026-04-28_tag_audit_results.json"
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    samples_by_code = defaultdict(list)
    for m in all_mismatches:
        for code in m["issues"]:
            if len(samples_by_code[code]) < 10:
                samples_by_code[code].append(m)
    with open(out_path, "w") as f:
        json.dump({
            "fleet_summary": dict(fleet_summary),
            "per_workspace": per_workspace_summary,
            "samples_by_code": {k: v for k, v in samples_by_code.items()},
            "all_mismatches_count": len(all_mismatches),
        }, f, indent=2, default=str)
    print(f"\nFull samples written to {out_path}")


if __name__ == "__main__":
    main()
