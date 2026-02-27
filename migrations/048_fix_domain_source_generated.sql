-- ============================================
-- Migration 048: Fix domain_source for generated domains
-- ============================================
-- Problem: 150 domains with NO inboxes are incorrectly marked as 'legacy'
-- They should be 'generated' (AI-generated, awaiting purchase)
--
-- Correct categorization:
-- - 'legacy': Has inboxes (external purchase, working) - 359 domains
-- - 'generated': No inboxes, no purchased_at (awaiting purchase) - 150 domains
-- - 'purchased': Has purchased_at (bought through our system) - 0 domains currently

BEGIN;

-- Fix domains with NO inboxes that are incorrectly marked as 'legacy'
-- These are AI-generated domains awaiting purchase
UPDATE domains d
SET domain_source = 'generated', updated_at = NOW()
WHERE d.domain_source = 'legacy'
  AND d.purchased_at IS NULL
  AND NOT EXISTS (
    SELECT 1 FROM sender_accounts sa WHERE sa.domain_id = d.id
  );

COMMIT;

-- Verification query (run after migration):
-- SELECT
--   domain_source,
--   COUNT(*) as count,
--   SUM(CASE WHEN EXISTS(SELECT 1 FROM sender_accounts sa WHERE sa.domain_id = d.id) THEN 1 ELSE 0 END) as with_inboxes
-- FROM domains d
-- WHERE d.is_active = TRUE
-- GROUP BY domain_source;
-- Expected: legacy=359 (all with inboxes), generated=150 (none with inboxes)

SELECT 'Migration 048: Fixed domain_source for generated domains' AS status;
