-- Migration 108: Event triggers (Phase 2 of event-driven architecture)
--
-- Plan: docs/plans/event-driven-architecture.md
--
-- WHAT THIS DOES
-- ──────────────
-- Adds DB triggers that fire on every meaningful state change. Each
-- trigger does TWO things in one atomic operation:
--   1. INSERT INTO event_log (status='emitted')
--   2. PERFORM pg_notify(channel, payload)
--
-- Triggers run in the SAME transaction as the originating state change.
-- If the change commits, the event_log row commits. If it rolls back,
-- the row rolls back. Zero "missed event" race condition.
--
-- The pg_notify is best-effort low-latency hint; the durable record
-- is the event_log row. Listeners that miss the NOTIFY (because they
-- were offline) catch up on reconnect by reading WHERE status='emitted'.
--
-- IDEMPOTENCY
-- ───────────
-- Triggers are idempotent: re-running this migration drops + recreates
-- functions and triggers. Safe to apply multiple times.

BEGIN;

-- =====================================================================
-- HELPER: emit_event(event_type, entity_type, entity_id, payload, workspace_id)
-- =====================================================================
-- Single helper used by all triggers. Inserts event_log row + notifies.
-- Trigger functions call this rather than duplicating insert+notify.

CREATE OR REPLACE FUNCTION emit_event(
    p_event_type    TEXT,
    p_entity_type   TEXT,
    p_entity_id     UUID,
    p_payload       JSONB,
    p_workspace_id  UUID DEFAULT NULL
) RETURNS UUID AS $$
DECLARE
    v_event_id UUID;
    v_full_payload JSONB;
BEGIN
    -- Build full payload with the event_id baked in so listener handlers
    -- can fetch the row by id without re-querying via entity_id.
    v_event_id := gen_random_uuid();

    v_full_payload := p_payload || jsonb_build_object(
        'event_id',     v_event_id,
        'event_type',   p_event_type,
        'entity_type',  p_entity_type,
        'entity_id',    p_entity_id,
        'workspace_id', p_workspace_id,
        'emitted_at',   NOW()
    );

    INSERT INTO event_log (
        id, event_type, entity_type, entity_id,
        payload, workspace_id, status
    ) VALUES (
        v_event_id, p_event_type, p_entity_type, p_entity_id,
        v_full_payload, p_workspace_id, 'emitted'
    );

    -- pg_notify payload is the event_id as a string. Listener fetches
    -- the full row by that id. Keeps payload size bounded (8000 bytes
    -- is the postgres NOTIFY limit; UUIDs are 36 chars).
    PERFORM pg_notify(p_event_type, v_event_id::text);

    RETURN v_event_id;
END;
$$ LANGUAGE plpgsql;


-- =====================================================================
-- KILL CHAIN TRIGGERS
-- =====================================================================

-- bounce_observed: every new hard bounce in response_messages.
-- Handler will recompute the lifetime rate for this inbox and queue
-- a kill if > 5%.
CREATE OR REPLACE FUNCTION notify_bounce_observed()
RETURNS TRIGGER AS $$
DECLARE
    v_workspace_id UUID;
