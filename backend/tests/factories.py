"""Test helpers for creating DB rows without removed admin HTTP routes."""

from __future__ import annotations

from typing import Any

from backend import database as db


def create_test_profile(name: str = "Test", **fields: Any) -> dict[str, Any]:
    """Insert a profile row via database layer (OPS-02 admin create removed)."""
    return db.create_profile(name=name, **fields)
