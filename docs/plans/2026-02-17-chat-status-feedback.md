# Chat Status Feedback Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Show real-time tool status in the chat UI — "Thinking..." transitions to tool-specific messages (with query text) on invocation, then result counts on completion, then disappears when the final response arrives.

**Architecture:** New `tool_start` SSE event emitted before each tool call in `llm.py`; existing `used_sources`/`web_results` events gain a `query` field; frontend `useChat.ts` maps these events to a `currentStatus` string that `MessageArea` renders with `whitespace-pre-line`.

**Tech Stack:** Python/FastAPI (SSE), React/TypeScript (hooks + components), sse-starlette

---

## Context

Key files (read before making any change):
- `app/backapp/frontend/app/services/llm.py` — async generator, emits `ToolEvent` objects. The tool execution loop has **two paths**:
  - **Text tool calls path** (lines 180–203): for local LLMs that emit tool calls as text
  - **Native tool calls path** (lines 215–246): for OpenAI-compatible APIs
  Both paths must emit `tool_start` before `_execute_tool`.
- `app/backapp/frontend/app/routers/chat.py` — `event_generator()` (lines 80–102) fans out `ToolEvent` objects to SSE payloads.
- `app/frontend/src/hooks/useChat.ts` — SSE consumer. State: `deepAnalysisPhase`, `usedDeepAnalysis`.
- `app/frontend/src/components/chat/MessageArea.tsx` — renders the status bubble (line 61).
- `app/frontend/src/components/chat/ChatLayout.tsx` — passes `deepAnalysisPhase` prop to `MessageArea` (lines 145, 236).

---

## Task 1: Emit `tool_start` ToolEvent in llm.py

**Files:**
- Modify: `app/backapp/frontend/app/services/llm.py`

No tests for this task — it's an async generator tested via integration. Verify by watching backend logs / SSE stream in Task 5.

**Step 1: Add `tool_start` yield before each `_execute_tool` call — text tool calls path (lines 182–201)**

In the text tool call block (around line 185), before `result = await _execute_tool(...)`:

```python
# Yield tool_start event before executing
tool_start_data: dict = {"tool": tc["name"]}
if tc["name"] == "retrieve_documents":
    tool_start_data["query"] = tc["arguments"].get("query", "")
elif tc["name"] == "web_search":
    tool_start_data["query"] = tc["arguments"].get("query", "")
elif tc["name"] == "graph_search":
    tool_start_data["mode"] = tc["arguments"].get("mode", "global")
    if tc["arguments"].get("entity_a"):
        tool_start_data["entity_a"] = tc["arguments"]["entity_a"]
    if tc["arguments"].get("entity_b"):
        tool_start_data["entity_b"] = tc["arguments"]["entity_b"]
elif tc["name"] == "query_documents_metadata":
    tool_start_data["question"] = tc["arguments"].get("question", "")
elif tc["name"] == "deep_analysis":
    tool_start_data["query"] = tc["arguments"].get("query", "")
yield ToolEvent(tool_name="tool_start", data=tool_start_data)
```

Place this block **before** `status_events.clear()` and `result = await _execute_tool(...)` on the text-path (the inner `for tc in text_tool_calls:` loop at ~line 182).

**Step 2: Add `tool_start` yield before each `_execute_tool` call — native tool calls path (lines 215–246)**

In the native tool call block (inner `for tool_call in choice.message.tool_calls:` loop), before `status_events.clear()` and `result = await _execute_tool(...)`:

```python
# Yield tool_start event before executing
tool_start_data: dict = {"tool": name}
if name == "retrieve_documents":
    tool_start_data["query"] = args.get("query", "")
elif name == "web_search":
    tool_start_data["query"] = args.get("query", "")
elif name == "graph_search":
    tool_start_data["mode"] = args.get("mode", "global")
    if args.get("entity_a"):
        tool_start_data["entity_a"] = args["entity_a"]
    if args.get("entity_b"):
        tool_start_data["entity_b"] = args["entity_b"]
elif name == "query_documents_metadata":
    tool_start_data["question"] = args.get("question", "")
elif name == "deep_analysis":
    tool_start_data["query"] = args.get("query", "")
yield ToolEvent(tool_name="tool_start", data=tool_start_data)
```

