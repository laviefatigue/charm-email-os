-- Migration 014: Add is_active column to strategy_suggestions
-- This fixes an error where a database trigger references is_active but the column doesn't exist
-- The trigger was likely added manually and references this column

-- Add is_active column with default true
ALTER TABLE strategy_suggestions
ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT true;

-- Also check for and drop any rogue triggers on the table
-- (Uncomment if you need to drop triggers)
-- DROP TRIGGER IF EXISTS some_trigger_name ON strategy_suggestions;
