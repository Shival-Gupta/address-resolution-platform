# File: tests/unit/test_config.py
"""Unit tests for configuration management and settings loading.

Validates default settings, environment variable overrides, confidence threshold
bounds, and cached singleton instantiation.
"""

from __future__ import annotations

import os
from unittest.mock import patch

from app.core.config import Settings, get_settings


class TestConfig:
    """Test suite for application configuration."""

    def test_default_settings(self) -> None:
        """Test default values for settings."""
        settings = Settings()
        assert settings.EMBEDDING_MODEL == "text-embedding-004"
        assert settings.LLM_MODEL == "gemini-2.5-flash"
        assert settings.TIER1_CONFIDENCE_THRESHOLD == 0.92
        assert settings.TIER2_CONFIDENCE_THRESHOLD == 0.88
        assert settings.MANUAL_REVIEW_THRESHOLD == 0.75
        assert settings.DISCARD_THRESHOLD == 0.50
        assert settings.CIRCUIT_BREAKER_THRESHOLD == 5
        assert settings.CIRCUIT_BREAKER_TIMEOUT == 60
        assert settings.PORT == 8000
        assert settings.WORKERS == 4

    def test_env_override(self) -> None:
        """Test overriding settings via environment variables."""
        with patch.dict(
            os.environ,
            {
                "TIER1_CONFIDENCE_THRESHOLD": "0.95",
                "PORT": "9000",
                "GEMINI_API_KEY": "custom_api_key",
            },
        ):
            settings = Settings()
            assert settings.TIER1_CONFIDENCE_THRESHOLD == 0.95
            assert settings.PORT == 9000
            assert settings.GEMINI_API_KEY == "custom_api_key"

    def test_get_settings_cached_singleton(self) -> None:
        """Test that get_settings returns the same cached instance."""
        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2