**Step 3: Also add `query` to retrieve_documents and web_search result ToolEvents**

In the text-path, find where `ToolEvent(tool_name="retrieve_documents", ...)` and `ToolEvent(tool_name="web_search", ...)` are yielded and add the query. Change:

```python
# text path, retrieve_documents (around line 195):
yield ToolEvent(tool_name="retrieve_documents", data={"sources": sources})
# becomes:
yield ToolEvent(tool_name="retrieve_documents", data={"sources": sources, "query": tc["arguments"].get("query", "")})

# text path, web_search (around line 191):
yield ToolEvent(tool_name="web_search", data=result)
# already contains full result dict; add query:
result_with_query = {**result, "query": tc["arguments"].get("query", "")}
yield ToolEvent(tool_name="web_search", data=result_with_query)
tool_result_str = result.get("answer", "")
```

In the native-path, same changes for lines ~229–234:

```python
# native path, web_search (around line 229):
yield ToolEvent(tool_name="web_search", data={**result, "query": args.get("query", "")})
tool_result_str = result.get("answer", "")

# native path, retrieve_documents (around line 232):
sources = result.get("citation_sources", [])
yield ToolEvent(tool_name="retrieve_documents", data={"sources": sources, "query": args.get("query", "")})
```

**Step 4: Commit**

```bash
cd /home/ralph/dev/agentic-rag
git add app/backapp/frontend/app/services/llm.py
git commit -m "feat: emit tool_start ToolEvent before each tool call"
```

---

## Task 2: Handle `tool_start` in chat.py + pass query through result events

**Files:**
- Modify: `app/backapp/frontend/app/routers/chat.py`

**Step 1: Add `tool_start` handler in `event_generator()`**

In the `async for event in stream_chat_completion(...)` block (lines 90–102), add a new `elif` branch after the existing handlers:

```python
elif isinstance(event, ToolEvent) and event.tool_name == "tool_start":
    yield {"data": json.dumps({"tool_start": event.data})}
```

**Step 2: Add `query` to `used_sources` payload**

Change line ~100:
```python
# Before:
yield {"data": json.dumps({"used_sources": sources})}
# After:
query = event.data.get("query", "")
yield {"data": json.dumps({"used_sources": sources, "query": query})}
```

**Step 3: Add `query` to `web_results` payload**

Change line ~96:
```python
# Before:
results = event.data.get("results", [])
accumulated_web_results.extend(results)
yield {"data": json.dumps({"web_results": results})}
# After:
results = event.data.get("results", [])
accumulated_web_results.extend(results)
query = event.data.get("query", "")
yield {"data": json.dumps({"web_results": results, "query": query})}
```

**Step 4: Verify backend starts without errors**

```bash
cd /home/ralph/dev/agentic-rag/backend
source venv/bin/activate
python -c "from app.routers.chat import router; print('OK')"
```
Expected: `OK`

**Step 5: Commit**

```bash
git add app/backapp/frontend/app/routers/chat.py
git commit -m "feat: forward tool_start SSE events and add query to result payloads"
```

---

## Task 3: Add `formatToolStatus` utility + unit test

This is the only pure function worth unit testing. It maps raw SSE `tool_start` / result events to human-readable status strings.

**Files:**
- Create: `app/frontend/src/lib/toolStatus.ts`
- Create: `app/frontend/src/lib/toolStatus.test.ts`

**Step 1: Write the failing tests**

Create `app/frontend/src/lib/toolStatus.test.ts`:

