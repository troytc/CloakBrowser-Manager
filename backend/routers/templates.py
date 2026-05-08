"""Admin CRUD router for vendor templates (TMPL-02, TMPL-03, TMPL-04).

Registered under /api/templates. Sits behind the app-level AuthMiddleware —
no _AUTH_EXEMPT entry is added (CLAUDE.md security rule 3).
"""

from __future__ import annotations

import json
import logging
from sqlite3 import IntegrityError
from typing import Any

from fastapi import APIRouter, HTTPException

from .. import database as db
from ..models import (
    TemplateBlueprint,
    VendorTemplateCreate,
    VendorTemplateResponse,
    VendorTemplateUpdate,
)

logger = logging.getLogger("cloakbrowser.manager.templates")
router = APIRouter(prefix="/api/templates", tags=["templates"])


def _row_to_response(row: dict[str, Any]) -> VendorTemplateResponse:
    blueprint = TemplateBlueprint.model_validate(json.loads(row["blueprint"]))
    return VendorTemplateResponse(
        id=row["id"],
        vendor_type=row["vendor_type"],
        label=row["label"],
        notes=row["notes"],
        blueprint=blueprint,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


@router.get("", response_model=list[VendorTemplateResponse])
async def list_templates() -> list[VendorTemplateResponse]:
    rows = db.list_templates()
    return [_row_to_response(r) for r in rows]


@router.post("", response_model=VendorTemplateResponse, status_code=201)
async def create_template(payload: VendorTemplateCreate) -> VendorTemplateResponse:
    # Emit blueprint with default model_dump_json (no exclude_defaults) — Pitfall 3.
    blueprint_json = payload.blueprint.model_dump_json()
    try:
        row = db.create_template(
            vendor_type=payload.vendor_type,
            label=payload.label,
            notes=payload.notes,
            blueprint_json=blueprint_json,
        )
    except IntegrityError as exc:
        # UNIQUE(vendor_type) violation — surface as 409
        raise HTTPException(
            status_code=409,
            detail=f"A template for vendor_type '{payload.vendor_type}' already exists",
        ) from exc
    return _row_to_response(row)


@router.get("/{template_id}", response_model=VendorTemplateResponse)
async def get_template(template_id: str) -> VendorTemplateResponse:
    row = db.get_template(template_id)
    if not row:
        raise HTTPException(status_code=404, detail="Template not found")
    return _row_to_response(row)


@router.put("/{template_id}", response_model=VendorTemplateResponse)
async def update_template(
    template_id: str, payload: VendorTemplateUpdate
) -> VendorTemplateResponse:
    fields: dict[str, Any] = {}
    data = payload.model_dump(exclude_unset=True)
    if "label" in data:
        fields["label"] = data["label"]
    if "notes" in data:
        fields["notes"] = data["notes"]
    if "blueprint" in data and payload.blueprint is not None:
        fields["blueprint_json"] = payload.blueprint.model_dump_json()
    row = db.update_template(template_id, **fields)
    if row is None:
        raise HTTPException(status_code=404, detail="Template not found")
    return _row_to_response(row)


@router.delete("/{template_id}")
async def delete_template(template_id: str) -> dict[str, bool]:
    # 404 first — don't leak whether the template existed via the 409 path
    if db.get_template(template_id) is None:
        raise HTTPException(status_code=404, detail="Template not found")

    # ① App-layer check (D-06 belt)
    blocking = db.list_profiles_by_template(template_id)
    if blocking:
        raise HTTPException(
            status_code=409,
            detail={
                "detail": (
                    f"Template has {len(blocking)} attached profile(s); "
                    "delete or reassign them first"
                ),
                "blocking_profile_ids": blocking,
            },
        )

    # ② DB-layer safety net (D-06 suspenders) — FK ON DELETE RESTRICT
    try:
        deleted = db.delete_template(template_id)
    except IntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail="Template acquired a profile reference during deletion; retry",
        ) from exc
    if not deleted:
        # Another caller deleted it in between the get_template check and here
        raise HTTPException(status_code=404, detail="Template not found")
    return {"ok": True}
