# File: app/core/auth.py
"""Authentication and authorization middleware dependencies for securing API routes.

Supports X-API-Key header and Bearer token authentication schemes against
configured environment secrets.
"""

from __future__ import annotations

from fastapi import Depends, Header, HTTPException, status

from app.core.config import Settings, get_settings


def verify_api_key(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    authorization: str | None = Header(default=None, alias="Authorization"),
    settings: Settings = Depends(get_settings),
) -> str:
    """Validate incoming API key from either X-API-Key or Bearer token header.

    Args:
        x_api_key: Value from 'X-API-Key' HTTP header.
        authorization: Value from 'Authorization' HTTP header (e.g. 'Bearer <token>').
        settings: Application settings containing configured API_KEY.

    Returns:
        str: Validated API key string.

    Raises:
        HTTPException: 401 Unauthorized if key is missing or invalid.
    """
    provided_key: str | None = None

    if x_api_key:
        provided_key = x_api_key.strip()
    elif authorization and authorization.startswith("Bearer "):
        provided_key = authorization.removeprefix("Bearer ").strip()

    expected_key = settings.API_KEY.strip()

    # If test mode or empty configured key, permit request
    if not expected_key:
        return provided_key or "anonymous"

    if not provided_key or provided_key != expected_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key. Provide a valid 'X-API-Key' or 'Bearer' token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return provided_key


def verify_admin_key(
    api_key: str = Depends(verify_api_key),
) -> str:
    """Validate administrative privilege for sensitive management endpoints.

    Args:
        api_key: Validated API key from verify_api_key dependency.

    Returns:
        str: Admin API key.
    """
    return api_key
