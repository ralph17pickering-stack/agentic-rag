-- 022_blocked_tags.sql
-- Blocked-tags table and RPCs for blocking/unblocking tags.
-- Blocking a tag also strips it from all of the user's documents.

-- ── Table ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS blocked_tags (
    id         uuid        DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id    uuid        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    tag        text        NOT NULL,
    created_at timestamptz DEFAULT now(),
    UNIQUE (user_id, tag)
);

-- ── RLS ──────────────────────────────────────────────────────────────
ALTER TABLE blocked_tags ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own blocked tags"
    ON blocked_tags FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own blocked tags"
    ON blocked_tags FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can delete own blocked tags"
    ON blocked_tags FOR DELETE
    USING (auth.uid() = user_id);

-- ── block_tag RPC ────────────────────────────────────────────────────
-- Adds a tag to the blocklist and strips it from all of the caller's
-- documents. Returns the number of documents updated.
CREATE OR REPLACE FUNCTION block_tag(p_tag text)
RETURNS integer
LANGUAGE plpgsql
SECURITY INVOKER
AS $$
DECLARE
    v_count integer;
BEGIN
    INSERT INTO blocked_tags (user_id, tag)
    VALUES (auth.uid(), p_tag)
    ON CONFLICT DO NOTHING;

    UPDATE documents
    SET    topics = array_remove(topics, p_tag)
    WHERE  topics @> ARRAY[p_tag];

    GET DIAGNOSTICS v_count = ROW_COUNT;
    RETURN v_count;
END;
$$;

-- ── unblock_tag RPC ──────────────────────────────────────────────────
-- Removes a tag from the blocklist. Does not re-add the tag to any
-- documents.
CREATE OR REPLACE FUNCTION unblock_tag(p_tag text)
RETURNS void
LANGUAGE plpgsql
SECURITY INVOKER
AS $$
BEGIN
    DELETE FROM blocked_tags
    WHERE  user_id = auth.uid()
      AND  tag = p_tag;
END;
$$;
