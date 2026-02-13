"""GraphRAG entity/relationship extraction from document chunks."""
import json
import logging
from langsmith import traceable
from openai import AsyncOpenAI
from langsmith.wrappers import wrap_openai
from pydantic import BaseModel, ValidationError

from app.config import settings
from app.services.supabase import get_service_supabase_client

logger = logging.getLogger(__name__)

_client = wrap_openai(
    AsyncOpenAI(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
    )
)


class ExtractedEntity(BaseModel):
    name: str
    entity_type: str = "UNKNOWN"
    description: str | None = None


class ExtractedRelationship(BaseModel):
    source: str
    target: str
    relation_type: str
    description: str | None = None


class ChunkExtractionResult(BaseModel):
    entities: list[ExtractedEntity] = []
    relationships: list[ExtractedRelationship] = []


class BatchExtractionResult(BaseModel):
    results: list[ChunkExtractionResult] = []


_EXTRACTION_PROMPT = """\
You are an information extraction system. Extract named entities and relationships from the provided text chunks.

Entity types to extract: {entity_types}

For each chunk, return entities (name, entity_type, optional description) and relationships between those entities (source, target, relation_type, optional description).

Output ONLY valid JSON in this exact format:
{{
  "results": [
    {{
      "entities": [
        {{"name": "Entity Name", "entity_type": "PERSON", "description": "optional description"}}
      ],
      "relationships": [
        {{"source": "Entity A", "target": "Entity B", "relation_type": "WORKS_FOR", "description": "optional"}}
      ]
    }}
  ]
}}

One result object per chunk, in the same order as the input chunks.

Text chunks:
{chunks_text}
"""


@traceable(name="extract_graph_batch")
async def _extract_graph_batch(
    chunks: list[dict],
    entity_types: str,
) -> list[ChunkExtractionResult]:
    """Call LLM to extract entities and relationships from a batch of chunks."""
    chunks_text = "\n\n".join(
        f"[Chunk {i + 1}]\n{c['content']}" for i, c in enumerate(chunks)
    )
    prompt = _EXTRACTION_PROMPT.format(
        entity_types=entity_types,
        chunks_text=chunks_text,
    )

    try:
        response = await _client.chat.completions.create(
            model=settings.llm_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )
        raw = response.choices[0].message.content or ""

        # Strip markdown code fences if present
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```", 2)[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.rsplit("```", 1)[0].strip()

        data = json.loads(raw)
        result = BatchExtractionResult.model_validate(data)
        return result.results

    except (json.JSONDecodeError, ValidationError, Exception) as e:
        logger.warning(f"Graph extraction batch failed: {e}")
        return [ChunkExtractionResult() for _ in chunks]


def _upsert_entities(
    sb,
    user_id: str,
    document_id: str,
    entities: list[ExtractedEntity],
) -> dict[str, str]:
    """Upsert entities via RPC. Returns {name_lower: entity_id}."""
    name_map: dict[str, str] = {}
    for entity in entities:
        name_lower = entity.name.lower().strip()
        if not name_lower:
            continue
        try:
            result = sb.rpc("upsert_entity", {
                "p_user_id": user_id,
                "p_name": entity.name.strip(),
                "p_name_lower": name_lower,
                "p_entity_type": entity.entity_type or "UNKNOWN",
                "p_description": entity.description,
                "p_document_id": document_id,
            }).execute()
            if result.data:
                name_map[name_lower] = str(result.data)
        except Exception as e:
            logger.warning(f"Failed to upsert entity '{entity.name}': {e}")
    return name_map


def _upsert_relationships(
    sb,
    user_id: str,
    document_id: str,
    relationships: list[ExtractedRelationship],
    entity_name_map: dict[str, str],
) -> None:
    """Upsert relationships via RPC. Skips if source/target not in name_map."""
    for rel in relationships:
        source_lower = rel.source.lower().strip()
        target_lower = rel.target.lower().strip()
        source_id = entity_name_map.get(source_lower)
        target_id = entity_name_map.get(target_lower)
        if not source_id or not target_id:
            continue
        try:
            sb.rpc("upsert_relationship", {
                "p_user_id": user_id,
                "p_source_id": source_id,
                "p_target_id": target_id,
                "p_relation_type": rel.relation_type or "RELATED_TO",
                "p_description": rel.description,
                "p_document_id": document_id,
            }).execute()
        except Exception as e:
            logger.warning(f"Failed to upsert relationship '{rel.source}→{rel.target}': {e}")


def _insert_chunk_entities(
    sb,
    user_id: str,
    chunk_id: str,
    entity_ids: list[str],
) -> None:
    """Bulk insert chunk_entity links, ignoring conflicts."""
    if not entity_ids:
        return
    rows = [{"chunk_id": chunk_id, "entity_id": eid, "user_id": user_id} for eid in entity_ids]
    try:
        sb.table("chunk_entities").upsert(rows, on_conflict="chunk_id,entity_id").execute()
    except Exception as e:
        logger.warning(f"Failed to insert chunk_entities for chunk {chunk_id}: {e}")


@traceable(name="extract_graph_for_document")
async def extract_graph_for_document(
    document_id: str,
    user_id: str,
    chunk_rows: list[dict],
) -> None:
    """Main entry point: extract entities/relationships from all chunks of a document."""
    if not chunk_rows:
        return

    sb = get_service_supabase_client()
    batch_size = settings.graphrag_extraction_batch_size
    entity_types = settings.graphrag_entity_types

    # Collect all entity name_lower→id for this document (across batches)
    document_entity_map: dict[str, str] = {}

    try:
        for i in range(0, len(chunk_rows), batch_size):
            batch = chunk_rows[i: i + batch_size]
            extraction_results = await _extract_graph_batch(batch, entity_types)

            for chunk, result in zip(batch, extraction_results):
                chunk_id = chunk["id"]

                # Collect all entity names in this chunk
                all_entities = result.entities
                if not all_entities:
                    continue

                # Upsert entities and get id map for this chunk
                chunk_entity_map = _upsert_entities(sb, user_id, document_id, all_entities)
                document_entity_map.update(chunk_entity_map)

                # Insert chunk↔entity links
                _insert_chunk_entities(sb, user_id, chunk_id, list(chunk_entity_map.values()))

                # Upsert relationships using the full document entity map for cross-chunk refs
                merged_map = {**document_entity_map, **chunk_entity_map}
                _upsert_relationships(sb, user_id, document_id, result.relationships, merged_map)

        logger.info(
            f"Graph extraction complete for document {document_id}: "
            f"{len(document_entity_map)} entities"
        )

    except Exception:
        logger.exception(f"Graph extraction failed for document {document_id}")
