# File: app/api/v1/router.py
"""Version 1 API router combining search and admin sub-routers."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.admin import router as admin_router
from app.api.v1.search import router as search_router

api_v1_router = APIRouter()
api_v1_router.include_router(search_router)
api_v1_router.include_router(admin_router)

__all__ = ["api_v1_router"]
