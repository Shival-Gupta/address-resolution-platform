# File: app/pipeline/__init__.py
"""Pipeline package for address normalization and processing."""

from __future__ import annotations

from app.engines.normalizer import normalize

__all__ = ["normalize"]
