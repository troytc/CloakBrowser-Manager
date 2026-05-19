"""Machine-API router for /profiles/* (Phase 2: PROF-01, PROF-02, PROF-03, PROF-04).

Mounted at /profiles. All routes gated by Depends(require_api_key) — strictly
segregated from /admin/* (CLAUDE.md security rule 3, CONTEXT.md D-10/D-12).

CONTEXT.md D-20: list endpoints return [] on no match (NOT 404). 404 only on
single-item lookup (/profiles/{id}).
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from .. import database as db
from ..auth_api_key import require_api_key
from ..models import MachineProfileResponse, ProfilePatch

if TYPE_CHECKING:
    from ..session_manager import SessionManager

logger = logging.getLogger("vendorbrowser.profiles_router")

router = APIRouter(
    prefix="/profiles",
    tags=["profiles"],
    dependencies=[Depends(require_api_key)],
)


def get_session_manager(request: Request) -> "SessionManager":
    return request.app.state.session_manager


def _to_response(profile_row: dict) -> MachineProfileResponse:
    """Project a profile DB row to MachineProfileResponse (PROF-01/PROF-02 wire shape)."""
    return MachineProfileResponse(
        id=profile_row["id"],
        name=profile_row["name"],
        vendor_type=profile_row["vendor_type"],
        vendor_connection_id=profile_row["vendor_connection_id"],
        template_id=profile_row.get("template_id"),
        notes=profile_row.get("notes"),
        user_data_dir=profile_row["user_data_dir"],
        created_at=profile_row["created_at"],
        updated_at=profile_row["updated_at"],
        timezone=profile_row.get("timezone"),
        locale=profile_row.get("locale"),
        platform=profile_row.get("platform") or "windows",
        screen_width=profile_row.get("screen_width") or 1920,
        screen_height=profile_row.get("screen_height") or 1080,
        clipboard_sync=bool(profile_row.get("clipboard_sync") or False),
    )


@router.get("", response_model=list[MachineProfileResponse])
async def list_profiles(
    vendor_type: str | None = Query(default=None),
    vendor_connection_id: str | None = Query(default=None),
) -> list[MachineProfileResponse]:
    """PROF-01 / PROF-02 / D-20: filtered list, returns [] on no match."""
    rows = db.list_profiles_filtered(
        vendor_type=vendor_type,
        vendor_connection_id=vendor_connection_id,
    )
    return [_to_response(r) for r in rows]


@router.get("/{profile_id}", response_model=MachineProfileResponse)
async def get_profile(profile_id: str) -> MachineProfileResponse:
    """Single-item lookup; 404 on miss (D-20)."""
    row = db.get_profile(profile_id)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={"detail": "Profile not found", "profile_id": profile_id},
        )
    return _to_response(row)


@router.patch("/{profile_id}", response_model=MachineProfileResponse)
async def patch_profile(profile_id: str, payload: ProfilePatch) -> MachineProfileResponse:
    """PROF-03: admin-owned fields only (notes in v1).

    Identity keys, clipboard_sync, and any unknown fields are rejected by
    ProfilePatch's extra='forbid' config — Pydantic returns 422 before this
    handler runs.
    """
    fields = payload.model_dump(exclude_unset=True)
    if not fields:
        # No-op patch — return current state instead of 400 (idempotent)
        existing = db.get_profile(profile_id)
        if existing is None:
            raise HTTPException(
                status_code=404,
                detail={"detail": "Profile not found", "profile_id": profile_id},
            )
        return _to_response(existing)

    row = db.update_profile(profile_id, **fields)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={"detail": "Profile not found", "profile_id": profile_id},
        )
    return _to_response(row)


@router.delete("/{profile_id}", status_code=204)
async def delete_profile(
    profile_id: str,
    sm: "SessionManager" = Depends(get_session_manager),
) -> Response:
    """PROF-04: destructive — stop the browser, drop the row, remove the on-disk
    profile dir. Returns 204 on success, 404 on miss.
    """
    from ..main import browser_mgr  # late import: avoid circular

    profile = db.get_profile(profile_id)
    if profile is None:
        raise HTTPException(
            status_code=404,
            detail={"detail": "Profile not found", "profile_id": profile_id},
        )

    # 1. Stop browser if running (idempotent)
    if profile_id in browser_mgr.running:
        await browser_mgr.stop(profile_id)

    # 2. Cancel any pending idle timer
    sm._cancel_idle(profile_id)

    # 3. Remove the per-key lock entry (Claude's discretion — prevent unbounded growth)
    sm.remove_key_lock(profile["vendor_type"], profile["vendor_connection_id"])

    # 4. Drop DB row
    db.delete_profile(profile_id)

    # 5. Remove on-disk profile directory (PROF-04: destructive)
    user_data_dir = Path(profile["user_data_dir"])
    if user_data_dir.exists():
        shutil.rmtree(user_data_dir, ignore_errors=True)

    logger.info(
        "event=profile_delete profile_id=%s vendor_type=%s vendor_connection_id=%s",
        profile_id, profile["vendor_type"], profile["vendor_connection_id"],
    )

    return Response(status_code=204)
