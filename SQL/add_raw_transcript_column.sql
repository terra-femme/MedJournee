-- Add raw_transcript column to journal_entries table
-- Run this in Supabase SQL Editor

ALTER TABLE journal_entries
ADD COLUMN IF NOT EXISTS raw_transcript TEXT;

-- Verify the column was added
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'journal_entries' AND column_name = 'raw_transcript';