```typescript
import { describe, it, expect } from "vitest"
import { formatToolStart, formatToolResult } from "./toolStatus"

describe("formatToolStart", () => {
  it("retrieve_documents with query", () => {
    expect(formatToolStart({ tool: "retrieve_documents", query: "revenue figures Q3" }))
      .toBe('Searching knowledge base for:\n"revenue figures Q3"')
  })

  it("retrieve_documents truncates long query", () => {
    const long = "a".repeat(80)
    const result = formatToolStart({ tool: "retrieve_documents", query: long })
    expect(result).toContain("Searching knowledge base for:")
    expect(result.split("\n")[1].length).toBeLessThanOrEqual(63) // 60 + quotes + ellipsis
  })

  it("web_search with query", () => {
    expect(formatToolStart({ tool: "web_search", query: "latest AI benchmarks" }))
      .toBe('Searching the web for:\n"latest AI benchmarks"')
  })

  it("graph_search global mode", () => {
    expect(formatToolStart({ tool: "graph_search", mode: "global" }))
      .toBe("Searching knowledge graph globally...")
  })

  it("graph_search relationship mode", () => {
    expect(formatToolStart({ tool: "graph_search", mode: "relationship", entity_a: "OpenAI", entity_b: "Microsoft" }))
      .toBe('Tracing relationship between:\n"OpenAI" and "Microsoft"')
  })

  it("query_documents_metadata", () => {
    expect(formatToolStart({ tool: "query_documents_metadata", question: "how many PDFs?" }))
      .toBe('Querying document metadata:\n"how many PDFs?"')
  })

  it("deep_analysis", () => {
    expect(formatToolStart({ tool: "deep_analysis", query: "compare revenue trends" }))
      .toBe('Starting deep analysis:\n"compare revenue trends"')
  })

  it("unknown tool", () => {
    expect(formatToolStart({ tool: "unknown_tool" })).toBe("Working...")
  })
})

describe("formatToolResult", () => {
  it("retrieve_documents with results and query", () => {
    expect(formatToolResult("retrieve_documents", 5, "revenue Q3"))
      .toBe('Found 5 chunk(s) for:\n"revenue Q3"')
  })

  it("retrieve_documents with no query", () => {
    expect(formatToolResult("retrieve_documents", 3, ""))
      .toBe("Found 3 chunk(s)")
  })

  it("web_results with query", () => {
    expect(formatToolResult("web_search", 4, "AI news"))
      .toBe('Found 4 web result(s) for:\n"AI news"')
  })
})
```

**Step 2: Run tests to verify they fail**

```bash
cd /home/ralph/dev/agentic-rag/frontend
npx vitest run src/lib/toolStatus.test.ts 2>&1 | head -20
```
Expected: FAIL — "Cannot find module './toolStatus'"

**Step 3: Implement `toolStatus.ts`**

Create `app/frontend/src/lib/toolStatus.ts`:

```typescript
const MAX_QUERY_LEN = 60

function truncate(s: string): string {
  return s.length > MAX_QUERY_LEN ? s.slice(0, MAX_QUERY_LEN) + "…" : s
}

export interface ToolStartData {
  tool: string
  query?: string
  question?: string
  mode?: string
  entity_a?: string
  entity_b?: string
}

export function formatToolStart(data: ToolStartData): string {
  const q = (s: string | undefined) => `"${truncate(s ?? "")}"`

  switch (data.tool) {
    case "retrieve_documents":
      return `Searching knowledge base for:\n${q(data.query)}`
    case "web_search":
      return `Searching the web for:\n${q(data.query)}`
    case "graph_search":
      if (data.mode === "relationship" && data.entity_a && data.entity_b) {
        return `Tracing relationship between:\n"${data.entity_a}" and "${data.entity_b}"`
      }
      return "Searching knowledge graph globally..."
    case "query_documents_metadata":
      return `Querying document metadata:\n${q(data.question)}`
    case "deep_analysis":
      return `Starting deep analysis:\n${q(data.query)}`
    default:
      return "Working..."
  }
}

export function formatToolResult(tool: string, count: number, query: string): string {
  switch (tool) {
    case "retrieve_documents":
      return query
        ? `Found ${count} chunk(s) for:\n"${truncate(query)}"`
        : `Found ${count} chunk(s)`
    case "web_search":
      return query
        ? `Found ${count} web result(s) for:\n"${truncate(query)}"`
        : `Found ${count} web result(s)`
    default:
      return `Found ${count} result(s)`
  }
}
```

**Step 4: Run tests to verify they pass**

