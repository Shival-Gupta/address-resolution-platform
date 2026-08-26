# File: app/core/exceptions.py
"""Custom exception hierarchy for the Address Resolution Platform.

Provides domain-specific exceptions for normalization errors, database operations,
circuit breaker state, AI engine communications, and authentication failures.
"""

from __future__ import annotations


class AddressResolutionError(Exception):
    """Base exception for all Address Resolution Platform errors."""

    def __init__(self, message: str, details: dict[str, str] | None = None) -> None:
        """Initialize base exception with message and optional details.

        Args:
            message: Human-readable error message.
            details: Optional dictionary with additional error metadata.
        """
        super().__init__(message)
        self.message = message
        self.details = details or {}


class NormalizationError(AddressResolutionError):
    """Raised when address string normalization fails."""


class DatabaseError(AddressResolutionError):
    """Raised when database query or ingestion operation fails."""


class CircuitBreakerOpenError(AddressResolutionError):
    """Raised when an operation is attempted while a circuit breaker is in OPEN state."""


class AuthenticationError(AddressResolutionError):
    """Raised when client API key or token authentication fails."""


class InvalidQueryError(AddressResolutionError):
    """Raised when an inbound search query fails business validation."""


class EmbeddingError(AddressResolutionError):
    """Raised when vector embedding generation fails."""


class LLMDisambiguationError(AddressResolutionError):
    """Raised when Tier 3 LLM disambiguation fails."""
