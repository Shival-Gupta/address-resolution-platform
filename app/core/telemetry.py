# File: app/core/telemetry.py
"""OpenTelemetry tracing configuration and span context management.

Provides telemetry instrumentation helpers and custom tracer spans for tracking
per-tier execution latency across search and ingestion pipelines.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from typing import Any

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Fallback in-memory span tracer when collector is not configured
_TRACER_INITIALIZED = False


def init_telemetry(service_name: str = "address-resolution-platform") -> None:
    """Initialize OpenTelemetry tracer provider and exporter.

    Args:
        service_name: Service identifier for distributed trace spans.
    """
    global _TRACER_INITIALIZED  # noqa: PLW0603
    settings = get_settings()

    if not settings.OTEL_EXPORTER_ENDPOINT:
        logger.info("OpenTelemetry collector endpoint not set. Using local tracing.")
        _TRACER_INITIALIZED = True
        return

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider

        resource = Resource.create({"service.name": service_name})
        provider = TracerProvider(resource=resource)
        trace.set_tracer_provider(provider)
        _TRACER_INITIALIZED = True
        logger.info("OpenTelemetry initialized with service name '%s'.", service_name)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to initialize OpenTelemetry exporter: %s", exc)


@contextmanager
def trace_span(span_name: str, attributes: dict[str, Any] | None = None) -> Iterator[None]:
    """Synchronous context manager for instrumenting code blocks with trace spans.

    Args:
        span_name: Name of the traced operation or search tier.
        attributes: Key-value attributes to attach to the span.

    Yields:
        None
    """
    settings = get_settings()
    attrs = attributes or {}

    if not settings.OTEL_EXPORTER_ENDPOINT or not _TRACER_INITIALIZED:
        logger.debug("[SPAN %s] attributes=%s", span_name, attrs)
        yield
        return

    try:
        from opentelemetry import trace

        tracer = trace.get_tracer("address-resolution-platform")
        with tracer.start_as_current_span(span_name, attributes=attrs):
            yield
    except Exception:  # noqa: BLE001
        yield


@asynccontextmanager
async def async_trace_span(
    span_name: str, attributes: dict[str, Any] | None = None
) -> AsyncIterator[None]:
    """Asynchronous context manager for instrumenting async code blocks with trace spans.

    Args:
        span_name: Name of the traced operation or search tier.
        attributes: Key-value attributes to attach to the span.

    Yields:
        None
    """
    with trace_span(span_name, attributes):
        yield
