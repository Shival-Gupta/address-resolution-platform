# File: tests/unit/test_circuit_breaker.py
"""Unit tests for CircuitBreaker state transitions and fault tolerance.

Validates CLOSED -> OPEN -> HALF_OPEN -> CLOSED state lifecycle, consecutive
failure threshold, recovery timeouts, and manual reset.
"""

from __future__ import annotations

import time

from app.core.circuit_breaker import CircuitBreaker, CircuitState


class TestCircuitBreaker:
    """Test suite for CircuitBreaker."""

    def test_initial_state_closed(self) -> None:
        """Verify circuit breaker initializes in CLOSED state and allows requests."""
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=0.1)
        assert cb.state == CircuitState.CLOSED
        assert cb.is_allowed() is True

    def test_transitions_to_open_after_consecutive_failures(self) -> None:
        """Verify breaker trips to OPEN after reaching failure threshold."""
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=0.1)

        cb.record_failure()
        assert cb.state == CircuitState.CLOSED
        assert cb.is_allowed() is True

        cb.record_failure()
        assert cb.state == CircuitState.CLOSED

        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert cb.is_allowed() is False

    def test_success_resets_failure_counter(self) -> None:
        """Verify recording success resets consecutive failure count."""
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=0.1)

        cb.record_failure()
        cb.record_failure()
        cb.record_success()

        # Should require 3 new failures to trip
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED

        cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_recovery_timeout_transitions_to_half_open(self) -> None:
        """Verify cooldown period transitions breaker from OPEN to HALF_OPEN."""
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.05)

        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

        time.sleep(0.06)
        assert cb.state == CircuitState.HALF_OPEN
        assert cb.is_allowed() is True

    def test_half_open_success_closes_breaker(self) -> None:
        """Verify successful request in HALF_OPEN state resets breaker to CLOSED."""
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.05)

        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

        time.sleep(0.06)
        assert cb.state == CircuitState.HALF_OPEN

        cb.record_success()
        assert cb.state == CircuitState.CLOSED
        assert cb.is_allowed() is True

    def test_half_open_failure_reopens_breaker(self) -> None:
        """Verify failed request in HALF_OPEN state immediately trips breaker back to OPEN."""
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.05)

        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

        time.sleep(0.06)
        assert cb.state == CircuitState.HALF_OPEN

        cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_manual_reset(self) -> None:
        """Verify manual reset returns breaker to CLOSED state."""
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=60.0)

        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

        cb.reset()
        assert cb.state == CircuitState.CLOSED
        assert cb.is_allowed() is True
