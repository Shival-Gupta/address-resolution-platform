# File: app/api/v1/__init__.py
"""V1 API package module."""

from __future__ import annotations

from app.api.v1.router import api_v1_router

__all__ = ["api_v1_router"]
