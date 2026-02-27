-- Migration: 057_add_disconnected_inbox_state.sql
-- Purpose: Add 'disconnected' as an intermediate inbox_state between 'live' and 'dead'
--
-- LIFECYCLE:
--   live → disconnected → dead
--
-- DEFINITIONS:
--   - LIVE: inbox_state='live' AND status='Connected'
--   - DISCONNECTED: inbox_state='disconnected' (was live, now not connected)
--   - DEAD: inbox_state='dead' (killed by trigger OR disconnected for 21+ days)
--
-- RULES:
--   1. When a live inbox loses connection → inbox_state='disconnected', disconnected_at=NOW()
--   2. When a disconnected inbox reconnects → inbox_state='live', disconnected_at=NULL
--   3. When disconnected for 21+ days → inbox_state='dead', kill_trigger='disconnected_timeout'
--   4. Domain with ALL inboxes disconnected = dead domain (no operational capacity)

BEGIN;

-- =============================================================================
-- PART 1: Add new inbox_state value to enum (if using enum)
-- =============================================================================

-- Check if inbox_state is an enum or varchar
-- If varchar, no enum change needed - just add column comment

-- Add disconnected_at column to track when inbox became disconnected
ALTER TABLE sender_accounts
ADD COLUMN IF NOT EXISTS disconnected_at TIMESTAMP WITH TIME ZONE;

-- Add comment explaining the column
COMMENT ON COLUMN sender_accounts.disconnected_at IS
'Timestamp when inbox status changed from Connected to Not connected/Disconnected.
Used to auto-kill inboxes disconnected for 21+ days. NULL if inbox is connected or dead.';

-- =============================================================================
-- PART 2: Add new kill trigger type for disconnected timeout
-- =============================================================================

-- The kill_trigger column already accepts any string, so 'disconnected_timeout' is valid
-- Just document it here for clarity

COMMENT ON COLUMN sender_accounts.kill_trigger IS
'Kill trigger that caused inbox death. Values:
- spam_complaint: Spam complaint received
- hard_blocked_24h: Hard blocked bounces in 24h
- hard_unknown_24h: Invalid addresses in 24h
- hard_bounces_24h: Combined hard bounces in 24h
- hard_bounce_rate_7d: Hard bounce rate > 0.5%
- bounce_rate_all_7d: Total bounce rate > 5%
- fresh_inbox_bounce: Any bounce on inbox < 14 days old
- disconnected_timeout: Disconnected for 21+ days (NEW)
- manual: Manually killed';

-- =============================================================================
-- PART 3: Initialize disconnected_at for currently disconnected inboxes
-- =============================================================================

-- For inboxes that are currently 'Not connected' but still live,
-- we don't know when they became disconnected. Use last_sync_at or updated_at as estimate.
UPDATE sender_accounts
SET disconnected_at = COALESCE(updated_at, NOW())
WHERE inbox_state = 'live'
  AND status IN ('Not connected', 'Disconnected')
  AND disconnected_at IS NULL;

DO $$
DECLARE
    affected INTEGER;
BEGIN
    GET DIAGNOSTICS affected = ROW_COUNT;
    RAISE NOTICE 'Initialized disconnected_at for % currently disconnected inboxes', affected;
END $$;

-- =============================================================================
-- PART 4: Transition existing long-disconnected inboxes to 'disconnected' state
-- =============================================================================

-- Inboxes that have been disconnected for a while should be marked as 'disconnected'
-- But we'll let the sync worker handle the actual state transition
-- This just sets up the data

-- For inboxes disconnected more than 21 days, mark them as dead with timeout trigger
UPDATE sender_accounts
SET
    inbox_state = 'dead',
    kill_trigger = 'disconnected_timeout',
    killed_at = NOW(),
    kill_reason = 'Auto-killed after 21+ days disconnected'
WHERE inbox_state = 'live'
  AND status IN ('Not connected', 'Disconnected')
  AND disconnected_at IS NOT NULL
  AND disconnected_at < NOW() - INTERVAL '21 days';

DO $$
DECLARE
    affected INTEGER;
BEGIN
    GET DIAGNOSTICS affected = ROW_COUNT;
    RAISE NOTICE 'Auto-killed % inboxes disconnected for 21+ days', affected;
END $$;

-- =============================================================================
-- PART 5: Update domain counts after state changes
-- =============================================================================

