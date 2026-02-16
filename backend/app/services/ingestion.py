import logging
from langsmith import traceable
from app.config import settings
from app.services.supabase import get_service_supabase_client
from app.services.chunker import chunk_text
from app.services.extraction import extract_text
from app.services.document_cleaner import clean_text
from app.services.embeddings import generate_embeddings
from app.services.metadata import extract_metadata

logger = logging.getLogger(__name__)

EMBEDDING_BATCH_SIZE = 100
CHUNK_INSERT_BATCH_SIZE = 50


@traceable(name="ingest_document")
async def ingest_document(document_id: str, user_id: str, storage_path: str, file_type: str = "txt"):
    """Background task: download file, chunk, embed, and store vectors."""
    sb = get_service_supabase_client()

    try:
        # Verify document still exists (may have been replaced)
        doc_check = sb.table("documents").select("id").eq("id", document_id).execute()
        if not doc_check.data:
            logger.info(f"Document {document_id} no longer exists, skipping ingestion")
            return

        # Update status → processing
        sb.table("documents").update({"status": "processing"}).eq(
            "id", document_id
        ).execute()

        # Download file from Supabase Storage
        file_bytes = sb.storage.from_("documents").download(storage_path)
        text = extract_text(file_bytes, file_type)
        text = clean_text(text)

        if not text.strip():
            sb.table("documents").update(
                {"status": "error", "error_message": "File is empty"}
            ).eq("id", document_id).execute()
            return

        # Upload extracted text to Storage
        extracted_path = f"{user_id}/{document_id}_extracted.txt"
        sb.storage.from_("documents").upload(
            extracted_path,
            text.encode("utf-8"),
            {"content-type": "text/plain; charset=utf-8"},
        )

        # Extract metadata via LLM
        metadata = await extract_metadata(text)

        # Chunk text
        chunks = chunk_text(text)

        # Generate embeddings in batches
        all_embeddings = []
        for i in range(0, len(chunks), EMBEDDING_BATCH_SIZE):
            batch = chunks[i : i + EMBEDDING_BATCH_SIZE]
            batch_texts = [c.content for c in batch]
            embeddings = await generate_embeddings(batch_texts)
            all_embeddings.extend(embeddings)

        # Insert chunks with embeddings in batches
        for i in range(0, len(chunks), CHUNK_INSERT_BATCH_SIZE):
            batch_chunks = chunks[i : i + CHUNK_INSERT_BATCH_SIZE]
            batch_embeddings = all_embeddings[i : i + CHUNK_INSERT_BATCH_SIZE]
            rows = [
                {
                    "document_id": document_id,
                    "user_id": user_id,
                    "content": chunk.content,
                    "embedding": emb,
                    "chunk_index": chunk.chunk_index,
                    "token_count": chunk.token_count,
                    "content_hash": chunk.content_hash,
                }
                for chunk, emb in zip(batch_chunks, batch_embeddings)
            ]
            sb.table("chunks").insert(rows).execute()

        # GraphRAG: extract entities and relationships from chunks
        if settings.graphrag_enabled:
            try:
                from app.services.graph_extractor import extract_graph_for_document
                chunk_rows = [
                    {"id": r["id"], "content": r["content"]}
                    for r in sb.table("chunks").select("id,content")
                                 .eq("document_id", document_id).execute().data
                ]
                await extract_graph_for_document(document_id, user_id, chunk_rows)
            except Exception:
                logger.exception(f"Graph extraction failed for {document_id}, continuing")

            if settings.graphrag_community_rebuild_enabled:
                try:
                    from app.services.community_builder import build_communities_for_user
                    await build_communities_for_user(user_id)
                except Exception:
                    logger.exception(f"Community rebuild failed for user {user_id}, continuing")

        # Update status → ready with metadata
        sb.table("documents").update(
            {
                "status": "ready",
                "chunk_count": len(chunks),
                "extracted_text_path": extracted_path,
                "title": metadata.title,
                "summary": metadata.summary,
                "topics": metadata.topics,
                "document_date": metadata.document_date.isoformat() if metadata.document_date else None,
            }
        ).eq("id", document_id).execute()

        logger.info(
            f"Document {document_id} ingested: {len(chunks)} chunks"
        )

    except Exception as e:
        logger.exception(f"Ingestion failed for document {document_id}")
        try:
            sb.table("documents").update(
                {"status": "error", "error_message": str(e)[:500]}
            ).eq("id", document_id).execute()
        except Exception:
            logger.exception("Failed to update document error status")
