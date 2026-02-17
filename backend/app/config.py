from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    supabase_jwt_secret: str = ""

    llm_base_url: str = "http://127.0.0.1:8081/v1"
    llm_api_key: str = "not-needed"
    llm_model: str = "local-model"

    embedding_base_url: str = ""    # If set, embeddings use this URL instead of llm_base_url
    embedding_model: str = "local-model"
    embedding_dim: int = 768
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

    topic_consolidation_enabled: bool = True
    topic_consolidation_interval_hours: float = 24

    graphrag_enabled: bool = True
    graphrag_extraction_batch_size: int = 5
    graphrag_entity_types: str = "PERSON,ORGANIZATION,LOCATION,CONCEPT,EVENT,PRODUCT"
    graphrag_community_min_size: int = 3
    graphrag_community_chunks_per_summary: int = 5
    graphrag_community_rebuild_enabled: bool = True
    graphrag_expansion_enabled: bool = True
    graphrag_expansion_top_k: int = 3
    graphrag_global_communities_top_n: int = 5

    langchain_tracing_v2: bool = True
    langchain_api_key: str = ""
    langchain_project: str = "agentic-rag"

    model_config = {"env_file": ".env"}


settings = Settings()
