-- Add draft_lrc field to media table for storing formatted timestamped transcription
-- Run this migration after 001_add_transcribe_fields.sql

ALTER TABLE media ADD COLUMN IF NOT EXISTS draft_lrc TEXT;

COMMENT ON COLUMN media.draft_lrc IS 'Formatted transcription in LRC subtitle format (with timestamps)';