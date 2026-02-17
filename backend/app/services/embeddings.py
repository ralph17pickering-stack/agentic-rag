from langsmith import traceable
from langsmith.wrappers import wrap_openai
from openai import AsyncOpenAI
from app.config import settings

# Use a dedicated embedding endpoint if configured, otherwise fall back to the main LLM.
_embedding_base_url = settings.embedding_base_url or settings.llm_base_url

embedding_client = wrap_openai(
    AsyncOpenAI(
        base_url=_embedding_base_url,
        api_key=settings.llm_api_key,
    )
)


@traceable(name="generate_embeddings", run_type="embedding")
async def generate_embeddings(texts: list[str]) -> list[list[float]]:
    """Generate embeddings for a batch of texts."""
    response = await embedding_client.embeddings.create(
        model=settings.embedding_model,
        input=texts,
    )
    return [item.embedding for item in response.data]


@traceable(name="generate_embedding", run_type="embedding")
async def generate_embedding(text: str) -> list[float]:
    """Generate a single embedding for query-time retrieval."""
    response = await embedding_client.embeddings.create(
        model=settings.embedding_model,
        input=text,
    )
    return response.data[0].embedding
