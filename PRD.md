# Agentic RAG Masterclass - PRD

## What We're Building

A RAG application with two interfaces:
1. **Chat** (default view) - Threaded conversations with retrieval-augmented responses
2. **Ingestion** - Upload files manually, track processing, manage documents

This is **not** an automated pipeline with connectors. Files are uploaded manually via drag-and-drop. Configuration is via environment variables, no admin UI.

## Target Users

Technically-minded people who want to build production RAG systems using AI coding tools (Claude Code, Cursor, etc.). They don't need to know Python or React - that's the AI's job.

**They need to understand:**
- RAG concepts deeply (chunking, embeddings, retrieval, reranking)
- Codebase structure (what sits where, how pieces connect)
- How to direct AI to build what they need
- How to direct AI to fix things when they break

## Scope

### In Scope
- ✅ Document ingestion and processing
- ✅ Vector search with pgvector
- ✅ Hybrid search (keyword + vector)
- ✅ Reranking
- ✅ Metadata extraction
- ✅ Record management (deduplication)
- ✅ Multi-format support (PDF, DOCX, HTML, Markdown)
- ✅ Text-to-SQL tool
- ✅ Web search fallback
- ✅ Sub-agents with isolated context
- ✅ Chat with threads and memory
- ✅ Streaming responses
- ✅ Auth with RLS

### Out of Scope
- ❌ Knowledge graphs / GraphRAG
- ❌ Code execution / sandboxing
- ❌ Image/audio/video processing
- ❌ Fine-tuning
- ❌ Multi-tenant admin features
- ❌ Billing/payments
- ❌ Admin UI (config via env vars)

## Stack

| Layer | Choice |
|-------|--------|
| Frontend | React + TypeScript + Vite + Tailwind + shadcn/ui |
| Backend | Python + FastAPI |
| Database | Supabase (Postgres + pgvector + Auth + Storage + Realtime) |
| LLM (Module 1) | OpenAI Responses API (managed threads + file_search) |
| LLM (Module 2+) | Any OpenAI-compatible endpoint (OpenRouter, Ollama, LM Studio, etc.) |
| Observability | LangSmith |

## Constraints

- No LLM frameworks - raw OpenAI SDK using the standard Chat Completions API (OpenAI-compatible), Pydantic for structured outputs
- Row-Level Security on all tables - users only see their own data
- Streaming chat via SSE
- Ingestion status via Supabase Realtime

---

## Module 1: The App Shell + Observability

**Build:** Auth, chat UI, OpenAI Responses API (manages threads + file_search), LangSmith tracing

**Learn:** What RAG is, why managed RAG exists, its limitations (OpenAI handles memory and retrieval - black box)

**Note:** The Responses API is OpenAI-specific. It provides managed threads and built-in file search, but locks you into OpenAI. Module 2 transitions to the standard Chat Completions API for provider flexibility.

---

## Architectural Decision: Module 1 → Module 2 Transition

At the end of Module 1, you have a working chat app using OpenAI's **Responses API**—a managed solution where OpenAI handles threads, memory, and file search. In Module 2, you switch to the standard **Chat Completions API** to support any OpenAI-compatible provider (OpenRouter, Ollama, LM Studio, etc.).

**The decision you need to make:** What do you do with the Responses API code? Here are two common approaches, but you're not limited to these—come up with your own if it makes sense for your use case.

| Option | Approach | Pros | Cons |
|--------|----------|------|------|
| **A: Replace** | Remove Responses API code entirely, rebuild on Chat Completions | Clean codebase, single pattern, easier to maintain | Lose the ability to use OpenAI's managed RAG |
| **B: Dual Support** | Keep Responses API alongside Chat Completions, configurable per request | Flexibility to use either approach, compare them side-by-side | More complex codebase, two patterns to understand |


---

## Module 2: BYO Retrieval + Memory

**Prerequisites:** Complete the architectural decision above.

**Build:** Ingestion UI, file storage, chunking → embedding → pgvector, retrieval tool, Chat Completions API integration (OpenRouter/Ollama/LM Studio), chat history storage (stateless API - you manage memory now), realtime ingestion status

