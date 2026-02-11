from langsmith import traceable
from openai import AsyncOpenAI
from app.config import settings

perplexity_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global perplexity_client
    if perplexity_client is None:
        perplexity_client = AsyncOpenAI(
            base_url="https://api.perplexity.ai",
            api_key=settings.perplexity_api_key,
        )
    return perplexity_client


@traceable(name="web_search")
async def search_web(query: str) -> dict:
    try:
        client = _get_client()
        response = await client.chat.completions.create(
            model=settings.perplexity_model,
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful search assistant. Provide concise, factual answers.",
                },
                {"role": "user", "content": query},
            ],
        )
        answer = response.choices[0].message.content or ""

        # Perplexity returns citations in response metadata
        citations = []
        results = []
        raw = response.model_dump() if hasattr(response, "model_dump") else {}

        # Citations may be in top-level or in choices[0]
        if "citations" in raw:
            citations = raw["citations"]
        elif raw.get("choices") and "citations" in raw["choices"][0]:
            citations = raw["choices"][0]["citations"]

        for i, url in enumerate(citations):
            results.append(
                {
                    "title": f"Source {i + 1}",
                    "url": url if isinstance(url, str) else str(url),
                    "snippet": "",
                }
            )

        return {
            "answer": answer,
            "citations": citations,
            "results": results,
        }
    except Exception as e:
        return {
            "answer": f"Web search failed: {e}",
            "citations": [],
            "results": [],
        }
