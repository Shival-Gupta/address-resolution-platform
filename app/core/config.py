# File: app/core/config.py
"""Central application configuration using Pydantic BaseSettings.

Loads settings from environment variables and `.env` file. Provides configuration
for external AI models, database storage, search confidence thresholds, circuit
breaker parameters, and server settings.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Global configuration settings for Address Resolution Platform.

    Attributes:
        GEMINI_API_KEY: API key for Google GenAI services.
        OPENAI_API_KEY: Optional API key for OpenAI services.
        EMBEDDING_MODEL: Google GenAI embedding model identifier.
        LLM_MODEL: Google GenAI model identifier for Tier 3 disambiguation.
        DUCKDB_PATH: File path for local DuckDB search index.
        SAP_DSN: Connection string for SAP S/4HANA source database.
        GIS_DB_URL: Connection URL for PostGIS spatial database.
        TIER1_CONFIDENCE_THRESHOLD: Minimum confidence to accept Tier 1 lexical match.
        TIER2_CONFIDENCE_THRESHOLD: Minimum confidence to accept Tier 2 semantic match.
        MANUAL_REVIEW_THRESHOLD: Minimum confidence requiring human review before resolving.
        DISCARD_THRESHOLD: Scores below this threshold are treated as no match.
        LLM_FALLBACK_ENABLED: Whether Tier 3 LLM fallback is active.
        CIRCUIT_BREAKER_THRESHOLD: Consecutive failures to open circuit breaker.
        CIRCUIT_BREAKER_TIMEOUT: Cooldown time in seconds before half-open state.
        API_KEY: Pre-shared key for securing API endpoints.
        LOG_LEVEL: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        OTEL_EXPORTER_ENDPOINT: OpenTelemetry collector endpoint URL.
        PORT: Port number for FastAPI server.
        WORKERS: Number of Uvicorn worker processes.
    """

    # AI / LLM Providers
    GEMINI_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    EMBEDDING_MODEL: str = "text-embedding-004"
    LLM_MODEL: str = "gemini-2.5-flash"

    # Database
    DUCKDB_PATH: str = "./data/addresses.db"
    SAP_DSN: str = ""
    GIS_DB_URL: str = ""

    # Confidence Thresholds
    TIER1_CONFIDENCE_THRESHOLD: float = 0.92
    TIER2_CONFIDENCE_THRESHOLD: float = 0.88
    MANUAL_REVIEW_THRESHOLD: float = 0.75
    DISCARD_THRESHOLD: float = 0.50

    # Fallback & Circuit Breaker
    LLM_FALLBACK_ENABLED: bool = True
    CIRCUIT_BREAKER_THRESHOLD: int = 5
    CIRCUIT_BREAKER_TIMEOUT: int = 60

    # Observability & Server
    LOG_LEVEL: str = "INFO"
    OTEL_EXPORTER_ENDPOINT: str = ""
    API_KEY: str = "test_api_key"
    PORT: int = 8000
    WORKERS: int = 4

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Return a cached singleton instance of application settings.

    Returns:
        Settings: Validated configuration settings instance.
    """
    return Settings()
