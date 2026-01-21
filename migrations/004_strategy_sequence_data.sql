-- Migration 004: Add sequence_data column for 4-email sequences
-- This enables strategy-AI to generate complete campaigns with 4 emails
-- instead of single variants
--
-- The sequence_data column stores:
-- [
--   { position: 1, wait_days: 0, subject_line: "...", email_body: "...", thread_reply: false, strategy: "custom_signal", value_prop: "save_time", word_count: 72 },
--   { position: 2, wait_days: 3, subject_line: null, email_body: "...", thread_reply: true, strategy: "creative_ideas", value_prop: "make_money", word_count: 85 },
--   { position: 3, wait_days: 4, subject_line: "...", email_body: "...", thread_reply: false, strategy: "case_study", value_prop: "save_money", word_count: 58 },
--   { position: 4, wait_days: 4, subject_line: null, email_body: "...", thread_reply: true, strategy: "redirect", value_prop: null, word_count: 32 }
-- ]

-- Add sequence_data JSONB column to store 4-email sequences
ALTER TABLE strategy_suggestions
ADD COLUMN IF NOT EXISTS sequence_data JSONB;

-- Add value_prop_rotation to track the rotation strategy used
ALTER TABLE strategy_suggestions
ADD COLUMN IF NOT EXISTS value_prop_rotation JSONB;

-- Add is_sequence flag to distinguish single variants from full sequences
ALTER TABLE strategy_suggestions
ADD COLUMN IF NOT EXISTS is_sequence BOOLEAN DEFAULT FALSE;

-- Add total_word_count for quick filtering
ALTER TABLE strategy_suggestions
ADD COLUMN IF NOT EXISTS total_word_count INTEGER;

-- Add index for querying sequences
CREATE INDEX IF NOT EXISTS idx_strategy_suggestions_is_sequence
ON strategy_suggestions(client_id, is_sequence)
WHERE is_sequence = TRUE;

-- Comment explaining the migration
COMMENT ON COLUMN strategy_suggestions.sequence_data IS 'JSONB array containing 4-email sequence data for complete campaigns';
COMMENT ON COLUMN strategy_suggestions.value_prop_rotation IS 'Array of value props used in sequence: ["save_time", "make_money", "save_money"]';
COMMENT ON COLUMN strategy_suggestions.is_sequence IS 'TRUE if this is a full 4-email sequence, FALSE for single variant';
