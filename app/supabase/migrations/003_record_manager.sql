-- Record Manager: add content hashing for deduplication

ALTER TABLE documents ADD COLUMN content_hash TEXT;
CREATE UNIQUE INDEX idx_documents_user_content_hash ON documents(user_id, content_hash) WHERE content_hash IS NOT NULL;
CREATE INDEX idx_documents_user_filename ON documents(user_id, filename);

ALTER TABLE chunks ADD COLUMN content_hash TEXT;
CREATE INDEX idx_chunks_document_content_hash ON chunks(document_id, content_hash) WHERE content_hash IS NOT NULL;
