-- Add used_sources JSONB column to messages to track which chunks were retrieved for a response
ALTER TABLE messages ADD COLUMN used_sources JSONB DEFAULT NULL;
