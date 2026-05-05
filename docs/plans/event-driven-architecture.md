---
title: Event-Driven Architecture — Scope & Migration Plan
created: 2026-05-05
status: SCOPING (no code changes yet)
related-docs:
  - docs/concepts/kill-triggers.md
  - docs/local-development/emailbison-sync-worker.md
  - docs/plans/INBOX-INTEGRITY-PROGRAM.md
---

# Event-Driven Architecture — Scope & Migration Plan

## Why this exists

The current architecture is polling-driven. Every action loop (health
checks, kill processing, threshold maintenance, tag reconciliation) runs
on a fixed timer and reacts to the database state at that moment. This
works, but introduces latency between condition and action that's
material for the kill→promote chain:

| Stage | Cycle (pre-2026-05-05) | Cycle (post-2026-05-05) |
|-------|-----------------------:|------------------------:|
| EB → DB sync (data ingestion) | 30s–5m | unchanged (EB has no webhooks) |
| Health check evaluation       | 15 min | 5 min |
| Kill queue processing         | 30 min | 60s |
| Pool threshold maintenance    | 30 min | 60s |
| Set tag reconciliation        | 30 min | 60s |
| Daily counter reset           | midnight | irrelevant after lifetime-rule |

Worst-case kill→promote latency dropped from ~75 min to ~7 min on
2026-05-05 by shortening polls (commit pending). That's acceptable but
not ideal: a killed inbox can still be assigned to campaigns for up to
~7 min after EB sees the death. **Operationally we want kill→promote
in single-digit seconds, not minutes.**

Event-driven addresses the residual gap and aligns with the design
philosophy that **the system should act when conditions occur**, not
when the next timer fires.

## Scope

### What can be event-driven

These are events that originate INSIDE the system (DB state changes
or in-process triggers). Latency depends only on our infrastructure.

| Event | Trigger | Action |
|-------|---------|--------|
| `kill_queued` | Insert into `kill_queue` with `status='pending'` | kill_processor runs immediately for that row |
| `inbox_died` | `sender_accounts.inbox_state` transitions to `'dead'` | pool_promotion fires immediately for that workspace |
| `domain_burned` | `domains.pool_status` transitions to `'burned'` | All inbox detag fires immediately |
| `pool_status_changed` | `sender_accounts.inventory_pool_status` changes | set_tag_sync reconciles EB tag |
| `package_assigned` | `workspaces.package_id` becomes non-NULL | `_maintain_pool_thresholds` runs immediately for that workspace |
| `workspace_paused` | `workspaces.pause_pool_transitions` becomes TRUE | Future promotions blocked |

### What cannot be event-driven

These are events that originate OUTSIDE the system (in EmailBison or
HyperTide). We have no push channel from those services, so we must
poll.

| External signal | Why we poll |
|-----------------|-------------|
| New bounce in `/replies` | EB has no webhooks |
| New campaign metric | EB has no webhooks |
| Inbox connection state change | EB has no webhooks |
| HyperTide order completion | HT has no webhooks |
| OAuth re-auth required | EB has no webhooks |

These remain polling-based. Polling for ingestion is fine — the latency
of "we learn about a bounce 5 min late" is fine as long as the
**reaction** to that bounce (queueing a kill) fires within seconds of
ingestion.

### What stays as polling even in steady state

| Job | Why polling is correct |
|-----|------------------------|
| Daily 24h counter reset | Calendar-driven, not state-driven (legacy column maintenance after rate rewrite — may be deleted in Phase 5) |
| Daily volume snapshot | Calendar-driven, daily aggregation |
| Daily inbox audit | Calendar-driven |
| Daily Slack audit (7 AM Pacific) | Calendar-driven |
| Workspace discovery (every 5 min) | Polls EB for new workspaces |
| OAuth queue processing | Periodic batch, low-urgency |

## Architecture options

### Option A — Postgres LISTEN/NOTIFY (recommended)

Use the database we already have. Triggers fire `pg_notify()` on state
changes; a worker subscribes via `LISTEN`. Free, durable as the DB
itself, no new infrastructure.