**Learn:** Chunking, embeddings, vector search, tool calling, relevance thresholds, managing conversation history, **steering AI agents through architectural refactoring**

---

## Module 3: Record Manager

**Build:** Content hashing, detect changes, only process what's new/modified

**Learn:** Why naive ingestion duplicates, incremental updates

---

## Module 4: Metadata Extraction

**Build:** LLM extracts structured metadata, filter retrieval by metadata

**Learn:** Structured extraction, schema design, metadata-enhanced retrieval

---

## Module 5: Multi-Format Support

**Build:** PDF/DOCX/HTML/Markdown via docling, cascade deletes

**Learn:** Document parsing challenges, format considerations

---

## Module 6: Hybrid Search & Reranking

**Build:** Keyword + vector search, RRF combination, reranking

**Learn:** Why vector alone isn't enough, hybrid strategies, reranking

---

## Module 7: Additional Tools

**Build:** Text-to-SQL tool (query structured data), web search fallback (when docs don't have the answer)

**Learn:** Multi-tool agents, routing between structured/unstructured data, graceful fallbacks, attribution for trust

---

## Module 8: Sub-Agents

**Build:** Detect full-document scenarios, spawn isolated sub-agent with its own tools, nested tool call display in UI, show reasoning from both main agent and sub-agents

**Learn:** Context management, agent delegation, hierarchical agent display, when to isolate

## Module 8A: Delegation Policy Spec (Implementation-Ready)

### 1) Policy Objectives (priority order)
Delegation decisions MUST optimize in this order:
1. **Answer correctness & evidence coverage**
2. **Security/compliance** (RLS, tool/data boundaries)
3. **Latency SLO adherence**
4. **Cost/token control**
5. **User transparency** (clear explanation of delegation)

If objectives conflict, higher-priority objective wins.

### 2) Delegation Decision Contract

#### 2.1 Input Schema (`DelegationPolicyInput`)
```json
{
  "request_id": "string",
  "user_id": "uuid",
  "thread_id": "uuid",
  "query": "string",
  "query_intent": "fact_lookup | doc_summary | compare_docs | evidence_trace | exploratory | procedural",
  "retrieval_stats": {
    "top_score": 0.0,
    "score_spread": 0.0,
    "candidate_count": 0,
    "docs_hit_count": 0
  },
  "doc_scope": {
    "target_doc_ids": ["uuid"],
    "estimated_tokens": 0,
    "requires_full_document": false,
    "multi_document": false
  },
  "conversation_state": {
    "attempt_index": 1,
    "prior_failures": 0,
    "user_requested_deep_mode": false
  },
  "runtime_budget": {
    "max_total_latency_ms": 25000,
    "remaining_latency_ms": 25000,
    "max_total_tokens": 24000,
    "remaining_tokens": 24000,
    "max_subagent_cost_usd": 0.08
  },
  "risk_flags": {
    "sensitive_domain": false,
    "restricted_tools_only": true,
    "compliance_mode": "normal | strict"
  },
  "system_health": {
    "degraded_mode": false,
    "subagent_queue_depth": 0,
    "active_subagents": 0
  }
}
```

#### 2.2 Output Schema (`DelegationPolicyOutput`)
```json
{
  "decision": "delegate | no_delegate | defer",
  "reason_codes": [
    "FULL_DOC_REQUIRED",
    "LOW_RETRIEVAL_CONFIDENCE"
  ],
  "selected_profile": "doc_reader | comparator | evidence_builder | web_verifier",
  "tool_scope": ["retrieve_documents", "query_metadata", "web_search"],
  "budget_allocation": {
    "max_child_latency_ms": 15000,
    "max_child_tokens": 8000,
    "max_child_cost_usd": 0.03,
    "max_child_turns": 3
  },
  "expected_artifacts": [
    "answer_summary",
    "citations",
    "uncertainty_notes"
  ],
  "fallback_plan": "main_agent_synthesis | reduced_profile | abstain_with_guidance"
}
```

### 3) Trigger Matrix

#### 3.1 Hard Gates (all must pass)
- User authorization verified for all target documents.
- Remaining latency/tokens/cost budget above minimum threshold.
- System not in circuit-breaker state.
- Required tools healthy.

If any hard gate fails → `decision = no_delegate`.

#### 3.2 Positive Triggers (any can trigger delegation)
- Query intent is `doc_summary`, `compare_docs`, or `evidence_trace`.
- `doc_scope.requires_full_document = true`.
- Retrieval confidence below threshold (`top_score < 0.62`).
- Ambiguous retrieval (`score_spread < 0.08` with `candidate_count >= 6`).
- Multi-document synthesis needed (`multi_document = true`).
- User explicitly requests deep analysis.
- Prior main-agent attempt failed (`prior_failures >= 1`).

#### 3.3 Negative Triggers (force no delegation)
- Intent is simple `fact_lookup` with high confidence (`top_score >= 0.78` and `score_spread >= 0.15`).
- System degraded mode enabled.
- Active subagent limit reached.
- Remaining latency below minimum child budget.

### 4) Default Thresholds & Limits (config-driven)
```yaml
subagents:
  enabled: true
  max_per_request: 2
  max_recursion_depth: 1
  child_timeout_ms: 15000
  child_max_turns: 3
  child_retry_count: 1
  child_retry_backoff_ms: 750
  circuit_breaker:
    failure_rate_threshold: 0.35
    window_requests: 50
    cooldown_seconds: 300

policy_thresholds:
  low_retrieval_confidence_top_score: 0.62
  high_confidence_no_delegate_top_score: 0.78
  low_score_spread_ambiguity: 0.08
  high_score_spread_clarity: 0.15

budgets:
  max_total_tokens_per_request: 24000
  max_child_tokens: 8000
  max_child_cost_usd: 0.03
  max_total_latency_ms: 25000
  min_remaining_latency_to_delegate_ms: 12000
```

### 5) Sub-Agent Profile Catalog

#### 5.1 `doc_reader`
- **Use when:** single-document deep synthesis/extraction
- **Allowed tools:** `retrieve_documents`, `query_metadata`
- **Output schema:** summary by section + claims + citations + uncertainty
- **Stop criteria:** evidence coverage achieved OR max turns reached

#### 5.2 `comparator`
- **Use when:** multi-document compare/contrast
- **Allowed tools:** `retrieve_documents`, `query_metadata`
- **Output schema:** similarities, differences, conflicts, citation matrix
- **Stop criteria:** all requested comparison dimensions addressed

#### 5.3 `evidence_builder`
- **Use when:** user asks "show me sources/proof"
- **Allowed tools:** `retrieve_documents`, `query_metadata`
- **Output schema:** claim→source mapping, confidence per claim
- **Stop criteria:** each major claim backed or marked unsupported

#### 5.4 `web_verifier` (optional; gated)
- **Use when:** internal corpus insufficient and external corroboration needed
- **Allowed tools:** `web_search`, `retrieve_documents`
- **Output schema:** corroborated claims + external citations + trust notes
- **Stop criteria:** corroboration complete OR timeout

### 6) Decision Algorithm (deterministic envelope)
1. Evaluate hard gates.
2. Evaluate negative triggers.
3. Evaluate positive triggers.
4. If positive and no blockers, select profile using intent mapping.
5. Allocate child budget from remaining request budget.
6. Emit `DelegationPolicyOutput` with reason codes.

**Safe default on policy engine error:** `no_delegate` + reason code `POLICY_EVAL_ERROR`.

### 7) Failure Semantics
- **Child timeout:** return partial artifacts + warning; continue with main-agent synthesis.
- **Tool failure in child:** retry once; then downgrade profile or fallback.
- **No evidence found:** abstain with explicit gap statement and suggested next step.
- **Budget exceeded:** terminate child and continue with best available evidence.

### 8) Transparency / UX Rules
When delegation occurs, UI must show:
- Delegation badge: "Deep analysis mode used"
- Profile label (e.g., "Evidence Builder")
- Human-readable reason from `reason_codes`
- Child run status timeline (started/running/completed/fallback)
- Citations and uncertainty notes from child output

### 9) Observability Event Schema
Emit a policy decision event for every request:
```json
{
  "event": "delegation_policy_decision",
  "request_id": "string",
  "decision": "delegate | no_delegate | defer",
  "reason_codes": ["..."],
  "selected_profile": "...",
  "latency_budget_ms": 0,
  "token_budget": 0,
  "policy_version": "v1"
}
```
Track metrics by profile:
- delegate rate, success rate, timeout rate
- p50/p95 latency
- token/cost per run
- citation coverage proxy
- fallback frequency

### 10) Minimum Acceptance Tests (must pass)
1. **High-confidence fact lookup:** no delegation.
2. **Full-document summary request:** delegates to `doc_reader`.
3. **Cross-document comparison:** delegates to `comparator`.
4. **Low-confidence retrieval ambiguity:** delegates (if budget allows).
5. **Timeout scenario:** partial result + fallback + explicit warning.
6. **Policy engine error:** safe `no_delegate`.
7. **Budget exhaustion:** no delegation with clear reason code.
8. **Restricted mode:** disallowed tools never included in child scope.

---

## Success Criteria

By the end, students should have:
- ✅ A working RAG application they built with AI assistance
- ✅ Deep understanding of RAG concepts (chunking, embedding, retrieval, reranking)
- ✅ Understanding of codebase structure - what lives where, how pieces connect
- ✅ Ability to direct AI coding tools to build new features
- ✅ Ability to direct AI coding tools to debug and fix issues
- ✅ Experience with agentic patterns (multi-tool, sub-agents)
- ✅ Observability set up from day one

## Planned Enhancements & Wishlist

Based on the progress tracking and feature requests, the following enhancements are planned for the application:

### Chat UX & Thread Management
- Clear Chat button to reset conversation history
- Delete button for individual chat threads
- Enhanced thread management with selective deletion capabilities

### Document UX Improvements
- Ability to edit metadata for imported files in the UI
- Make Metadata categories displayed below files clickable to filter by category
- Documents in the RAG should be viewable in a readable format
- Web searches imported into the RAG should be readable with original links included

### Retrieval Quality & Provenance
- Save retrieved web searches with chats so clicking on previous chats shows links
- Implement RAG-Fusion to improve search coverage and accuracy
- When chat uses file information from the RAG, it should be linked in the right-hand panel to the source document

### Advanced Features
- GraphRAG functionality (for knowledge graph integration)
- Enable management of TLS certificates and public hostname for the UI
- Enhanced source attribution and citation display

### Module 8: Sub-Agents Implementation Roadmap

The sub-agent functionality will be implemented in phases:
1. **Delegation Policy** - Define when and how the main agent spawns sub-agents
2. **Sub-Agent Contract** - Establish inputs/outputs, tool permissions, and context boundaries
3. **Isolated Context Retrieval** - Support full-document scenarios with isolated retrieval
4. **Execution Lifecycle** - Manage sub-agent spawning, status streaming, and cleanup
5. **UI Representation** - Display nested tool calls and parent/child run timelines
6. **Reasoning Transparency** - Show safe reasoning summaries and citations
7. **Memory Boundaries** - Define what gets persisted to thread history
8. **Observability** - Add LangSmith tracing for parent/child runs
9. **Failure Handling** - Implement graceful fallbacks and error states
10. **Security & Guardrails** - Add tool sandboxing and data scope controls
11. **Performance Targets** - Set latency budgets and concurrency limits
12. **Acceptance Tests** - Define specific scenarios for sub-agent functionality

### Definition of Done
When all planned enhancements are implemented and tested, the application will be considered complete with:
- Full chat thread management capabilities
- Editable document metadata
- Clickable metadata filters
- Readable document views
- Web search provenance tracking
- RAG-Fusion implementation
- Source linking in chat responses
- GraphRAG functionality (optional)
- TLS certificate management capabilities
- Complete sub-agent implementation with all phases
- All acceptance criteria met