```bash
cd /home/ralph/dev/agentic-rag/frontend
npx vitest run src/lib/toolStatus.test.ts
```
Expected: All tests PASS

**Step 5: Commit**

```bash
git add app/frontend/src/lib/toolStatus.ts app/frontend/src/lib/toolStatus.test.ts
git commit -m "feat: add toolStatus formatter with tests"
```

---

## Task 4: Update `useChat.ts` — replace `deepAnalysisPhase` with `currentStatus`

**Files:**
- Modify: `app/frontend/src/hooks/useChat.ts`

**Step 1: Replace state declaration (line 14)**

```typescript
// Before:
const [deepAnalysisPhase, setDeepAnalysisPhase] = useState<string | null>(null)
// After:
const [currentStatus, setCurrentStatus] = useState<string | null>(null)
```

**Step 2: Update reset in `sendMessage` (line 58)**

```typescript
// Before:
setDeepAnalysisPhase(null)
// After:
setCurrentStatus(null)
```

**Step 3: Add import for toolStatus helpers (top of file, after existing imports)**

```typescript
import { formatToolStart, formatToolResult } from "@/lib/toolStatus"
```

**Step 4: Replace SSE event handlers (lines 97–128)**

Replace the entire block from `if (data.web_results)` through `} else if (data.token)` with:

```typescript
if (data.tool_start) {
  setCurrentStatus(formatToolStart(data.tool_start))
}
if (data.web_results) {
  const query: string = data.query ?? ""
  setWebResults(data.web_results)
  setCurrentStatus(formatToolResult("web_search", data.web_results.length, query))
}
if (data.used_sources) {
  const query: string = data.query ?? ""
  setUsedSources(prev => [...prev, ...data.used_sources])
  setCurrentStatus(formatToolResult("retrieve_documents", data.used_sources.length, query))
}
if (data.sub_agent_status) {
  if (data.sub_agent_status.done) {
    setCurrentStatus(null)
    setUsedDeepAnalysis(true)
  } else if (data.sub_agent_status.phase) {
    setCurrentStatus(data.sub_agent_status.phase)
    setUsedDeepAnalysis(true)
  }
}
if (data.done) {
  if (data.message) {
    setMessages(prev => [...prev, data.message])
    if (data.message?.used_sources) {
      setUsedSources(data.message.used_sources)
    } else {
      setUsedSources([])
    }
  }
  if (data.new_title && onTitleUpdate) {
    onTitleUpdate(tid, data.new_title)
  }
} else if (data.token) {
  fullContent += data.token
  setStreamingContent(fullContent)
  // Clear status on first token — response has started
  if (fullContent.length === data.token.length) {
    setCurrentStatus(null)
  }
}
```

**Step 5: Update `finally` block (line 139)**

```typescript
// Before:
setDeepAnalysisPhase(null)
// After:
setCurrentStatus(null)
```

**Step 6: Update return value (line 156)**

```typescript
// Before:
deepAnalysisPhase,
// After:
currentStatus,
```

**Step 7: TypeScript check**

```bash
cd /home/ralph/dev/agentic-rag/frontend
npx tsc --noEmit 2>&1 | head -30
```
Expected: No errors (or only pre-existing unrelated errors).

**Step 8: Commit**

```bash
git add app/frontend/src/hooks/useChat.ts
git commit -m "feat: replace deepAnalysisPhase with currentStatus in useChat"
```

---

## Task 5: Update `MessageArea.tsx` — render `currentStatus`

**Files:**
- Modify: `app/frontend/src/components/chat/MessageArea.tsx`

**Step 1: Update props interface (lines 4–10)**

```typescript
// Before:
interface MessageAreaProps {
  messages: Message[]
  streamingContent: string
  isStreaming: boolean
  deepAnalysisPhase?: string | null
  usedDeepAnalysis?: boolean
}
// After:
interface MessageAreaProps {
  messages: Message[]
  streamingContent: string
  isStreaming: boolean
  currentStatus?: string | null
  usedDeepAnalysis?: boolean
}
```

**Step 2: Update function signature (line 12)**