-- Recalculate live/dead inbox counts for all domains
WITH inbox_counts AS (
    SELECT
        domain_id,
        COUNT(*) FILTER (WHERE inbox_state = 'live') as live_count,
        COUNT(*) FILTER (WHERE inbox_state = 'dead') as dead_count,
        COUNT(*) FILTER (WHERE inbox_state = 'live' AND status = 'Connected') as connected_count,
        COUNT(*) FILTER (WHERE inbox_state = 'live' AND status IN ('Not connected', 'Disconnected')) as disconnected_count
    FROM sender_accounts
    WHERE domain_id IS NOT NULL
    GROUP BY domain_id
)
UPDATE domains d
SET
    live_inbox_count = COALESCE(ic.live_count, 0),
    dead_inbox_count = COALESCE(ic.dead_count, 0),
    updated_at = NOW()
FROM inbox_counts ic
WHERE d.id = ic.domain_id;

-- =============================================================================
-- PART 6: Update domain_state for domains with all disconnected inboxes
-- =============================================================================

-- Domains where ALL live inboxes are disconnected should be flagged
-- (They have live inboxes but 0 operational capacity)
UPDATE domains
SET
    domain_state = 'flagged',
    updated_at = NOW()
WHERE id IN (
    SELECT d.id
    FROM domains d
    JOIN sender_accounts sa ON sa.domain_id = d.id
    WHERE d.domain_state = 'live'
    GROUP BY d.id
    HAVING
        COUNT(*) FILTER (WHERE sa.inbox_state = 'live' AND sa.status = 'Connected') = 0
        AND COUNT(*) FILTER (WHERE sa.inbox_state = 'live') > 0
);

DO $$
DECLARE
    affected INTEGER;
BEGIN
    GET DIAGNOSTICS affected = ROW_COUNT;
    RAISE NOTICE 'Flagged % domains with all live inboxes disconnected', affected;
END $$;

-- =============================================================================
-- PART 7: Summary report
-- =============================================================================

DO $$
DECLARE
    live_connected INTEGER;
    live_disconnected INTEGER;
    dead_inboxes INTEGER;
    flagged_domains INTEGER;
BEGIN
    SELECT COUNT(*) INTO live_connected
    FROM sender_accounts WHERE inbox_state = 'live' AND status = 'Connected';

    SELECT COUNT(*) INTO live_disconnected
    FROM sender_accounts WHERE inbox_state = 'live' AND status IN ('Not connected', 'Disconnected');

    SELECT COUNT(*) INTO dead_inboxes
    FROM sender_accounts WHERE inbox_state = 'dead';

    SELECT COUNT(*) INTO flagged_domains
    FROM domains WHERE domain_state = 'flagged';

    RAISE NOTICE '=== Migration 057 Complete ===';
    RAISE NOTICE 'Inbox state distribution:';
    RAISE NOTICE '  Live + Connected: %', live_connected;
    RAISE NOTICE '  Live + Disconnected: %', live_disconnected;
    RAISE NOTICE '  Dead: %', dead_inboxes;
    RAISE NOTICE '  Flagged domains: %', flagged_domains;
END $$;

COMMIT;

-- =============================================================================
-- DOCUMENTATION: New State Transitions
-- =============================================================================
--
-- INBOX STATE MACHINE:
--
--   ┌─────────────────────────────────────────────────────────────┐
--   │                        LIVE                                │
--   │  (inbox_state='live', status='Connected')                  │
--   └────────────────────────┬────────────────────────────────────┘
--                            │
--              status changes to 'Not connected'
--              → set disconnected_at = NOW()
--                            │
--                            ▼
--   ┌─────────────────────────────────────────────────────────────┐
--   │                    DISCONNECTED                            │
--   │  (inbox_state='live', status='Not connected')              │
--   │  (disconnected_at is set)                                  │
--   └────────────────────────┬────────────────────────────────────┘
--                            │
--        ┌───────────────────┼───────────────────┐
--        │                   │                   │
--   status='Connected'  21 days pass      kill trigger fires
--   → disconnected_at=NULL                       │
--        │                   │                   │
--        ▼                   ▼                   ▼
--   ┌─────────┐        ┌─────────────┐     ┌─────────────┐
--   │  LIVE   │        │    DEAD     │     │    DEAD     │
--   └─────────┘        │  (timeout)  │     │  (trigger)  │
--                      └─────────────┘     └─────────────┘
--
-- DOMAIN STATE RULES:
--   - LIVE: Has connected live inboxes
--   - FLAGGED: Has live inboxes but all disconnected, OR has dead inboxes
--   - DEAD: No live inboxes at all
--