**Pros:**
- Zero new services to operate.
- Notifications are in-process to the DB, sub-second latency.
- Triggers are atomic with the change — if the DB transaction commits,
  the notification fires.
- Easy to debug: `SELECT * FROM pg_listening_channels()` shows what's
  subscribed; `pg_notify('channel', 'payload')` from psql tests the
  flow manually.

**Cons:**
- Notifications are NOT durable. If the worker is offline when an event
  fires, the event is lost. Mitigation: treat events as a latency
  optimization, keep polling as a backstop. Worker reconnects and the
  next poll sweep catches anything missed.
- Payload size limited to 8000 bytes (more than enough for IDs).
- Single-connection LISTEN — multiple workers need a fan-out pattern
  (one listener relays to a queue, or each worker LISTENs separately
  and idempotency on the consumer side prevents double-processing).

**How it would work for our hottest path:**

```sql
-- Trigger on kill_queue insert
CREATE FUNCTION notify_kill_queued() RETURNS TRIGGER AS $$
BEGIN
    IF NEW.status = 'pending' THEN
        PERFORM pg_notify('kill_queued', json_build_object(
            'kill_queue_id', NEW.id,
            'inbox_id', NEW.inbox_id,
            'workspace_id', NEW.workspace_id,
            'trigger_type', NEW.trigger_type::text
        )::text);
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER kill_queue_notify_pending
AFTER INSERT ON kill_queue
FOR EACH ROW EXECUTE FUNCTION notify_kill_queued();
```

```python
# Worker subscription pattern
async def listen_for_events():
    conn = await asyncpg.connect(...)
    await conn.add_listener('kill_queued', on_kill_queued)
    await conn.add_listener('inbox_died', on_inbox_died)
    # connection stays open; events arrive as callbacks
    while True:
        await asyncio.sleep(60)  # heartbeat

async def on_kill_queued(connection, pid, channel, payload):
    data = json.loads(payload)
    # process this single kill_queue row immediately
    await process_kill_row(data['kill_queue_id'])
```

### Option B — Redis Streams or RabbitMQ

External message broker. More features (durable, multiple consumers,
backpressure, replay) but more infrastructure.

**Pros:**
- Durable: events survive worker restarts.
- Native fan-out, consumer groups, dead-letter handling.

**Cons:**
- New service to deploy, monitor, back up.
- Operational overhead.
- We don't currently use either; introducing one is a meaningful tax.

