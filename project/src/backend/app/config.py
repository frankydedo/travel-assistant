from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://travel:travel@localhost:5432/travel"

    # OIDC (Keycloak). The issuer is the URL the browser sees; the JWKS URL may be internal to Docker.
    oidc_issuer: str = "http://localhost:8080/realms/travel"
    oidc_jwks_url: str = "http://localhost:8080/realms/travel/protocol/openid-connect/certs"
    oidc_audience: str = "travel-api"

    # RAG
    chroma_path: str = "./data/chroma"
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    embedding_cache_dir: str | None = None  # the Docker image pre-downloads the model here
    # "chroma" (local embeddings) or "keyword" (no model; used by tests)
    retriever: str = "chroma"

    # Fallback chain order (ADR-0005). Providers without credentials are skipped.
    llm_chain: str = "groq,gemini,mock"  # ADR-0018, ADR-0019
    llm_timeout_seconds: float = 30.0
    llm_cooldown_seconds: float = 60.0
    # Model names change often: they are configuration, not code (check each provider's console).
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-flash-lite-latest"
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai"
    gemini_reasoning_effort: str | None = "low"
    groq_api_key: str | None = None
    groq_model: str = "openai/gpt-oss-120b"
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_reasoning_effort: str | None = "low"
    mock_stream_delay_ms: int = 0

    # Langfuse (ADR-0010): self-hosted in compose; tracing is off when keys are missing.
    langfuse_host: str | None = None  # internal URL, e.g. http://langfuse-web:3000
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_ui_url: str = "http://localhost:3001"  # what the browser opens for trace links
    langfuse_project_id: str = "travel-assistant"

    # Per-user rate limit (ADR-0007)
    rate_limit_messages: int = 20
    rate_limit_window_seconds: int = 60
    max_message_chars: int = 2000

    # Logging (ADR-0017): "json" in Docker, "console" for local development
    log_level: str = "INFO"
    log_format: str = "console"

    # Planner
    max_trip_days: int = 14


@lru_cache
def get_settings() -> Settings:
    return Settings()
