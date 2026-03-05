-- Migration 060: Domain Fulfillment Tracking
-- Created: 2026-03-03
-- Purpose: Track HyperTide delivery fulfillment and enable rotation recommendations
--
-- Key insight: We manage domains, but we monitor inboxes.
-- HyperTide delivers domain + inbox packages. We cannot add inboxes to existing domains.
-- Our only action is domain rotation (swap).
--
-- This migration adds:
-- 1. expected_inbox_count - What HyperTide should deliver (50 Entra, 3 Google)
-- 2. max_inboxes_seen - Peak inbox count ever observed (fulfillment verification)
-- 3. fulfillment_status - Did HyperTide deliver what we paid for?

-- =====================================================
-- 1. ADD COLUMNS
-- =====================================================

-- Expected inboxes based on provider type and subscription
-- Set at HyperTide order time or backfilled from defaults
ALTER TABLE domains ADD COLUMN IF NOT EXISTS expected_inbox_count INTEGER;

-- Maximum inboxes ever observed for this domain in EmailBison
-- Used to detect under-delivery (if max < expected, HyperTide issue)
ALTER TABLE domains ADD COLUMN IF NOT EXISTS max_inboxes_seen INTEGER DEFAULT 0;

-- Fulfillment status derived from expected vs max_seen
-- pending: expected not set yet
-- under_delivered: max_seen < expected * 0.9 (HyperTide issue)
-- fulfilled: max_seen >= expected * 0.9 (normal)
-- over_delivered: max_seen > expected (bonus)
ALTER TABLE domains ADD COLUMN IF NOT EXISTS fulfillment_status VARCHAR(20) DEFAULT 'pending';

-- Add check constraint if not exists (postgres doesn't have IF NOT EXISTS for constraints)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'domains_fulfillment_status_check'
    ) THEN
        ALTER TABLE domains ADD CONSTRAINT domains_fulfillment_status_check
            CHECK (fulfillment_status IN ('pending', 'under_delivered', 'fulfilled', 'over_delivered'));
    END IF;
END $$;

-- =====================================================
-- 2. BACKFILL EXPECTED_INBOX_COUNT
-- =====================================================

-- Set expected based on infrastructure_type
-- Entra: 50 inboxes per domain (standard HyperTide package)
-- Google: 3 inboxes per domain (standard HyperTide package)
UPDATE domains d
SET expected_inbox_count = CASE
    WHEN d.infrastructure_type = 'entra' THEN 50
    WHEN d.infrastructure_type = 'google' THEN 3
    ELSE NULL
END
WHERE d.expected_inbox_count IS NULL
AND d.infrastructure_type IS NOT NULL;

-- Secondary backfill: Use DETECTED provider from sender_accounts
-- (infrastructure_type is often NULL, but we can detect from inbox ESP)
UPDATE domains d
SET expected_inbox_count = CASE
    WHEN detected.provider = 'entra' THEN 50
    WHEN detected.provider = 'google' THEN 3
    ELSE NULL
END
FROM (
    SELECT
        sa.domain_id,
        CASE
            WHEN COUNT(*) FILTER (WHERE sa.esp = 'microsoft') > 0 THEN 'entra'
            WHEN COUNT(*) FILTER (WHERE sa.esp = 'gmail') > 0 THEN 'google'
            ELSE NULL
        END as provider
    FROM sender_accounts sa
    WHERE sa.domain_id IS NOT NULL
    GROUP BY sa.domain_id
) detected
WHERE d.id = detected.domain_id
AND d.expected_inbox_count IS NULL
AND detected.provider IS NOT NULL;

-- =====================================================
-- 3. BACKFILL MAX_INBOXES_SEEN
-- =====================================================

-- Set max_inboxes_seen to current total count per domain
-- This includes both active and inactive (is_active) inboxes
-- because we want to know the peak HyperTide ever delivered
UPDATE domains d
SET max_inboxes_seen = COALESCE(sub.total_count, 0)
FROM (
    SELECT
        sa.domain_id,
        COUNT(*) AS total_count
    FROM sender_accounts sa
    WHERE sa.domain_id IS NOT NULL
    GROUP BY sa.domain_id
) sub
WHERE d.id = sub.domain_id
AND (d.max_inboxes_seen IS NULL OR d.max_inboxes_seen = 0);

-- =====================================================
-- 4. CALCULATE FULFILLMENT_STATUS
-- =====================================================

-- Update fulfillment status based on expected vs max_seen
UPDATE domains d
SET fulfillment_status = CASE
    -- No expected set = pending
    WHEN d.expected_inbox_count IS NULL THEN 'pending'
    -- Under-delivered: got less than 90% of expected
    WHEN d.max_inboxes_seen < d.expected_inbox_count * 0.9 THEN 'under_delivered'
    -- Over-delivered: got more than expected
    WHEN d.max_inboxes_seen > d.expected_inbox_count THEN 'over_delivered'
    -- Fulfilled: got what we expected
    ELSE 'fulfilled'
END
WHERE d.fulfillment_status IS NULL OR d.fulfillment_status = 'pending';

-- =====================================================
-- 5. ADD INDEX FOR QUERIES
-- =====================================================

-- Index for finding under-delivered domains (HyperTide issues)
CREATE INDEX IF NOT EXISTS idx_domains_fulfillment_status
ON domains(fulfillment_status)
WHERE fulfillment_status = 'under_delivered';

-- =====================================================
-- 6. ADD COMMENTS
-- =====================================================

COMMENT ON COLUMN domains.expected_inbox_count IS
    'Expected inboxes from HyperTide based on provider (50 Entra, 3 Google). Set at order time.';

COMMENT ON COLUMN domains.max_inboxes_seen IS
    'Maximum inboxes ever observed in EmailBison for this domain. Used for fulfillment verification.';

COMMENT ON COLUMN domains.fulfillment_status IS
    'Fulfillment status: pending (not set), under_delivered (<90% of expected), fulfilled (>=90%), over_delivered (>100%)';

-- =====================================================
-- 7. VERIFICATION QUERY
-- =====================================================

-- Show fulfillment status distribution
SELECT
    fulfillment_status,
    infrastructure_type,
    COUNT(*) as domain_count,
    AVG(expected_inbox_count) as avg_expected,
    AVG(max_inboxes_seen) as avg_delivered
FROM domains
WHERE infrastructure_type IS NOT NULL
GROUP BY fulfillment_status, infrastructure_type
ORDER BY fulfillment_status, infrastructure_type;

SELECT 'Migration 060_domain_fulfillment_tracking complete' AS status;