**When this becomes worth it:**
- We start having multiple worker instances handling the same event type.
- We need event replay for debugging or auditing.
- Latency requirements drop below 100ms (LISTEN/NOTIFY isn't a fit then).

For our 7-min → 1-second goal, Option A is sufficient.

### Option C — In-process pub/sub

Single Python process with internal event bus. Simplest of all but
breaks if we ever scale to multiple workers.

We're already on a single sync worker, so this would technically work,
but it doesn't decouple producer and consumer the way LISTEN/NOTIFY
does. A DB write from one component (e.g., kill_processor) wouldn't
be observable to another (e.g., a future external dashboard). Skip.

## Recommended path: Option A (Postgres LISTEN/NOTIFY)

### Phase 1 — Foundation (~1 day)

- New module `sync_modules/event_listener.py` that opens a long-lived
  asyncpg connection, registers handlers per channel, and runs as a
  background coroutine alongside the existing poll loop.
- Add migration `106_event_notification_triggers.sql` with one trigger
  per event class above.
- Worker startup: spawn `EventListener.run()` task. Existing poll loop
  continues unchanged — events are a SUPPLEMENT, not a replacement.

### Phase 2 — Wire up the kill chain (~1 day)

The hottest path. Three triggers + three handlers:

- `kill_queued` → handler runs `kill_processor.process_one(kill_queue_id)`
  (new method that processes a single row instead of the full queue).
- `inbox_died` → handler runs `pool_promotion.promote_one(workspace_id)`.
- `pool_status_changed` → handler runs `set_tag_sync.sync_one(inbox_id)`.

Idempotency: each handler checks current state first
(`SELECT FOR UPDATE`), bails if already processed. The poll-loop
backstop will eventually catch anything that fails handler execution.

### Phase 3 — Soak with poll backstop (~1 week)

Run both event-driven and poll-driven paths in parallel. The poll
catches anything events missed (worker disconnects, payload parse
errors, race conditions). Compare: how many events fired vs how many
items the poll caught. Target: events handle >95% of state changes,
poll picks up <5%.

If the percentages look right, we know events are reliable.

### Phase 4 — Tighten polls, keep them as backstop (~half day)

Lengthen poll intervals back out (e.g., kill_processor every 5 min
instead of 60s) since events handle the latency-sensitive path.
Polls stay as the safety net, not the primary mechanism. Worst-case
latency stays low because events fire in <1s; polls are now there
to catch the rare event-drop.

### Phase 5 — Add the rest of the events (~1 day)

`domain_burned`, `package_assigned`, `workspace_paused` follow the
same pattern. Each is independently valuable.

### Phase 6 — Observability (~half day)

Add metrics: event count per channel per minute, handler execution
time, handler failure count. Slack alert if event count drops to zero
(suggests trigger broken or worker disconnected).

## What changes in operator behavior

| Before (polling) | After (events + poll backstop) |
|------------------|-------------------------------|
| Inbox killed → ~7 min until tagged in EB | Inbox killed → <1s until tagged |
| Reserve graduates → ~1 min until promoted | Reserve graduates → <1s until promoted |
| Operator assigns package → wait one cycle | Operator assigns package → immediate threshold check |
| Domain burns → ~7 min until inbox detag | Domain burns → <1s until detag |
| Operator must wait to confirm an action took effect | Operator sees DB state change → tag change in EB within seconds |

## Risks and mitigations

| Risk | Mitigation |
|------|-----------|
| LISTEN connection drops, events lost | Poll backstop catches missed events on next cycle |
| Handler crashes mid-execution | Idempotency check on next handler run / poll fallback |
| Trigger payload parsing error | Handler logs + skips, poll picks up |
| pg_notify size limit (8000 bytes) | Send IDs only, never full row data — we re-fetch in handler |
| Multiple workers double-processing | `SELECT ... FOR UPDATE SKIP LOCKED` pattern in handler |
| Trigger logic bug | Triggers are isolated SQL functions; well-tested before enabling |

## Out of scope

- **EmailBison webhooks.** EB doesn't push events to us. Polling EB
  remains the only ingestion path.
- **Replacing the poll loop entirely.** Polling stays as a backstop
  forever. Events are an optimization layer, not a replacement.
- **Cross-service event bus.** No external message broker. Postgres
  is sufficient for our scale and shape.
- **Replay / audit log.** If we need historical event replay later,
  we add `event_log` table and write-through. Not needed now.

## Decision points for the operator

1. **Approve Option A (Postgres LISTEN/NOTIFY)?** vs invest in a broker.
2. **Phase 2 scope:** kill chain only, or include other state changes?
3. **Cycle length after Phase 4:** how aggressive do we make the poll
   backstop? My pick: 5 min for the kill chain (catches anything
   events missed within reasonable freshness), keep 60s for Phase 1
   while we're proving event reliability.

## Estimated effort

~3-4 days of engineering work spread across 1-2 weeks for the soak
period. No new infrastructure. Roughly:

- Day 1: Foundation (event listener + first trigger) + first kill chain handler.
- Day 2: Remaining kill chain triggers + handlers.
- Day 3: Tests + dry-run/audit flag.
- Days 4-10: Soak; compare event vs poll counts.
- Day 11: Tighten polls, ship.

## Files that would change

| File | Change |
|------|--------|
| `sync_modules/event_listener.py` | NEW — listener loop |
| `sync_modules/kill_processor.py` | Add `process_one(kill_queue_id)` single-row method |
| `sync_modules/pool_promotion.py` | Add `promote_one(workspace_id)` |
| `sync_modules/set_tag_sync.py` | Add `sync_one(inbox_id)` |
| `emailbison_sync_worker.py` | Spawn EventListener task in poll loop startup |
| `migrations/106_event_notification_triggers.sql` | NEW — triggers + functions |
| `tests/test_event_listener.py` | NEW — handler idempotency, missed-event recovery |
