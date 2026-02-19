-- 021_tag_management_rpcs.sql
-- Tag management RPCs for the manage_tags tool.
-- All functions use SECURITY INVOKER so they run as the calling user
-- and inherit RLS — users can only affect their own documents.

-- Apply a tag to a list of documents (skips docs that already have it).
-- Returns the count of documents actually updated.
CREATE OR REPLACE FUNCTION apply_tag_to_docs(
    p_tag     text,
    p_doc_ids uuid[]
)
RETURNS integer
LANGUAGE plpgsql
SECURITY INVOKER
AS $$
DECLARE
    v_count integer;
BEGIN
    UPDATE documents
    SET    topics = array_append(topics, p_tag)
    WHERE  id = ANY(p_doc_ids)
      AND  NOT (topics @> ARRAY[p_tag]);

    GET DIAGNOSTICS v_count = ROW_COUNT;
    RETURN v_count;
END;
$$;

-- Remove a tag from all of the calling user's documents that have it.
-- Returns the count of documents updated.
CREATE OR REPLACE FUNCTION delete_tag_from_docs(
    p_tag text
)
RETURNS integer
LANGUAGE plpgsql
SECURITY INVOKER
AS $$
DECLARE
    v_count integer;
BEGIN
    UPDATE documents
    SET    topics = array_remove(topics, p_tag)
    WHERE  topics @> ARRAY[p_tag];

    GET DIAGNOSTICS v_count = ROW_COUNT;
    RETURN v_count;
END;
$$;

-- Rename a tag: remove p_from and add p_to on all docs that have p_from.
-- Skips docs that already have p_to to avoid duplicates.
-- Returns the count of documents updated.
CREATE OR REPLACE FUNCTION merge_tags(
    p_from text,
    p_to   text
)
RETURNS integer
LANGUAGE plpgsql
SECURITY INVOKER
AS $$
DECLARE
    v_count integer;
BEGIN
    UPDATE documents
    SET    topics = array_append(array_remove(topics, p_from), p_to)
    WHERE  topics @> ARRAY[p_from]
      AND  NOT (topics @> ARRAY[p_to]);

    GET DIAGNOSTICS v_count = ROW_COUNT;
    RETURN v_count;
END;
$$;
