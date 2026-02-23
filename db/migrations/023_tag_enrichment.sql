-- 023_tag_enrichment.sql
-- Adds last_tag_checked_at to documents for enrichment sweep priority queue.

ALTER TABLE documents
  ADD COLUMN IF NOT EXISTS last_tag_checked_at timestamptz DEFAULT NULL;

CREATE INDEX IF NOT EXISTS idx_documents_last_tag_checked_at
  ON documents (last_tag_checked_at ASC NULLS FIRST);
