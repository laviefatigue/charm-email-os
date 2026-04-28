# Integration tests for the 2026-04-27 tagging-kill overhaul

These tests run against a **real Postgres** and exercise the production
modules (`lifecycle_tag_sync`, `set_tag_sync`, `kill_processor`,
`health_checks`) end-to-end, with a `FakeEmailBisonClient` test double
in place of the network-bound EB client.

## What's in here

| File | Purpose |
|------|---------|
| `conftest.py` | Pytest fixtures — DB pool, schema setup, workspace factory |
| `fakes.py` | `FakeEmailBisonClient` — records calls, models EB tag state, lets tests inject failures |
| `test_overhaul.py` | 8 critical-behavior tests (T1, T2, T3, T5, T7, T8, T11, T12 from the overhaul plan) |

## Running

The tests resolve a Postgres URL in this order:

1. `TEST_DATABASE_URL` env var — pointing at any reachable Postgres
2. `testcontainers` Postgres (requires Docker Desktop running)

If neither is available the suite skips cleanly — never silently passes
with mocked DB.

### With a local Postgres

```bash
# 1. Create a fresh test database
PGPASSWORD=postgres psql -h localhost -p 5433 -U postgres -d postgres \
    -c "DROP DATABASE IF EXISTS charm_test_overhaul"
PGPASSWORD=postgres psql -h localhost -p 5433 -U postgres -d postgres \
    -c "CREATE DATABASE charm_test_overhaul"

# 2. Apply the schema (see "Schema setup" below)

# 3. Run the suite
TEST_DATABASE_URL="postgresql://postgres:postgres@localhost:5433/charm_test_overhaul" \
    py -m pytest tests/test_overhaul.py -v
```

### With testcontainers

```bash
# Docker Desktop must be running
py -m pytest tests/test_overhaul.py -v
```

## Schema setup

The tests need the current production schema. Two paths:

**Path A — fresh dump (recommended):** export a fresh `pg_dump` from a
production-state Postgres and put it at `docker/init/00_public_schema.sql`,
replacing the existing stale dump. The `conftest.py` will apply it +
migrations 094 and 095 (the overhaul migrations) automatically.

**Path B — migrate from scratch:** run the project's normal migration
runner against the empty test database. This requires the migration
runner to be ordering-aware (the `migrations/` directory has duplicate-
numbered files like `023_hypertide_*.sql` and `023_oauth_configs_*.sql`
that need explicit ordering — `conftest.py` cannot resolve that).

The current `docker/init/00_public_schema.sql` is from an older
production state and is missing columns added by later migrations
(`warmup_enabled`, `inventory_pool_status`, `inventory_lifecycle_status`,
etc.). Re-applying the migrations on top of it produces ordering
collisions; `conftest.py` logs and skips those, but enough downstream
state is missing that tests cannot run cleanly until a fresh dump is
generated.

## What the tests actually check

Every test asserts on **both database state and the fake EB tag state**
after calling a real production method. Mocking-and-asserting-the-mock
patterns are intentionally absent — tests describe the externally-
visible outcome the way production code produces it.

| Test | Behavior |
|------|----------|
| T1 | Google inbox graduating after 14 BD warmup gets only `reserve` tag in EB; `live` is never written |
| T2 | Microsoft inbox graduates directly to `live` with `inventory_pool_status='deployed'` |
| T3 | Pre-existing dual-tagged inbox (`live` + `reserve` in EB) is reconciled — wrong tag stripped |
| T5 | Inbox with `inventory_pool_status='warning'` has BOTH pool tags removed (active circuit breaker) |
| T7 | Cross-domain promotion: oldest reserve from any domain wins; source domain stays `pool_status='reserve'` |
| T8 | 3-inbox Google domain with 2 dead inboxes is retired (`domain_state='dead'`) |
| T11 | Inbox warmed for 14 BD but `warmup_enabled=FALSE` is NOT graduated (continuous-warmup invariant) |
| T12 | Low-volume inbox (`hard_bounces_24h=2`, `total_sends_24h=3`) is NOT killed (min-sends floor) |

## Failure injection

`FakeEmailBisonClient.fail_on(method, when)` lets a test arm a specific
EB call to raise `FakeEBError` on the next match. Use this to simulate
the partial-write race that produced the 133 dual-tag inboxes in
production:

```python
fake_client.fail_on(
    "untag_inbox",
    when=lambda account_id, tag_id: tag_id == reserve_tag_id,
)
# Now run set_tag_sync — the untag will fail mid-write, and the test
# can assert that the DB state is unchanged so the next cycle retries.
```
