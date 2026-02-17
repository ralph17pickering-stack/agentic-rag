# Chat Status Feedback Design

**Date:** 2026-02-17
**Status:** Approved

## Problem

The chat UI shows only "Thinking..." while the LLM works. When tools like vector search, graph search, or deep analysis are invoked, the user has no visibility into what is happening — they just wait.

## Goal

Show real-time status updates in a temporary bubble that changes as work progresses:

1. "Thinking..." → default while waiting
2. Tool invoked → "Searching knowledge base for: \"query\"..."
3. Results returned → "Found 5 chunks for: \"query\""
4. Final response → replaces the status bubble entirely

## Approach: Typed `tool_start` Event + Augmented Result Events

### SSE Event Protocol

**New `tool_start` event** emitted *before* each tool executes:

```json
{"tool_start": {"tool": "retrieve_documents", "query": "revenue figures Q3"}}
{"tool_start": {"tool": "web_search", "query": "latest AI benchmarks"}}
{"tool_start": {"tool": "graph_search", "mode": "global"}}
{"tool_start": {"tool": "graph_search", "mode": "relationship", "entity_a": "OpenAI", "entity_b": "Microsoft"}}
{"tool_start": {"tool": "query_documents_metadata", "question": "which docs mention Q3?"}}
{"tool_start": {"tool": "deep_analysis", "query": "compare revenue trends"}}
```

**Augmented result events** — existing events gain a `query` field:

```json
{"used_sources": [...], "query": "revenue figures Q3"}
{"web_results": [...], "query": "latest AI benchmarks"}
```

`sub_agent_status` is unchanged (already carries phase strings).

## Backend Changes

### `backend/app/services/llm.py`

Before calling `execute_tool`, yield a `ToolEvent(tool_name="tool_start", data={...})` with relevant args extracted per tool:

| Tool | Args surfaced |
|------|--------------|
| `retrieve_documents` | `query` |
| `web_search` | `query` |
| `graph_search` | `mode`, `entity_a`, `entity_b` |
| `query_documents_metadata` | `question` |
| `deep_analysis` | `query` |

### `backend/app/routers/chat.py`

- Add handler for `tool_start` ToolEvents → yield `{"tool_start": {...}}`
- Add `query` field to existing `used_sources` payload
- Add `query` field to existing `web_results` payload

**Scope:** ~30 lines across both files. No new files, no schema changes.

## Frontend Changes

### `useChat.ts`

Replace `deepAnalysisPhase: string | null` with `currentStatus: string | null`.

Status message mapping:

| Event | Status text |
|-------|-------------|
| `tool_start` (retrieve_documents) | `Searching knowledge base for:\n"<query ≤60 chars>"` |
| `tool_start` (web_search) | `Searching the web for:\n"<query>"` |
| `tool_start` (graph_search, global) | `Searching knowledge graph globally...` |
| `tool_start` (graph_search, relationship) | `Tracing relationship between:\n"<entity_a>" and "<entity_b>"` |
| `tool_start` (query_documents_metadata) | `Querying document metadata:\n"<question>"` |
| `tool_start` (deep_analysis) | `Starting deep analysis:\n"<query>"` |
| `used_sources` (N results) | `Found <N> chunk(s) for:\n"<query>"` |
| `web_results` (N results) | `Found <N> web result(s) for:\n"<query>"` |
| `sub_agent_status` (phase string) | Phase string verbatim |
| `sub_agent_status` (done) | `null` |
| First token received | `null` (cleared — response takes over) |

`usedDeepAnalysis` retained for the deep analysis badge.

### `MessageArea.tsx`

- The "Thinking..." / phase bubble renders `currentStatus` with `whitespace-pre-line` so `\n` creates line breaks
- When `currentStatus` is null and still streaming → falls back to "Thinking..."
- Supports 1-3 line status messages naturally

### `ChatLayout.tsx`

- Rename `deepAnalysisPhase` prop/state to `currentStatus` throughout

**Scope:** ~50 lines across three files. No new components.

## Non-Goals

- Persistent activity log / history of steps
- Per-tool icons or colour coding
- Backend controlling status copy (frontend owns all formatting)
