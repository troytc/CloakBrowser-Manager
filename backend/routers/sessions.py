"""Machine-API router for /sessions/* (Phase 2: SESS-01, SESS-02, SESS-13, SESS-14).

Mounted at /sessions (no /api prefix). All routes gated by
Depends(require_api_key) — strictly segregated from /admin/*
(CLAUDE.md security rule 3, CONTEXT.md D-10/D-12).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from .. import database as db
from ..auth_api_key import require_api_key
from ..browser_manager import BrowserLaunchError
from ..database import NoTemplateError
from ..models import (
    SessionListItem,
    SessionRequest,
    SessionResponse,
    SessionStatusResponse,
)

if TYPE_CHECKING:
    from ..session_manager import SessionManager

logger = logging.getLogger("vendorbrowser.sessions_router")

router = APIRouter(
    prefix="/sessions",
    tags=["sessions"],
    dependencies=[Depends(require_api_key)],
)


def get_session_manager(request: Request) -> "SessionManager":
    return request.app.state.session_manager


@router.post("", response_model=SessionResponse)
async def post_session(
    payload: SessionRequest,
    sm: "SessionManager" = Depends(get_session_manager),
) -> SessionResponse:
    """Idempotent upsert + wake (SESS-01, SESS-02, SESS-03, SESS-07).

    Errors per CONTEXT.md D-16:
      - 200 happy path
      - 400 invalid input (Pydantic)
      - 401 missing/invalid X-API-Key (Depends)
      - 404 no template (NoTemplateError)
      - 503 launch failure (BrowserLaunchError; sanitized reason)
    """
    try:
        result = await sm.get_or_wake(payload.vendor_type, payload.vendor_connection_id)
    except NoTemplateError as exc:
        raise HTTPException(
            status_code=404,
            detail={
                "detail": f"No template for vendor_type={exc.vendor_type!r}",
                "vendor_type": exc.vendor_type,
            },
        ) from exc
    except BrowserLaunchError as exc:
        logger.warning(
            "event=launch_failed vendor_type=%s vendor_connection_id=%s reason=%s",
            payload.vendor_type, payload.vendor_connection_id, exc,
        )
        raise HTTPException(
            status_code=503,
            detail={
                "detail": "Browser launch failed",
                "reason": str(exc),
            },
        ) from exc

    return SessionResponse(
        profile_id=result.profile_id,
        cdp_url=result.cdp_url,
        vnc_viewer_url=result.vnc_viewer_url,
        state=result.state,
    )


@router.get("", response_model=list[SessionListItem])
async def list_sessions(
    sm: "SessionManager" = Depends(get_session_manager),
) -> list[SessionListItem]:
    """List active sessions (D-14). Returns profiles currently in
    browser_mgr.running, sorted by last_launched_at desc.

    Empty list if nothing is running (NOT 404 — D-20).
    """
    from ..main import browser_mgr  # late import: avoid circular at module import

    items: list[SessionListItem] = []
    profile_ids = list(browser_mgr.running.keys())  # snapshot
    for pid in profile_ids:
        envelope = sm.status_envelope(pid)
        prof = db.get_profile(pid)
        if prof is None:
            continue  # edge: row gone (DELETE /profiles in flight)
        items.append(SessionListItem(
            profile_id=pid,
            vendor_type=prof["vendor_type"],
            vendor_connection_id=prof["vendor_connection_id"],
            state=envelope.state,
            cdp_attach_count=envelope.cdp_attach_count,
            viewer_attach_count=envelope.viewer_attach_count,
            idle_expires_at=envelope.idle_expires_at,
            last_launched_at=envelope.last_launched_at,
        ))

    # Sort by last_launched_at desc; None sorts last
    none_items = [i for i in items if i.last_launched_at is None]
    dated_items = [i for i in items if i.last_launched_at is not None]
    dated_items.sort(key=lambda i: i.last_launched_at, reverse=True)
    return dated_items + none_items


@router.get("/{profile_id}", response_model=SessionStatusResponse)
async def get_session_status(
    profile_id: str,
    sm: "SessionManager" = Depends(get_session_manager),
) -> SessionStatusResponse:
    """SESS-13 / D-18 envelope. 404 if profile_id unknown to DB."""
    if db.get_profile(profile_id) is None:
        raise HTTPException(
            status_code=404,
            detail={"detail": "Profile not found", "profile_id": profile_id},
        )
    env = sm.status_envelope(profile_id)
    return SessionStatusResponse(
        state=env.state,
        cdp_attach_count=env.cdp_attach_count,
        viewer_attach_count=env.viewer_attach_count,
        idle_expires_at=env.idle_expires_at,
        last_launched_at=env.last_launched_at,
    )


@router.delete("/{profile_id}", status_code=204)
async def delete_session(
    profile_id: str,
    sm: "SessionManager" = Depends(get_session_manager),
) -> Response:
    """SESS-14 / D-17: stop the browser, leave the row + dir untouched.
    Idempotent (204 even if not running). 404 only if profile_id unknown to DB.
    """
    from ..main import browser_mgr  # late import

    if db.get_profile(profile_id) is None:
        raise HTTPException(
            status_code=404,
            detail={"detail": "Profile not found", "profile_id": profile_id},
        )

    sm._cancel_idle(profile_id)

    if profile_id in browser_mgr.running:
        await browser_mgr.stop(profile_id)
        logger.info("event=session_delete profile_id=%s reason=manual", profile_id)

    return Response(status_code=204)
