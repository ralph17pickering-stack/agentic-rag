# Agentic Tag Tool — Design

**Date:** 2026-02-19
**Status:** Approved
**PROGRESS.md item:** Phase 4 — Agentic tag tool

---

## Overview

A new `manage_tags` tool registered in the existing tool registry. Accessible via the chat interface. The LLM constructs query parameters; the tool handles all document discovery and mutation internally. Doc IDs never pass through the LLM.

---

## Scope

**In scope:**
- `find_and_tag` — semantic + keyword search, apply a tag to all matching documents
- `delete_tag` — remove a tag from all documents that have it
- `merge_tags` — rename a tag across all documents (remove old, add new)
- Preview-first (dry_run) workflow — LLM always previews before executing

**Out of scope:**
- Frontend changes (no new UI components required)
- Bulk operations outside the chat interface
- Tag creation UI / tag management panel

---

## Architecture

**New files:**
- `app/backend/app/tools/manage_tags.py` — autodiscovered by tool registry
- `db/migrations/021_tag_management_rpcs.sql` — write RPCs

**Unchanged:** frontend, chat router, LLM service, tool registry loader.

---

## Tool Definition

```python
{
    "name": "manage_tags",
    "description": (
        "Find documents by semantic+keyword search and apply a tag, "
        "delete a tag from all documents, or rename/merge a tag across all documents. "
        "ALWAYS call with dry_run=true first to show the user a preview of changes, "
        "then ask for confirmation before calling with dry_run=false to execute."
    ),
    "parameters": {
        "operation":      "find_and_tag | delete_tag | merge_tags",
        "dry_run":        "boolean — true=preview only, false=execute (default: true)",
        "query":          "[find_and_tag] search string for semantic+keyword document search",
        "tag_to_apply":   "[find_and_tag] tag to add to matching documents",
        "tag_to_delete":  "[delete_tag] tag to remove from all documents",
        "tag_from":       "[merge_tags] tag to rename from",
        "tag_to":         "[merge_tags] tag to rename to",
    }
}
```

---

## Data Flow

### `find_and_tag`

**dry_run=true:**
1. Call `retrieve_chunks(query, user_token, mode="hybrid", top_k=10)`
2. Deduplicate chunks → unique document IDs
3. Fetch document titles via Supabase client
4. Return: `"Found ~47 documents matching 'climate change'. Sample: Doc A, Doc B, Doc C… Would apply tag 'climate' to all matching documents. Shall I proceed?"`

**dry_run=false:**
1. Call `retrieve_chunks(query, user_token, mode="hybrid", top_k=10000)`
2. Deduplicate → unique document IDs
3. Call `apply_tag_to_docs(p_tag, p_doc_ids)` RPC
4. Return: `"Tagged 47 documents with 'climate'."`

> The LLM passes identical parameters both times. The tool controls scope via `top_k` internally.

---

### `delete_tag`

**dry_run=true:**
1. Supabase query: `documents.select("id, title").contains("topics", [tag_to_delete])`
2. Return: `"Tag 'enviroment' appears on 6 documents: Doc A, Doc B… Would remove it from all. Shall I proceed?"`

**dry_run=false:**
1. Same query to get all doc IDs
2. Call `delete_tag_from_docs(p_tag)` RPC
3. Return: `"Removed tag 'enviroment' from 6 documents."`

---

### `merge_tags`

**dry_run=true:**
1. Supabase query: docs containing `tag_from`
2. Return: `"Would rename 'enviroment' → 'environment' on 6 documents: Doc A, Doc B… Shall I proceed?"`

**dry_run=false:**
1. Same query to confirm scope
2. Call `merge_tags(p_from, p_to)` RPC
3. Return: `"Renamed tag on 6 documents."`

---

## Database RPCs

All RPCs use `SECURITY INVOKER` — they run as the calling user and inherit RLS, so users can only affect their own documents.

```sql
-- Apply a tag to a list of documents (skips docs already having the tag)
apply_tag_to_docs(p_tag text, p_doc_ids uuid[]) → integer  -- returns count affected

-- Remove a tag from all of the user's documents that have it
delete_tag_from_docs(p_tag text) → integer

-- Rename a tag: remove p_from, add p_to (skips docs already having p_to)
merge_tags(p_from text, p_to text) → integer
```

---

## Error Handling

| Scenario | Behaviour |
|----------|-----------|
| No results found (dry_run) | "No documents found matching '{query}'. Try a broader search term." |
| Tag already applied to some docs | Skip silently; report "Tagged 43 (4 already had this tag)." |
| `tag_from` not found (merge_tags) | "No documents have tag '{tag_from}'." — abort, no confirmation needed |
| `tag_to` == `tag_from` (merge_tags) | "Source and target tags are identical." — abort immediately |
| Missing required parameters | Descriptive error string; LLM asks user to clarify |
| DB failure | "Tag operation failed. No changes were made." — safe, no partial state |

---

## Testing

1. **find_and_tag dry_run** — chat: "Find docs about climate change and tag them 'climate'" → preview shown, no DB changes
2. **find_and_tag execute** — confirm → verify all matching docs have 'climate' in topics
3. **delete_tag dry_run** → preview shows affected docs, no changes
4. **delete_tag execute** → tag removed from all docs
5. **merge_tags dry_run** → shows rename preview
6. **merge_tags execute** → old tag gone, new tag applied across all docs
7. **Missing tag** — merge non-existent tag → graceful "not found" message
8. **Scale** — 100+ docs — verify execute applies to all, not capped at preview size
