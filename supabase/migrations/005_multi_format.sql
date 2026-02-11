-- Widen file_type CHECK constraint to support PDF, DOCX, CSV, HTML
ALTER TABLE documents DROP CONSTRAINT IF EXISTS documents_file_type_check;
ALTER TABLE documents ADD CONSTRAINT documents_file_type_check
    CHECK (file_type IN ('txt', 'md', 'pdf', 'docx', 'csv', 'html'));
