#!/usr/bin/env python3
"""
One-shot seed for client_hypertide_subscriptions (chs) per DECISION 1 + DECISION 5
of docs/plans/hypertide-data-model-and-change-tracking.md.

Reads a fresh HT snapshot, joins against existing clients + the
domains.hypertide_subscription_id backfill from migration 110, and either
prints a dry-run plan (default) or applies the inserts (--apply).

Dispatch rule (DECISION 5 revised 2026-05-18):
  - Sub already mapped via domains.hypertide_subscription_id -> bind to that client
  - Otherwise group unmapped subs by organizationName and create ONE new client per
    distinct org_name, with client_status set by sending_tool:
      Email Bison   -> 'client'
      Instantly.ai  -> 'client'
      Smartlead.ai  -> 'friends_and_family'
      other/missing -> 'friends_and_family' (safe default)

Idempotency:
  - chs INSERTs use ON CONFLICT (subscription_id) DO NOTHING, so re-runs skip
    already-bound subs.
  - New-client groups check chs for ANY of their sub_ids first; if any are
    already bound, the group is skipped entirely (operator must clean up).
  - --apply runs each new-client group as one CTE transaction (atomic per org).

Output:
  - dry-run: stdout summary + writes a CSV to docs/audits/
              2026-05-18-ht-seed-preview.csv
  - --apply: stdout per-group result + final counts

Usage:
  py scripts/seed_client_hypertide_subscriptions.py                  # dry-run
  py scripts/seed_client_hypertide_subscriptions.py --snapshot PATH  # use specific snapshot
  py scripts/seed_client_hypertide_subscriptions.py --apply          # write to prod
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

ADMIN_API = "https://api.wizardgrimoire.cloud/api/admin/run-sql"
ADMIN_KEY = "098c0ee5901b50d93b251d29e57bdd979f5aee899a3dd5d0b39c7935119e60aa"
SEED_DATE = "2026-05-18"

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SNAPSHOT = Path("d:/tmp/ht_snapshot_2026-05-18T21-37-28Z.json")
CSV_OUT = REPO_ROOT / "docs" / "audits" / f"{SEED_DATE}-ht-seed-preview.csv"


def run_sql(sql: str) -> dict:
    qs = urllib.parse.urlencode({"key": ADMIN_KEY, "sql": sql})
    req = urllib.request.Request(
        f"{ADMIN_API}?{qs}",
        method="POST",
        headers={"User-Agent": "curl/8.0.0", "Accept": "application/json"},
    )
    try:
        r = urllib.request.urlopen(req, timeout=120)
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="ignore")
        raise RuntimeError(f"admin API HTTP {e.code}: {body[:500]}") from e
    body = json.loads(r.read())
    if isinstance(body, dict) and "detail" in body:
        raise RuntimeError(f"admin API error: {body['detail']}")
    return body


def classify(sending_tool: str | None) -> str:
    if sending_tool in ("Email Bison", "Instantly.ai"):
        return "client"
    return "friends_and_family"


def sql_lit(value: str | None) -> str:
    """PostgreSQL string literal with single-quote escaping. NULL for None."""
    if value is None:
        return "NULL"
    escaped = value.replace("'", "''")
    return f"'{escaped}'"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT, help="HT snapshot JSON (default: latest in d:/tmp)")
    ap.add_argument("--apply", action="store_true", help="write to prod (default: dry-run)")
    args = ap.parse_args()

    # --- Load snapshot ---
    if not args.snapshot.exists():
        sys.exit(f"snapshot not found: {args.snapshot}")
    with args.snapshot.open() as f:
        snap = json.load(f)
    records = snap.get("active", []) + snap.get("pending", [])
    print(f"loaded snapshot: {args.snapshot} ({len(records)} records)")

    # --- Collapse HT records by subscription_id ---
    sub_meta: dict[str, dict] = {}
    sub_orgs: dict[str, set[str]] = defaultdict(set)
    sub_tools: dict[str, set[str]] = defaultdict(set)
    sub_created: dict[str, str] = {}  # earliest createdAt per sub
    for r in records:
        sid = r.get("subscriptionId")
        if not sid:
            continue
        sub_meta[sid] = r
        if r.get("organizationName"):
            sub_orgs[sid].add(r["organizationName"].strip())
        if r.get("sendingTool"):
            sub_tools[sid].add(r["sendingTool"])
        ca = r.get("createdAt")
        if ca and (sid not in sub_created or ca < sub_created[sid]):
            sub_created[sid] = ca
    print(f"unique subscriptions: {len(sub_meta)}")

    # --- Fetch DB state via admin API ---
    print("fetching DB state ...")
    clients_rows = run_sql("SELECT id, name FROM clients ORDER BY name")["result"]
    existing_clients = {c["name"]: c["id"] for c in clients_rows}
    print(f"  existing clients: {len(existing_clients)}")

    # Already-bound subs from migration 110 backfill on domains
    domain_sub_rows = run_sql(
        "SELECT DISTINCT d.hypertide_subscription_id AS sub, w.client_id AS cid "
        "FROM domains d JOIN workspaces w ON w.id = d.workspace_id "
        "WHERE d.hypertide_subscription_id IS NOT NULL AND w.client_id IS NOT NULL"
    )["result"]
    sub_to_client = {r["sub"]: r["cid"] for r in domain_sub_rows}

    # Already-seeded chs rows (idempotency check)
    existing_chs_rows = run_sql("SELECT subscription_id FROM client_hypertide_subscriptions")["result"]
    existing_chs = {r["subscription_id"] for r in existing_chs_rows}
    print(f"  existing chs rows: {len(existing_chs)} (these will be skipped via ON CONFLICT)")

    # --- Bucket subs ---
    bind_existing: list[tuple[str, str]] = []  # (sub_id, client_id)
    org_to_subs: dict[str, list[str]] = defaultdict(list)
    skip_already_seeded: list[str] = []
    for sid in sub_meta:
        if sid in existing_chs:
            skip_already_seeded.append(sid)
            continue
        if sid in sub_to_client:
            bind_existing.append((sid, sub_to_client[sid]))
        else:
            org = next(iter(sub_orgs[sid]), None) or "(no org)"
            org_to_subs[org].append(sid)

    # New-client groups: collapse by org_name; classification by sending_tool
    # (use first sub's tool; flag if mixed)
    new_client_groups = []  # list of dicts: org, classification, sending_tool, sub_ids
    for org, subs in sorted(org_to_subs.items()):
        tools = {next(iter(sub_tools[s]), None) for s in subs}
        tools.discard(None)
        # classification: if ANY tool is Email Bison or Instantly.ai -> client; else F&F
        if tools & {"Email Bison", "Instantly.ai"}:
            classification = "client"
        else:
            classification = "friends_and_family"
        primary_tool = sorted(tools)[0] if tools else None
        new_client_groups.append({
            "org": org,
            "classification": classification,
            "sending_tools": sorted(tools),
            "sub_ids": subs,
            "primary_tool": primary_tool,
        })

    # --- Summary ---
    n_new_clients_eb_inst = sum(1 for g in new_client_groups if g["classification"] == "client")
    n_new_fnf = sum(1 for g in new_client_groups if g["classification"] == "friends_and_family")
    n_new_chs_from_groups = sum(len(g["sub_ids"]) for g in new_client_groups)
    print()
    print("=== dispatch summary ===")
    print(f"  already-seeded subs (skipped):              {len(skip_already_seeded)}")
    print(f"  chs INSERT bind-to-existing-client:         {len(bind_existing)}")
    print(f"  new clients (EB or Instantly -> 'client'):  {n_new_clients_eb_inst}")
    print(f"  new clients (Smartlead/other -> F&F):       {n_new_fnf}")
    print(f"  new chs INSERTs from new-client groups:     {n_new_chs_from_groups}")
    print(f"  TOTAL chs rows after seed (if fresh):       {len(bind_existing) + n_new_chs_from_groups + len(skip_already_seeded)}")
    print()

    # --- Write dry-run CSV ---
    CSV_OUT.parent.mkdir(parents=True, exist_ok=True)
    with CSV_OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "action", "subscription_id", "subscription_created_at",
            "organization_name", "sending_tool",
            "target_client_name", "target_client_status", "notes",
        ])
        # Bind to existing
        existing_id_to_name = {c["id"]: c["name"] for c in clients_rows}
        for sid, cid in sorted(bind_existing):
            r = sub_meta[sid]
            w.writerow([
                "bind_existing", sid, sub_created.get(sid, ""),
                r.get("organizationName") or "",
                next(iter(sub_tools[sid]), "") or "",
                existing_id_to_name.get(cid, "?"),
                "(unchanged)",
                f"seeded {SEED_DATE}, sending_tool={next(iter(sub_tools[sid]), '') or ''}",
            ])
        # New client groups
        for g in new_client_groups:
            for sid in g["sub_ids"]:
                r = sub_meta[sid]
                w.writerow([
                    f"new_{g['classification']}", sid, sub_created.get(sid, ""),
                    r.get("organizationName") or "",
                    g["primary_tool"] or "",
                    g["org"],  # new client name == org name
                    g["classification"],
                    f"seeded {SEED_DATE}, sending_tool={g['primary_tool'] or 'unknown'}"
                    + (f", multi_tool={g['sending_tools']}" if len(g["sending_tools"]) > 1 else ""),
                ])
        # Already-seeded (informational)
        for sid in sorted(skip_already_seeded):
            w.writerow(["skip_already_seeded", sid, "", "", "", "", "", ""])
    print(f"wrote preview CSV: {CSV_OUT}")

    if not args.apply:
        print()
        print("DRY-RUN ONLY — no DB writes. Re-run with --apply to seed.")
        return 0

    # --- Apply phase ---
    print()
    print("=== APPLYING SEED ===")
    notes_prefix = f"seeded {SEED_DATE}"

    # Phase 1: bind-to-existing chs INSERTs (batched into one statement)
    if bind_existing:
        values = []
        for sid, cid in bind_existing:
            r = sub_meta[sid]
            tool = next(iter(sub_tools[sid]), "") or ""
            ca = sub_created.get(sid)
            org = r.get("organizationName") or ""
            note = f"{notes_prefix}, sending_tool={tool}"
            ca_lit = f"'{ca}'::date" if ca else "NULL"
            values.append(f"({sql_lit(sid)}, '{cid}'::uuid, {ca_lit}, {sql_lit(org)}, {sql_lit(note)})")
        # Chunk into batches of 100 to keep URL size sane
        BATCH = 100
        applied = 0
        for i in range(0, len(values), BATCH):
            chunk = values[i:i + BATCH]
            sql = (
                "INSERT INTO client_hypertide_subscriptions "
                "(subscription_id, client_id, subscription_created_at, organization_name, notes) VALUES "
                + ", ".join(chunk)
                + " ON CONFLICT (subscription_id) DO NOTHING;"
            )
            res = run_sql(sql)
            print(f"  bind_existing batch {i//BATCH + 1}: {res['result']} ({len(chunk)} rows attempted)")
            applied += len(chunk)
        print(f"  bind_existing total attempted: {applied}")

    # Phase 2: new-client groups (one CTE transaction per org_name)
    for g in new_client_groups:
        org = g["org"]
        classification = g["classification"]
        primary_tool = g["primary_tool"]
        # Idempotency: skip group if any of its subs already have a chs row
        sub_list = ",".join(sql_lit(s) for s in g["sub_ids"])
        check = run_sql(
            f"SELECT subscription_id FROM client_hypertide_subscriptions WHERE subscription_id IN ({sub_list})"
        )["result"]
        if check:
            print(f"  SKIP group {org!r}: {len(check)} of {len(g['sub_ids'])} subs already bound")
            continue
        # Build CTE: insert new client, then insert chs rows for all its subs
        chs_values = []
        for sid in g["sub_ids"]:
            r = sub_meta[sid]
            ca = sub_created.get(sid)
            tool = next(iter(sub_tools[sid]), "") or primary_tool or ""
            ca_lit = f"'{ca}'::date" if ca else "NULL"
            note = f"{notes_prefix}, sending_tool={tool}"
            chs_values.append(
                f"({sql_lit(sid)}, (SELECT id FROM new_client), {ca_lit}, {sql_lit(org)}, {sql_lit(note)})"
            )
        sql = (
            "WITH new_client AS ("
            f"  INSERT INTO clients (name, client_status, primary_hypertide_organization_name) "
            f"  VALUES ({sql_lit(org)}, {sql_lit(classification)}, {sql_lit(org)}) RETURNING id"
            ") "
            "INSERT INTO client_hypertide_subscriptions "
            "(subscription_id, client_id, subscription_created_at, organization_name, notes) VALUES "
            + ", ".join(chs_values)
            + " ON CONFLICT (subscription_id) DO NOTHING;"
        )
        res = run_sql(sql)
        print(f"  NEW client {org!r} ({classification}) + {len(g['sub_ids'])} chs: {res['result']}")

    # Final verification
    print()
    print("=== POST-APPLY VERIFICATION ===")
    counts = run_sql(
        "SELECT (SELECT COUNT(*) FROM clients) AS clients, "
        "(SELECT COUNT(*) FROM client_hypertide_subscriptions) AS chs, "
        "(SELECT COUNT(*) FROM clients WHERE client_status='client') AS client_status_client, "
        "(SELECT COUNT(*) FROM clients WHERE client_status='friends_and_family') AS client_status_fnf, "
        "(SELECT COUNT(*) FROM v_operational_clients) AS v_operational_clients"
    )["result"][0]
    for k, v in counts.items():
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
