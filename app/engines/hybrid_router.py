# File: app/engines/hybrid_router.py
"""Hybrid Router alias module wrapping the central SearchOrchestrator.

Provides the canonical HybridRouter interface specified in architecture.md.
"""

from __future__ import annotations

from app.pipeline.orchestrator import SearchOrchestrator

# Canonical alias
HybridRouter = SearchOrchestrator

__all__ = ["HybridRouter", "SearchOrchestrator"]
