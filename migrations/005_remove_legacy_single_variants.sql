-- Migration 005: Remove legacy single-variant campaign suggestions
-- This migration cleans up old single-email records and enforces sequence-only going forward

-- Step 1: Log count of legacy records before deletion
DO $$
DECLARE
    legacy_count INTEGER;
    orphaned_jobs INTEGER;
BEGIN
    SELECT COUNT(*) INTO legacy_count
    FROM strategy_suggestions
    WHERE is_sequence = FALSE OR is_sequence IS NULL;

    RAISE NOTICE 'Found % legacy single-variant suggestions to remove', legacy_count;
END $$;

-- Step 2: Delete legacy single-variant suggestions (is_sequence = FALSE or NULL)
DELETE FROM strategy_suggestions
WHERE is_sequence = FALSE OR is_sequence IS NULL;

-- Step 3: Delete orphaned revision requests (requests for deleted suggestions)
DELETE FROM strategy_revision_requests
WHERE variant_id IS NOT NULL
AND variant_id NOT IN (SELECT id FROM strategy_suggestions);

-- Step 4: Delete orphaned jobs (jobs with no remaining suggestions)
DELETE FROM strategy_generation_jobs
WHERE id NOT IN (
    SELECT DISTINCT job_id
    FROM strategy_suggestions
    WHERE job_id IS NOT NULL
);

-- Step 5: Set default value and NOT NULL constraint on is_sequence
-- This prevents future creation of single-variant records
ALTER TABLE strategy_suggestions
ALTER COLUMN is_sequence SET DEFAULT TRUE;

-- Note: NOT NULL constraint added separately to handle any edge cases
DO $$
BEGIN
    -- First ensure no NULL values exist
    UPDATE strategy_suggestions SET is_sequence = TRUE WHERE is_sequence IS NULL;

    -- Then add the constraint
    ALTER TABLE strategy_suggestions
    ALTER COLUMN is_sequence SET NOT NULL;
EXCEPTION
    WHEN others THEN
        RAISE NOTICE 'NOT NULL constraint may already exist or failed: %', SQLERRM;
END $$;

-- Step 6: Add check constraint to ensure is_sequence is always TRUE going forward
DO $$
BEGIN
    ALTER TABLE strategy_suggestions
    ADD CONSTRAINT chk_is_sequence_true CHECK (is_sequence = TRUE);
EXCEPTION
    WHEN duplicate_object THEN
        RAISE NOTICE 'Constraint chk_is_sequence_true already exists';
END $$;

-- Verification query (run manually to confirm)
-- SELECT COUNT(*), is_sequence FROM strategy_suggestions GROUP BY is_sequence;
