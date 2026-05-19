---
title: HT Seed — Post-Seed Variant Merge Candidates
created: 2026-05-18
status: applied (merges 1-3 done 2026-05-18; item 4 deferred to operator)
tags: [hypertide, seed, merge, operator-action]
---

# HT Seed — Post-Seed Variant Merge Candidates

**Applied state (2026-05-18):** all 4 merges + all operator reviews done.

| Step | Result |
|---|---|
| Merge 1: Ink'd family (4 → 1) | Ink'd now has 11 chs subs |
| Merge 2: Root Access dupe | Root Access now has 12 chs subs |
| Merge 3: Sammy + Sammy AI | Sammy now has 19 chs subs |
| Merge 4: Stone Products Unlimited → SPUI | SPUI now has 4 chs subs (operator confirmed same customer) |
| Operator review: 397 Digital + Bridge | flipped to `friends_and_family` (not real customers) |
| Operator review: Estrada / EventPanda / Neon / Test Workspace | flipped to `client_status='inactive'` (no current HT activity) |

**Final production counts**: 53 clients (21 `'client'` + 28 `'friends_and_family'` + 4 `'inactive'`); 211 chs rows; `v_operational_clients`=21 / `v_operational_workspaces`=15 / `v_operational_domains`=673.

⚠️ The 39 domains under the 4 inactive clients are now excluded from `v_operational_*`. No operational impact until step 6 (read-path migration) lands, but reads that flip to the views post-step-6 will skip them — confirm Estrada/EventPanda/Neon really should be hidden from ops (Test Workspace clearly should).

The 2026-05-18 seed of `client_hypertide_subscriptions` (per migration 123 + 124, scripted in [scripts/seed_client_hypertide_subscriptions.py](../../scripts/seed_client_hypertide_subscriptions.py)) deliberately **did not fuzzy-match** organization names. That avoided the failure mode where a wrong auto-merge silently buries a real new customer under an existing client. Result: a small number of duplicated client rows by design, listed below for one operator-driven cleanup pass.

## What "merge" means here

Each merge re-points `client_hypertide_subscriptions.client_id` from the new (seeded) client row to the existing canonical client row, then deletes the empty new row. No `chs` data is lost — only the redundant `clients` row goes away.

