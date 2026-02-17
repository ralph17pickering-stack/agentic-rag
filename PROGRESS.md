# Progress

Track your progress through the masterclass. Update this file as you complete modules - Claude Code reads this to understand where you are in the project.

## Convention
- `[ ]` = Not started
- `[-]` = In progress
- `[x]` = Completed

## Modules

### Module 1: App Shell + Observability
- [x] Backend scaffolding (Python + FastAPI + venv)
- [x] Frontend scaffolding (Vite + React + Tailwind + shadcn/ui)
- [x] Root config files (.gitignore, .env.example)
- [x] Database migration (threads + messages tables with RLS)
- [x] Backend: config, JWT auth, Supabase client, thread CRUD, chat SSE endpoint, LLM service
- [x] Frontend: auth (login/signup), chat layout, thread sidebar, message area, SSE streaming
- [x] LangSmith observability (wrap_openai + @traceable)
- [x] **Manual step: Create Supabase project, run migration, populate .env files**

### Module 2: BYO Retrieval + Memory
- [x] Database schema: documents + chunks tables, pgvector extension, HNSW index, RLS, Realtime
- [x] match_chunks RPC function (similarity search with RLS)
- [x] Backend config: embedding_model, embedding_dim, chunk_size, chunk_overlap
- [x] Dependencies: python-multipart, tiktoken
- [x] Service role Supabase client (bypasses RLS for background ingestion)
- [x] Embedding service (batch + single, @traceable)
- [x] Chunker service (tiktoken cl100k_base, fixed-size with overlap)
- [x] Document models (Pydantic)
- [x] Ingestion pipeline (download → chunk → embed → store, background async)
- [x] Documents API (GET/POST/DELETE /api/documents)
- [x] Storage bucket auto-creation on startup
- [x] Retrieval service (query embedding → match_chunks RPC)
- [x] Tool-calling chat refactor (retrieve_documents tool definition + flow)
- [x] Frontend: Documents UI (upload, list, delete, status badges)
- [x] Frontend: Realtime status updates via Supabase
- [x] Frontend: Chat/Documents nav toggle
- [x] Integration testing + polish

### Module 3: Record Manager
- [x] Database migration: content_hash columns + indexes on documents and chunks
- [x] Hashing utility (sha256_hex, sha256_text)
- [x] Chunker: content_hash on each chunk
- [x] Pydantic model: content_hash, is_duplicate fields
- [x] Document router: dedup logic (exact duplicate → 200, same filename → replace, new → 201)
- [x] Ingestion: store chunk content_hash, existence check before processing
- [x] Frontend: TypeScript types, upload hook returns Document, duplicate info banner

### Module 4: Metadata Extraction
- [x] Database migration: title, summary, topics, document_date columns + updated match_chunks RPC
- [x] Metadata extraction service (LLM-based with graceful fallback)
- [x] Ingestion pipeline: extract metadata before chunking, store on document
- [x] Pydantic model: metadata fields on DocumentResponse
- [x] Retrieval: date filtering + recency boost params passed through to match_chunks
- [x] LLM tool definition: date_from, date_to, recency_weight optional params
- [x] Context format: chunk headers include doc title, date, topics, score
- [x] Chat router: forwards kwargs to retrieval
- [x] Frontend: TS types + DocumentsPanel displays title, summary, topics, date

### Module 5: Multi-Format Support
- [x] Database migration: widen file_type CHECK constraint (pdf, docx, csv, html)
- [x] Dependencies: pypdf, python-docx, beautifulsoup4
- [x] Text extraction service (format dispatcher: txt, md, pdf, docx, csv, html)
- [x] Ingestion pipeline: use extract_text() with file_type param
- [x] Backend router: expanded allowed extensions, content-type mapping, pass file_type to ingestion
- [x] Frontend: accept new formats in validation, file picker, and drop zone text

### Module 6: Hybrid Search & Reranking
- [x] Database migration: tsvector column, GIN index, auto-populate trigger, keyword search RPC
- [x] Config settings: search_mode, rrf_k, rerank_enabled, rerank_top_n, retrieval_candidates
- [x] Reranking service: LLM-based relevance scoring with Pydantic validation, graceful fallback
- [x] Hybrid retrieval pipeline: semantic + keyword in parallel, RRF merge, optional rerank
- [x] Score display: prefer rerank_score > rrf_score > similarity in chunk headers

### Module 7: Additional Tools
- [x] Database migration: query_document_metadata RPC (read-only SQL execution with SECURITY INVOKER)
- [x] Config: perplexity_api_key, perplexity_model, web_search_enabled, sql_tool_enabled
- [x] Text-to-SQL service: generate_sql + execute_metadata_query (LLM→SQL→RPC)
- [x] Web search service: Perplexity sonar API wrapper with citation parsing
- [x] LLM refactor: ToolContext, ToolEvent, multi-tool definitions, generalized dispatch, multi-round loop
- [x] Chat router: ToolContext construction, SSE web_results events
- [x] URL ingestion endpoint: POST /api/documents/from-url (fetch→store→ingest)
- [x] Frontend: WebResult type, web_results SSE handling in useChat
- [x] Frontend: WebResultsSidebar with Save to KB, integrated into ChatLayout

