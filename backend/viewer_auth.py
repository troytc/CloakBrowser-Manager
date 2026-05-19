"""FastAPI dependency for viewer JWT on machine routes (Phase 3: SEC-07)."""

from __future__ import annotations

from fastapi import HTTPException, Request

from .viewer_tokens import (
    ViewerTokenError,
    ViewerTokenExpired,
    ViewerTokenInvalid,
    ViewerTokenProfileMismatch,
    ViewerTokenReplay,
    validate_viewer_token,
)


def _extract_viewer_token(request: Request) -> str | None:
    header = request.headers.get("X-Viewer-Token")
    if header:
        return header.strip()
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:].strip()
    return None


async def require_viewer_token(
    request: Request,
    profile_id: str,
    *,
    consume_jti: bool = True,
) -> dict:
    """Validate viewer JWT for profile_id."""
    token = _extract_viewer_token(request)
    if not token:
        raise HTTPException(status_code=403, detail="Forbidden")
    try:
        return await validate_viewer_token(
            token, profile_id, consume_jti=consume_jti
        )
    except ViewerTokenExpired:
        raise HTTPException(status_code=403, detail="Forbidden") from None
    except ViewerTokenReplay:
        raise HTTPException(status_code=403, detail="Forbidden") from None
    except (ViewerTokenInvalid, ViewerTokenProfileMismatch, ViewerTokenError):
        raise HTTPException(status_code=403, detail="Forbidden") from None
