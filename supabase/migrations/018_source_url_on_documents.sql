-- Add source_url column to store original URL for web-ingested documents
ALTER TABLE documents ADD COLUMN source_url TEXT DEFAULT NULL;