```typescript
// Before:
export function MessageArea({ messages, streamingContent, isStreaming, deepAnalysisPhase, usedDeepAnalysis }: MessageAreaProps) {
// After:
export function MessageArea({ messages, streamingContent, isStreaming, currentStatus, usedDeepAnalysis }: MessageAreaProps) {
```

**Step 3: Update the status bubble (line 58–64)**

```tsx
// Before:
{isStreaming && !streamingContent && (
  <div className="flex justify-start">
    <div className="rounded-lg bg-muted px-4 py-2">
      <span className="animate-pulse">{deepAnalysisPhase || "Thinking..."}</span>
    </div>
  </div>
)}
// After:
{isStreaming && !streamingContent && (
  <div className="flex justify-start">
    <div className="rounded-lg bg-muted px-4 py-2">
      <span className="animate-pulse whitespace-pre-line">{currentStatus || "Thinking..."}</span>
    </div>
  </div>
)}
```

**Step 4: TypeScript check**

```bash
cd /home/ralph/dev/agentic-rag/frontend
npx tsc --noEmit 2>&1 | head -30
```

**Step 5: Commit**

```bash
git add app/frontend/src/components/chat/MessageArea.tsx
git commit -m "feat: render currentStatus in MessageArea status bubble"
```

---

## Task 6: Update `ChatLayout.tsx` — rename prop references

**Files:**
- Modify: `app/frontend/src/components/chat/ChatLayout.tsx`

**Step 1: Update destructuring from `useChat` (line 40)**

```typescript
// Before:
deepAnalysisPhase,
// After:
currentStatus,
```

**Step 2: Update both `<MessageArea>` usages (lines 141–147 and 232–238)**

In both places, change:
```tsx
deepAnalysisPhase={deepAnalysisPhase}
```
to:
```tsx
currentStatus={currentStatus}
```

**Step 3: TypeScript check**

```bash
cd /home/ralph/dev/agentic-rag/frontend
npx tsc --noEmit 2>&1 | head -30
```
Expected: No errors.

**Step 4: Commit**

```bash
git add app/frontend/src/components/chat/ChatLayout.tsx
git commit -m "feat: wire currentStatus prop through ChatLayout"
```

---

## Task 7: Browser verification

**Prerequisite:** Backend and frontend dev servers are running.
- Backend: `cd /home/ralph/dev/agentic-rag/backend && source venv/bin/activate && uvicorn app.main:app --reload --port 8001`
- Frontend: `cd /home/ralph/dev/agentic-rag/frontend && npm run dev`

**Step 1: Open browser to `http://localhost:5173` and log in with test credentials**
- Email: `test@agentic-rag.dev`
- Password: `TestPass123!`

**Step 2: Test retrieve_documents status**

Send a message that will trigger a knowledge base search (requires at least one uploaded document):
> "What are the main topics in my documents?"

Observe:
- [ ] "Thinking..." appears immediately
- [ ] Changes to `Searching knowledge base for:\n"What are the main topics..."` (or similar query the LLM generates)
- [ ] Changes to `Found N chunk(s) for:\n"..."` when results arrive
- [ ] Status disappears and response text begins streaming

**Step 3: Test web_search status** (requires web search to be enabled)

Send:
> "What is the latest news about AI?"

Observe:
- [ ] "Thinking..." → "Searching the web for:\n\"...\""
- [ ] → "Found N web result(s) for:\n\"...\""
- [ ] → response streams in

**Step 4: Verify no console errors**

Open browser devtools console — confirm no TypeScript/runtime errors.

**Step 5: Commit verification note**

```bash
git tag -a v-status-feedback -m "chat status feedback feature complete and browser-verified"
```

---

## Done Criteria

- [ ] All TypeScript checks pass with no new errors
- [ ] `toolStatus.test.ts` tests pass
- [ ] "Thinking..." transitions through tool-specific status messages during a chat request
- [ ] Status disappears when first token arrives (response takes over)
- [ ] Multi-line status messages render correctly (no broken layout)
- [ ] `usedDeepAnalysis` badge still appears when deep analysis was used
