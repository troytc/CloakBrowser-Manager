"""Signed viewer routes (Phase 3: VIEW-01, VIEW-05, VIEW-06).

GET  /viewer/{profile_id}     — minimal noVNC shell (token in #fragment)
WS   /viewer/{profile_id}/ws  — VNC proxy gated by ?token= JWT

No API-key or admin cookie required; JWT is the capability.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from .. import database as db
from ..viewer_tokens import (
    ViewerTokenError,
    ViewerTokenExpired,
    ViewerTokenInvalid,
    ViewerTokenProfileMismatch,
    ViewerTokenReplay,
    validate_viewer_token,
)

if TYPE_CHECKING:
    from ..browser_manager import BrowserManager, RunningProfile
    from ..session_manager import SessionManager

logger = logging.getLogger("vendorbrowser.viewer_router")

router = APIRouter(prefix="/viewer", tags=["viewer"])

_VIEWER_EMBED_JS = Path(__file__).resolve().parent.parent / "static" / "viewer_embed.js"

_VIEWER_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>VendorBrowser Viewer</title>
  <style>
    html, body { margin: 0; height: 100%; background: #111; overflow: hidden; }
    #screen { width: 100%; height: 100%; }
    #error { color: #f88; padding: 1rem; font-family: system-ui, sans-serif; }
  </style>
</head>
<body>
  <div id="screen"></div>
  <div id="error" hidden></div>
  <script type="module" src="/viewer/static/embed.js"></script>
</body>
</html>
"""


def _get_browser_mgr(request: Request) -> "BrowserManager":
    from ..main import browser_mgr

    return browser_mgr


def _get_session_manager(request: Request) -> "SessionManager":
    return request.app.state.session_manager


def _viewer_response_headers() -> dict[str, str]:
    return {
        "Content-Security-Policy": _viewer_csp(),
        "X-Frame-Options": "DENY",
    }


@router.get("/static/embed.js")
async def viewer_embed_js() -> FileResponse:
    """External viewer bootstrap (CSP script-src 'self' — no inline script)."""
    return FileResponse(_VIEWER_EMBED_JS, media_type="application/javascript")


@router.get("/{profile_id}")
async def viewer_page(profile_id: str) -> HTMLResponse:
    """Serve noVNC shell; token must be in URL fragment (VIEW-04)."""
    # Reject path segments like "id/ws" — only the HTML page route, not WS subpaths.
    if "/" in profile_id:
        raise HTTPException(status_code=404, detail="Not found")

    return HTMLResponse(
        content=_VIEWER_HTML,
        headers=_viewer_response_headers(),
    )


def _viewer_csp() -> str:
    from ..security_csp import viewer_frame_ancestors_header

    return viewer_frame_ancestors_header()


@router.websocket("/{profile_id}/ws")
async def viewer_vnc_ws(
    websocket: WebSocket,
    profile_id: str,
    token: str = Query(..., description="Viewer JWT from #fragment"),
) -> None:
    """VNC WebSocket proxy authenticated by signed viewer token (VIEW-05)."""
    from ..main import (
        _check_websocket_origin,
        _run_vnc_proxy,
        browser_mgr,
    )

    if not await _check_websocket_origin(websocket):
        return

    try:
        await validate_viewer_token(token, profile_id, consume_jti=True)
    except ViewerTokenExpired:
        await websocket.close(code=4401, reason="Viewer token expired")
        return
    except ViewerTokenReplay:
        await websocket.close(code=4403, reason="Viewer token already used")
        return
    except (ViewerTokenInvalid, ViewerTokenProfileMismatch, ViewerTokenError):
        await websocket.close(code=4401, reason="Invalid viewer token")
        return

    running = browser_mgr.running.get(profile_id)
    if not running:
        await websocket.close(code=4004, reason="Profile not running")
        return

    sm = websocket.app.state.session_manager

    async with browser_mgr._lock:
        running.viewer_attach_count += 1
    sm.on_attach(profile_id)

    try:
        await _run_vnc_proxy(websocket, running, profile_id)
    except WebSocketDisconnect:
        pass
    finally:
        async with browser_mgr._lock:
            running.viewer_attach_count = max(0, running.viewer_attach_count - 1)
            both_zero = (
                running.cdp_attach_count == 0
                and running.viewer_attach_count == 0
            )
        if both_zero:
            sm.on_all_detached(profile_id)


@router.get("/{profile_id}/clipboard")
async def viewer_get_clipboard(
    profile_id: str,
    token: str = Query(..., description="Viewer JWT from #fragment"),
) -> JSONResponse:
    """SEC-07: clipboard read gated by viewer token + profile clipboard_sync."""
    try:
        await validate_viewer_token(token, profile_id, consume_jti=False)
    except ViewerTokenExpired:
        raise HTTPException(status_code=401, detail="Viewer token expired") from None
    except (ViewerTokenInvalid, ViewerTokenProfileMismatch, ViewerTokenError) as exc:
        raise HTTPException(status_code=401, detail="Invalid viewer token") from exc

    profile = db.get_profile(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    if not profile.get("clipboard_sync"):
        raise HTTPException(status_code=403, detail="Clipboard sync disabled for this profile")

    from ..main import _read_clipboard_text

    return JSONResponse(await _read_clipboard_text(profile_id))