Effect on counts after all merges below: 61 clients → **55 clients** (4 Ink'd variants + 1 Sammy dupe + 1 Sammy AI + 1 Root Access dupe = -7; `Stone Products Unlimited → SPUI` is operator-discretion = -0 or -1).

## Merge candidates

### 1. Ink'd family (4 → 1)

Existing canonical: `Ink'd` (id `e066df27-030e-442a-9865-0febc9b4af24`, 0 chs rows — never had any HT binding because all its subs are Instantly-only and HT spells it "Inkd" without the apostrophe).

| Merge source (seeded) | id | chs subs |
|---|---|---|
| `Inkd` | `75e02ff7-cce0-4a30-96e6-93b5187b1017` | 6 |
| `Inkd Instance` | `cefe6652-4426-4183-bdd2-d70a3d9215d3` | 1 |
| `Inkd Stores` | `2e660030-760c-49a7-9eba-42dcdf277d52` | 3 |
| `Inkd Virtualization` | `8f44e633-5f97-4335-bab0-4824e8fa58b7` | 1 |

```sql
BEGIN;
UPDATE client_hypertide_subscriptions
SET client_id = 'e066df27-030e-442a-9865-0febc9b4af24'
WHERE client_id IN (
    '75e02ff7-cce0-4a30-96e6-93b5187b1017',
    'cefe6652-4426-4183-bdd2-d70a3d9215d3',
    '2e660030-760c-49a7-9eba-42dcdf277d52',
    '8f44e633-5f97-4335-bab0-4824e8fa58b7'
);
DELETE FROM clients WHERE id IN (
    '75e02ff7-cce0-4a30-96e6-93b5187b1017',
    'cefe6652-4426-4183-bdd2-d70a3d9215d3',
    '2e660030-760c-49a7-9eba-42dcdf277d52',
    '8f44e633-5f97-4335-bab0-4824e8fa58b7'
);
COMMIT;
```

### 2. Root Access duplicate (2 → 1)

Existing canonical: `Root Access` (id `5a03c3fc-35f7-4927-a978-a49f5675048e`, 7 chs subs across EB + Smartlead).

| Merge source (seeded) | id | chs subs |
|---|---|---|
| `Root Access` (new) | `1f75c329-5f10-4a6d-9577-e1b0466ac75e` | 5 (Instantly) |

```sql
BEGIN;
UPDATE client_hypertide_subscriptions
SET client_id = '5a03c3fc-35f7-4927-a978-a49f5675048e'
WHERE client_id = '1f75c329-5f10-4a6d-9577-e1b0466ac75e';
DELETE FROM clients WHERE id = '1f75c329-5f10-4a6d-9577-e1b0466ac75e';
COMMIT;
```

### 3. Sammy duplicate + Sammy AI (3 → 1)

Existing canonical: `Sammy` (id `4ac7f374-8751-4d89-8017-7dfca23fb5f8`, 15 chs subs across EB + Instantly).

| Merge source (seeded) | id | chs subs |
|---|---|---|
| `Sammy` (new) | `dc97a008-6fa8-4bcc-b458-e9cffad81cab` | 3 (Instantly) |
| `Sammy AI` | `b2ada37a-d4c4-4d1c-a5c4-00ba1d36faad` | 1 (Instantly) |

```sql
BEGIN;
UPDATE client_hypertide_subscriptions
SET client_id = '4ac7f374-8751-4d89-8017-7dfca23fb5f8'
WHERE client_id IN (
    'dc97a008-6fa8-4bcc-b458-e9cffad81cab',
    'b2ada37a-d4c4-4d1c-a5c4-00ba1d36faad'
);
DELETE FROM clients WHERE id IN (
    'dc97a008-6fa8-4bcc-b458-e9cffad81cab',
    'b2ada37a-d4c4-4d1c-a5c4-00ba1d36faad'
);
COMMIT;
```

### 4. (Operator discretion) Stone Products Unlimited → SPUI

`Stone Products Unlimited` (seeded, 1 Instantly sub) is likely the same customer as our existing `SPUI` (3 EB subs). **Worth a quick Stripe/Hypertide check** — if it's the same Stripe customer, merge using the same pattern as above; otherwise leave it standalone.

| Existing canonical (if confirmed) | id | chs subs |
|---|---|---|
| `SPUI` | `4759c558-3b81-42fb-bcb3-a7625b09dbff` | 3 (Email Bison) |

| Merge source (if confirmed) | id | chs subs |
|---|---|---|
| `Stone Products Unlimited` | `938400bf-1f57-4379-a429-0153d856c8af` | 1 (Instantly) |

```sql
-- ONLY IF OPERATOR CONFIRMS SAME CUSTOMER
BEGIN;
UPDATE client_hypertide_subscriptions
SET client_id = '4759c558-3b81-42fb-bcb3-a7625b09dbff'
WHERE client_id = '938400bf-1f57-4379-a429-0153d856c8af';
DELETE FROM clients WHERE id = '938400bf-1f57-4379-a429-0153d856c8af';
COMMIT;
```

## Operator review items (not merges, but flag-and-confirm)

These seeded clients defaulted to `client_status='client'` per DECISION 5 (Email Bison or Instantly tool). If any are actually F&F partners that happen to use EB/Instantly, flip them now via `UPDATE clients SET client_status='friends_and_family' WHERE id=...`.

| Seeded client | id | subs | sending_tool | What to verify |
|---|---|---|---|---|
| `397 Digital` | `b0b691dc-f047-4e50-8e6f-7bc0d7c73108` | 5 | Email Bison | Real client or F&F? Created 2026-01-26 — recent enough that Stripe should know |
| `Bridge` | `0c8e5760-e8cf-48cd-be4d-3d7cf531407f` | 1 | Email Bison | Real client? |
| `10x PR`, `Carve Comms`, `Clarity and Form`, `Cookson Communication`, `Coterie Media`, `Pr73` | — | 1-4 each | Instantly | Each is an Ink'd-class onboarded-HT-side-only client; CharmOS will get the domain side once Instantly extraction lands (step 5+) |

## Charm-prefixed Smartlead orgs (left as F&F per operator decision 2026-05-18)

For audit trail: these stayed as `friends_and_family` per the standing decision (`Smartlead = F&F` regardless of org_name match):

- `Charm Node` (1 sub, created 2024-11-22)
- `Charm Orchestration` (2 subs, 2024-11-22)
- `Charm Organization HT Ent` (1 sub, 2024-11-22)
- `Charm Scaling system` (1 sub, 2024-11-22)

If this changes (e.g. Charm-internal Smartlead infra needs operational tracking after all), flip with a single UPDATE — but the rule says F&F.

## Existing clients with zero chs rows

Five existing clients have no HT subscription bound after the seed:

| Client | Notes |
|---|---|
| `Estrada` | No HT activity in current `/orders/active` |
| `EventPanda` | No HT activity |
| `Neon` | No HT activity |
| `Test Workspace` | Likely intentional — non-client test row |
| `Ink'd` | Will get 11 chs rows once Ink'd-family merge above is applied |

The first four are candidates for `client_status='inactive'` if they're truly inactive (no current HT relationship). Operator can decide per client.