BEGIN
    -- Only emit for hard bounces (the rule's numerator). Soft bounces
    -- are captured in response_messages but don't fire events.
    IF NEW.folder = 'bounced'
       AND NEW.bounce_type IN ('hard_blocked', 'hard_unknown')
       AND NEW.sender_account_id IS NOT NULL
    THEN
        SELECT workspace_id INTO v_workspace_id
        FROM sender_accounts WHERE id = NEW.sender_account_id;

        PERFORM emit_event(
            'bounce_observed',
            'response_message',
            NEW.id,
            jsonb_build_object(
                'sender_account_id', NEW.sender_account_id,
                'bounce_type',       NEW.bounce_type,
                'received_at',       NEW.received_at
            ),
            v_workspace_id
        );
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_response_messages_bounce_observed ON response_messages;
CREATE TRIGGER trg_response_messages_bounce_observed
    AFTER INSERT ON response_messages
    FOR EACH ROW EXECUTE FUNCTION notify_bounce_observed();


-- kill_queued: a new kill row was inserted with status='pending'.
-- Handler runs kill_processor.process_one(kill_queue_id).
CREATE OR REPLACE FUNCTION notify_kill_queued()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.status = 'pending' THEN
        PERFORM emit_event(
            'kill_queued',
            'kill_queue',
            NEW.id,
            jsonb_build_object(
                'inbox_id',          NEW.inbox_id,
                'trigger_type',      NEW.trigger_type::text,
                'trigger_value',     NEW.trigger_value,
                'trigger_threshold', NEW.trigger_threshold
            ),
            NEW.workspace_id
        );
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_kill_queue_pending ON kill_queue;
CREATE TRIGGER trg_kill_queue_pending
    AFTER INSERT ON kill_queue
    FOR EACH ROW EXECUTE FUNCTION notify_kill_queued();


-- inbox_died: sender_accounts.inbox_state transitioned to 'dead'.
-- Handler runs pool_promotion if package set; enqueues tag_op_remove
-- for live tag.
CREATE OR REPLACE FUNCTION notify_inbox_died()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.inbox_state = 'dead' AND OLD.inbox_state IS DISTINCT FROM 'dead' THEN
        PERFORM emit_event(
            'inbox_died',
            'inbox',
            NEW.id,
            jsonb_build_object(
                'email_address', NEW.email_address,
                'kill_trigger',  NEW.kill_trigger::text,
                'killed_at',     NEW.killed_at,
                'esp',           NEW.esp
            ),
            NEW.workspace_id
        );
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_sender_accounts_died ON sender_accounts;
CREATE TRIGGER trg_sender_accounts_died
    AFTER UPDATE OF inbox_state ON sender_accounts
    FOR EACH ROW EXECUTE FUNCTION notify_inbox_died();


-- =====================================================================
-- LIFECYCLE TRIGGERS
-- =====================================================================

-- inbox_pickup: new sender_accounts row inserted (HyperTide provisioned
-- + EB sync brought it down). Plan A CHECK already validated workspace
-- assignment; this event records the audit + lets soft-validation
-- handlers run.
CREATE OR REPLACE FUNCTION notify_inbox_pickup()
RETURNS TRIGGER AS $$
BEGIN
    PERFORM emit_event(
        'inbox_pickup',
        'inbox',
        NEW.id,
        jsonb_build_object(
            'email_address',     NEW.email_address,
            'esp',               NEW.esp,
            'domain_id',         NEW.domain_id,
            'first_seen_at',     NEW.first_seen_at
        ),
        NEW.workspace_id
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_sender_accounts_pickup ON sender_accounts;
CREATE TRIGGER trg_sender_accounts_pickup
    AFTER INSERT ON sender_accounts
    FOR EACH ROW EXECUTE FUNCTION notify_inbox_pickup();


-- pool_changed: inventory_pool_status transitioned (NULL → reserve,
-- reserve → live, live → NULL on burn, etc.). Handler enqueues
-- tag_op events for the Tier 2 batch worker.
--
-- Important: this fires on TRANSITIONS only. The initial NULL → first
-- assignment by lifecycle_tag_sync (graduation path) is handled by the
-- graduation handler instead, which writes the EB tag transition itself
-- in the same EB-first-DB-on-success pattern. Once incubation-watcher
-- Phase 4 cuts over and owns graduation, this trigger fires for ALL
-- pool changes including the initial assignment.
CREATE OR REPLACE FUNCTION notify_pool_changed()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.inventory_pool_status IS DISTINCT FROM OLD.inventory_pool_status THEN
        PERFORM emit_event(
            'pool_changed',
            'inbox',
            NEW.id,
            jsonb_build_object(
                'email_address',  NEW.email_address,
                'old_pool',       OLD.inventory_pool_status,
                'new_pool',       NEW.inventory_pool_status,
                'esp',            NEW.esp
            ),
            NEW.workspace_id
        );
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_sender_accounts_pool_changed ON sender_accounts;
CREATE TRIGGER trg_sender_accounts_pool_changed
    AFTER UPDATE OF inventory_pool_status ON sender_accounts
    FOR EACH ROW EXECUTE FUNCTION notify_pool_changed();


-- =====================================================================
-- DOMAIN TRIGGER
-- =====================================================================

-- domain_burned: a domain's pool_status flipped to 'burned'. Handler
-- detags all inboxes on that domain.
CREATE OR REPLACE FUNCTION notify_domain_burned()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.pool_status = 'burned' AND OLD.pool_status IS DISTINCT FROM 'burned' THEN
        PERFORM emit_event(
            'domain_burned',
            'domain',
            NEW.id,
            jsonb_build_object(
                'domain_name',   NEW.domain_name,
                'burn_trigger',  NEW.burn_trigger,
                'burned_at',     NEW.burned_at
            ),
            NEW.workspace_id
        );
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_domains_burned ON domains;
CREATE TRIGGER trg_domains_burned
    AFTER UPDATE OF pool_status ON domains
    FOR EACH ROW EXECUTE FUNCTION notify_domain_burned();


-- =====================================================================
-- WORKSPACE CONFIG TRIGGERS
-- =====================================================================

-- package_assigned: workspace got a package_id. Handler runs
-- _maintain_pool_thresholds immediately so the workspace doesn't
-- wait a full poll cycle.
CREATE OR REPLACE FUNCTION notify_package_assigned()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.package_id IS DISTINCT FROM OLD.package_id
       AND NEW.package_id IS NOT NULL
    THEN
        PERFORM emit_event(
            'package_assigned',
            'workspace',
            NEW.id,
            jsonb_build_object(
                'workspace_name', NEW.workspace_name,
                'old_package_id', OLD.package_id,
                'new_package_id', NEW.package_id
            ),
            NEW.id
        );
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_workspaces_package_assigned ON workspaces;
CREATE TRIGGER trg_workspaces_package_assigned
    AFTER UPDATE OF package_id ON workspaces
    FOR EACH ROW EXECUTE FUNCTION notify_package_assigned();


COMMIT;

-- Note: this migration is idempotent. The DROP TRIGGER IF EXISTS +
-- CREATE TRIGGER pattern means re-running is safe. Trigger functions
-- use CREATE OR REPLACE.
