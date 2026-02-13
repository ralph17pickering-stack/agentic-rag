from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    supabase_jwt_secret: str = ""

    llm_base_url: str = "http://127.0.0.1:8081/v1"
    llm_api_key: str = "not-needed"
    llm_model: str = "local-model"

    embedding_model: str = "local-model"
    embedding_dim: int = 2048
    chunk_size: int = 500
    chunk_overlap: int = 50

    search_mode: str = "hybrid"        # "semantic", "keyword", "hybrid"
    rrf_k: int = 60                    # RRF constant
    rerank_enabled: bool = True
    rerank_top_n: int = 5
    retrieval_candidates: int = 20     # per-method fetch count before merge
    rag_fusion_enabled: bool = False      # set RAG_FUSION_ENABLED=true in .env to activate
    rag_fusion_query_count: int = 3       # additional sub-queries; total = 1 + this value

    perplexity_api_key: str = ""
    perplexity_model: str = "sonar"
    web_search_enabled: bool = True
    sql_tool_enabled: bool = True
    sub_agents_enabled: bool = True

    langchain_tracing_v2: bool = True
    langchain_api_key: str = ""
    langchain_project: str = "agentic-rag"

    model_config = {"env_file": ".env"}


settings = Settings()
