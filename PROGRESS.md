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
- [ ] Not started

### Module 8: Sub-Agents
- [ ] Not started