### UX Redesign (UK-Centric)
- [x] Theme system: next-themes with system/light/dark cycle, toggle in header
- [x] Responsive breakpoint hook (mobile <768 / tablet <1024 / desktop)
- [x] Panel state hook (left: collapsed/overlay/pinned, right: hidden/overlay, keyboard shortcuts)
- [x] Left panel: icon rail (48px) + sliding overlay (280px) + pinnable on desktop
- [x] Right panel: hidden by default, overlay (320px) with edge tab handle, slide transition
- [x] Scrim overlay with fade transition for overlay panels
- [x] Mobile layout: bottom tab bar (Chat/History/Results), full-screen tab views, badge dot
- [x] Header: responsive (compact on mobile, hamburger menu), theme toggle
- [x] CSS transitions on all panel and scrim state changes

### Module 8: Sub-Agents (Deep Analysis)
- [x] Config: sub_agents_enabled flag
- [x] Sub-agent service: run_sub_agent with 5-round tool loop, text tool call parsing, @traceable, status callbacks
- [x] LLM service: deep_analysis tool definition, system prompt, get_tools, _execute_tool with on_status, stream status events
- [x] Chat router: SSE sub_agent_status events
- [x] Frontend: deepAnalysisPhase + usedDeepAnalysis state in useChat, SSE handling
- [x] Frontend: MessageArea phase text + violet "Deep Analysis" badge
- [x] Frontend: ChatLayout wiring for both mobile and desktop

### Improvements

#### Phase 1 — Chat hygiene + thread continuity

- [x] **Clear Chat (current thread):** Add a "Clear Chat" button to remove messages from the active thread (confirm modal).
- [x] **Selective thread deletion:** "-" button next to each chat to delete chat threads.
- [x] **Persist web results per thread (storage):** Save retrieved web search results against the thread (model + DB/API).
- [x] **Persist web results per thread (UI):** When reopening a thread, restore/show the saved links in the right-hand panel.

#### Phase 2 — Source traceability in the UI

- [x] **Citations pipeline (backend):** Track which retrieved chunks/docs were used in a response (store "used_sources" per assistant message).
- [x] **Right panel citations (docs):** When chat uses RAG file info, show linked sources in the right-hand panel (doc → chunk anchors).
- [x] **Right panel citations (web):** When chat uses web results, show linked sources in the right-hand panel (result → URL).

#### Phase 3 — Knowledge base readability parity

- [x] **Documents readable:** RAG documents viewable in readable format (not necessarily original file).
- [x] **Web documents readable:** Web searches saved/imported into the RAG are readable and include the original link.
- [ ] **KB viewer polish:** Unified viewer experience for file docs + web docs (title, source link, extracted text, metadata).

#### Phase 4 — Metadata curation + governance

* [x] **Metadata filter UX:** Metadata category displayed below files is clickable to filter by category.
* [x] **Topic consolidation:** Background task merges near-duplicate topic tags to canonical topics.
- [x] **Edit metadata (UI):** Ability to edit document metadata in the UI (start with title/topics; expand later if needed).
- [ ] **Edit metadata (audit + sync):** Track updated_at/editor; ensure edits flow into retrieval ranking (and any caches).

#### Phase 5 — Ingestion quality upgrades (chunking + enrichment)

- [x] **Pre-chunk cleaning (minimal):** Normalise whitespace; remove obvious boilerplate; preserve meaningful structure.
- [x] **Structure-preserving reformat:** Reformat tables/lists so they remain useful post-embedding (table→markdown, keep headers).
- [x] **Boundary-aware chunking:** Chunking respects headings/sections; keep headings attached; keep tables whole.
- [ ] **Chunk metadata schema:** Add per-chunk fields (summary, keywords, hypothetical questions) + keywords table.
- [ ] **Chunk enrichment pipeline:** For each chunk: generate summary, extract/store keywords, generate hypothetical questions.

#### Phase 6 — Projects (organisation + sharing)

- [ ] **Projects v1:** Chats + documents belong to a project; project switcher; default project per user.
- [ ] **Project sharing:** Share projects between users (roles: owner/editor/viewer) with RLS alignment.
- [ ] **Hierarchical projects:** Sub-projects inherit parent documents (explicit inheritance rules + conflict handling).

#### Phase 7 — Reasoning / orchestration layer

- [ ] **Planner interface:** Introduce a planning step that interprets user intent before retrieval/tooling.
- [ ] **Tool router:** Conditional router chooses tools (RAG, web, SQL, sub-agent, etc.) based on plan.
- [ ] **Multi-agent reasoning mode:** Optional multi-agent execution for complex queries, with consolidated final response.
- [ ] **Safety + observability:** Trace plans/tool decisions; guardrails to prevent tool spam / context bloat.

#### Phase 8 — Deployment hardening

- [ ] **TLS + hostname management:** Enable management of TLS certificates and public hostname for the UI.