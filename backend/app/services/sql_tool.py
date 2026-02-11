import json
import re

from langsmith import traceable
from app.config import settings
from app.services.supabase import get_supabase_client

SCHEMA_DESCRIPTION = """
Table: documents
Columns:
  - id (uuid, PK)
  - user_id (uuid, FK to auth.users)
  - filename (text) — original uploaded filename
  - file_type (text) — extension: txt, md, pdf, docx, csv, html
  - file_size (integer) — bytes
  - status (text) — pending, processing, ready, error
  - chunk_count (integer) — number of chunks after ingestion
  - title (text, nullable) — LLM-extracted document title
  - summary (text, nullable) — LLM-generated summary
  - topics (text[], nullable) — LLM-extracted topic tags
  - document_date (text, nullable) — date mentioned in document
  - content_hash (text) — SHA-256 of file content
  - created_at (timestamptz)
  - updated_at (timestamptz)

Notes:
- RLS is enabled; queries automatically filter to the current user's documents.
- Only SELECT queries are allowed.
- Use standard PostgreSQL syntax.
"""


@traceable(name="generate_sql")
async def generate_sql(question: str) -> str:
    from app.services.llm import client

    response = await client.chat.completions.create(
        model=settings.llm_model,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a SQL expert. Given the schema below and a user question, "
                    "generate a single PostgreSQL SELECT query. Return ONLY the SQL, no explanation.\n\n"
                    f"{SCHEMA_DESCRIPTION}"
                ),
            },
            {"role": "user", "content": question},
        ],
    )
    sql = response.choices[0].message.content.strip()
    # Strip markdown fences if present
    sql = re.sub(r"^```(?:sql)?\s*", "", sql)
    sql = re.sub(r"\s*```$", "", sql)
    return sql.strip()


@traceable(name="execute_metadata_query")
async def execute_metadata_query(question: str, user_token: str) -> str:
    try:
        sql = await generate_sql(question)
        sb = get_supabase_client(user_token)
        result = sb.rpc("query_document_metadata", {"sql_query": sql}).execute()
        data = result.data
        if isinstance(data, list) and len(data) == 0:
            return "No results found."
        return json.dumps(data, default=str)
    except Exception as e:
        return f"Error querying document metadata: {e}"
