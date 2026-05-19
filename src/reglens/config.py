"""Application configuration via pydantic-settings (env-driven)."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ------------------------------------------------------------------
    # Application
    app_name: str = "reglens"
    environment: str = Field(
        default="development", pattern="^(development|staging|production)$"
    )
    log_level: str = Field(
        default="INFO", pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$"
    )
    api_key: SecretStr = Field(description="Static API key for FastAPI auth")

    # ------------------------------------------------------------------
    # Database (Postgres with pgvector)
    database_url: str = Field(
        default="postgresql+psycopg://reglens:reglens@localhost:5432/reglens",
        description="SQLAlchemy-compatible Postgres connection URL",
    )
    database_pool_size: int = Field(default=10, ge=1, le=50)
    database_max_overflow: int = Field(default=20, ge=0, le=100)

    # ------------------------------------------------------------------
    # LLM providers
    gemini_api_key: SecretStr = Field(description="Google AI Studio API key")
    anthropic_api_key: SecretStr = Field(description="Anthropic API key")

    # Models
    gemini_ingestion_model: str = Field(default="gemini-2.5-pro")
    gemini_risk_model: str = Field(default="gemini-2.5-flash")
    gemini_embedding_model: str = Field(default="text-embedding-004")
    claude_model: str = Field(default="claude-sonnet-4-6")

    # ------------------------------------------------------------------
    # A2A agent endpoints
    a2a_ingestion_url: str = Field(
        default="http://reglens-adk-ingest:8001",
        description="Base URL of the Document Ingestion A2A server",
    )
    a2a_risk_scorer_url: str = Field(
        default="http://reglens-adk-risk:8002",
        description="Base URL of the Risk Scorer A2A server",
    )
    a2a_timeout_seconds: float = Field(default=120.0, gt=0)
    a2a_max_retries: int = Field(default=3, ge=1, le=10)

    # ------------------------------------------------------------------
    # Observability
    langsmith_api_key: SecretStr | None = Field(default=None)
    langsmith_project: str = Field(default="reglens")
    langsmith_tracing_enabled: bool = Field(default=False)

    otel_exporter_endpoint: str | None = Field(
        default=None,
        description="OTLP gRPC endpoint (e.g. http://otel-collector:4317). None → console exporter.",
    )
    otel_service_name: str = Field(default="reglens")

    # ------------------------------------------------------------------
    # RAG
    rag_top_k: int = Field(default=5, ge=1, le=20)
    rag_similarity_threshold: float = Field(default=0.6, ge=0.0, le=1.0)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
