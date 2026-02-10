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

    langchain_tracing_v2: bool = True
    langchain_api_key: str = ""
    langchain_project: str = "agentic-rag"

    model_config = {"env_file": ".env"}


settings = Settings()
