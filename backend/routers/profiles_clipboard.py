"""Machine-surface clipboard read scoped to viewer JWT (SEC-07).

Mounted at /profiles/{profile_id}/clipboard without API-key-only access.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ..viewer_auth import require_viewer_token

router = APIRouter(prefix="/profiles", tags=["profiles"])


async def _require_active_viewer_token(request: Request, profile_id: str) -> dict:
    return await require_viewer_token(request, profile_id, consume_jti=False)


@router.get("/{profile_id}/clipboard")
async def get_profile_clipboard(
    profile_id: str,
    _claims: dict = Depends(_require_active_viewer_token),
) -> dict[str, str]:
    from ..main import _read_clipboard_text

    return await _read_clipboard_text(profile_id)
