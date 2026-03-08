-- Add transcribe fields to media table
-- Run this migration manually or via Django migration

-- Add draft field for storing raw transcription
ALTER TABLE media ADD COLUMN IF NOT EXISTS draft TEXT;

-- Add status field for tracking transcription progress
ALTER TABLE media ADD COLUMN IF NOT EXISTS transcribe_status VARCHAR(32) DEFAULT NULL;

-- Create index for faster status queries
CREATE INDEX IF NOT EXISTS idx_media_transcribe_status ON media(transcribe_status);
CREATE INDEX IF NOT EXISTS idx_media_language ON media(language);

-- Comment on fields
COMMENT ON COLUMN media.draft IS 'Raw transcription from Whisper';
COMMENT ON COLUMN media.transcribe_status IS 'Transcription status: NULL, started_transcribe, finished_transcribe, started_formatting, finished_formatting';
