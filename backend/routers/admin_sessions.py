"""Admin ops list for all profiles + warm-pool telemetry (Phase 4: ADM-02)."""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, Request

from .. import database as db
from ..models import AdminSessionListItem

if TYPE_CHECKING:
    from ..session_manager import SessionManager

router = APIRouter(prefix="/api/admin/sessions", tags=["admin-sessions"])


def get_session_manager(request: Request) -> "SessionManager":
    return request.app.state.session_manager


def _parse_iso(iso: str | None) -> datetime.datetime | None:
    if not iso:
        return None
    try:
        return datetime.datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return None


@router.get("", response_model=list[AdminSessionListItem])
async def list_admin_sessions(
    sm: "SessionManager" = Depends(get_session_manager),
) -> list[AdminSessionListItem]:
    """All DB profiles merged with live session state (admin cookie auth only)."""
    now = datetime.datetime.now(datetime.timezone.utc)
    items: list[AdminSessionListItem] = []

    for row in db.list_profiles():
        profile_id = row["id"]
        env = sm.status_envelope(profile_id)

        uptime_seconds: int | None = None
        if env.state in ("running", "idle"):
            launched = _parse_iso(env.last_launched_at)
            if launched is not None:
                uptime_seconds = max(0, int((now - launched).total_seconds()))

        items.append(
            AdminSessionListItem(
                profile_id=profile_id,
                name=row["name"],
                vendor_type=row.get("vendor_type") or "",
                vendor_connection_id=row.get("vendor_connection_id") or "",
                state=env.state,
                cdp_attach_count=env.cdp_attach_count,
                viewer_attach_count=env.viewer_attach_count,
                idle_expires_at=env.idle_expires_at,
                last_launched_at=env.last_launched_at,
                uptime_seconds=uptime_seconds,
                clipboard_sync=bool(row.get("clipboard_sync") or False),
            )
        )

    items.sort(key=lambda i: (i.last_launched_at or "", i.vendor_type), reverse=True)
    return items
