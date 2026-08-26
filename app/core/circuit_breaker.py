# File: app/core/circuit_breaker.py
"""Circuit Breaker implementation for external AI service fault tolerance.

Implements the CLOSED -> OPEN -> HALF_OPEN state machine to prevent cascading
failures when external LLM APIs experience rate limits, outages, or timeouts.
"""

from __future__ import annotations

import time
from enum import StrEnum

from app.core.config import get_settings


class CircuitState(StrEnum):
    """Possible states for the CircuitBreaker."""

    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreaker:
    """Sliding-window circuit breaker with automatic state transitions and timeout recovery."""

    def __init__(
        self,
        failure_threshold: int | None = None,
        recovery_timeout: float | None = None,
    ) -> None:
        """Initialize CircuitBreaker with configurable thresholds.

        Args:
            failure_threshold: Consecutive failures to trip breaker to OPEN.
            recovery_timeout: Cooldown duration in seconds before HALF_OPEN test.
        """
        settings = get_settings()
        self.failure_threshold = (
            failure_threshold
            if failure_threshold is not None
            else settings.CIRCUIT_BREAKER_THRESHOLD
        )
        self.recovery_timeout = (
            recovery_timeout
            if recovery_timeout is not None
            else float(settings.CIRCUIT_BREAKER_TIMEOUT)
        )

        self._state = CircuitState.CLOSED
        self._consecutive_failures = 0
        self._last_state_change = time.monotonic()

    @property
    def state(self) -> CircuitState:
        """Return the current circuit breaker state, evaluating recovery timeout if OPEN.

        Does NOT mutate state on read — calls internal transition check.

        Returns:
            CircuitState: Current active state (CLOSED, OPEN, or HALF_OPEN).
        """
        self._maybe_transition_to_half_open()
        return self._state

    def _maybe_transition_to_half_open(self) -> None:
        """Check if recovery timeout elapsed and transition OPEN → HALF_OPEN.

        Only transitions if currently OPEN and cooldown has passed.
        Resets _last_state_change only once per actual transition, not on every read.
        """
        if self._state == CircuitState.OPEN:
            elapsed = time.monotonic() - self._last_state_change
            if elapsed >= self.recovery_timeout:
                self._state = CircuitState.HALF_OPEN
                # Do NOT reset _last_state_change here — preserve original OPEN timestamp
                # for diagnostics. Recovery restarts on success/failure recording.

    def is_allowed(self) -> bool:
        """Check if an outbound request is permitted through the breaker.

        Returns:
            bool: True if CLOSED or HALF_OPEN (for testing), False if OPEN.
        """
        return self.state in (CircuitState.CLOSED, CircuitState.HALF_OPEN)

    def record_success(self) -> None:
        """Record a successful operation, resetting failure counter and closing circuit."""
        self._consecutive_failures = 0
        self._state = CircuitState.CLOSED
        self._last_state_change = time.monotonic()

    def record_failure(self) -> None:
        """Record an operation failure, tripping breaker to OPEN if threshold reached."""
        self._consecutive_failures += 1
        if (
            self._state == CircuitState.HALF_OPEN
            or self._consecutive_failures >= self.failure_threshold
        ):
            self._state = CircuitState.OPEN
            self._last_state_change = time.monotonic()

    def reset(self) -> None:
        """Manually reset the circuit breaker to closed initial state."""
        self._state = CircuitState.CLOSED
        self._consecutive_failures = 0
        self._last_state_change = time.monotonic()
