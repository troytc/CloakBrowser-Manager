"""Tests for SQLite CRUD operations."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from backend import database as db


# ── init_db ──────────────────────────────────────────────────────────────────


def test_init_db_creates_tables(tmp_db: Path):
    with db.get_db() as conn:
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        names = {r["name"] for r in tables}
    assert "profiles" in names
    assert "profile_tags" in names


def test_init_db_idempotent(tmp_db: Path):
    # Second call should not crash
    db.init_db()
    with db.get_db() as conn:
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    assert len(tables) >= 2


# ── create_profile ───────────────────────────────────────────────────────────


def test_create_profile_minimal(tmp_db: Path):
    p = db.create_profile("Test")
    assert p["name"] == "Test"
    assert isinstance(p["id"], str) and len(p["id"]) == 36  # UUID
    assert 10000 <= p["fingerprint_seed"] <= 99999  # random default
    assert p["user_data_dir"].startswith(str(tmp_db))
    assert p["platform"] == "windows"
    assert p["created_at"] is not None
    assert p["updated_at"] is not None


def test_create_profile_with_seed(tmp_db: Path):
    p = db.create_profile("Seeded", fingerprint_seed=42)
    assert p["fingerprint_seed"] == 42


def test_create_profile_all_fields(tmp_db: Path):
    p = db.create_profile(
        "Full",
        fingerprint_seed=99999,
        proxy="http://host:8080",
        timezone="America/New_York",
        locale="en-US",
        platform="macos",
        user_agent="Test UA",
        screen_width=2560,
        screen_height=1440,
        gpu_vendor="NVIDIA",
        gpu_renderer="RTX 3070",
        hardware_concurrency=16,
        humanize=True,
        human_preset="careful",
        headless=True,
        geoip=True,
        color_scheme="dark",
        notes="test note",
    )
    assert p["proxy"] == "http://host:8080"
    assert p["platform"] == "macos"
    assert p["gpu_vendor"] == "NVIDIA"
    assert p["hardware_concurrency"] == 16
    assert p["humanize"] == 1  # SQLite stores bool as int
    assert p["human_preset"] == "careful"
    assert p["color_scheme"] == "dark"


def test_create_profile_with_tags(tmp_db: Path):
    p = db.create_profile(
        "Tagged",
        tags=[
            {"tag": "work", "color": "#ff0000"},
            {"tag": "dev", "color": "#00ff00"},
        ],
    )
    assert len(p["tags"]) == 2
    tag_names = {t["tag"] for t in p["tags"]}
    assert tag_names == {"work", "dev"}


def test_create_profile_defaults(tmp_db: Path):
    p = db.create_profile("Defaults")
    assert p["platform"] == "windows"
    assert p["screen_width"] == 1920
    assert p["screen_height"] == 1080
    assert p["humanize"] == 0
    assert p["headless"] == 0
    assert p["geoip"] == 0
    assert p["human_preset"] == "default"
    assert p["launch_args"] == []


def test_create_profile_with_launch_args(tmp_db: Path):
    p = db.create_profile("WithArgs", launch_args=["--load-extension=/tmp/ext", "--disable-features=Foo"])
    assert p["launch_args"] == ["--load-extension=/tmp/ext", "--disable-features=Foo"]


def test_get_profile_launch_args_roundtrip(tmp_db: Path):
    p = db.create_profile("Args", launch_args=["--flag1", "--flag2"])
    fetched = db.get_profile(p["id"])
    assert fetched["launch_args"] == ["--flag1", "--flag2"]


def test_update_profile_launch_args(tmp_db: Path):
    p = db.create_profile("Args")
    assert p["launch_args"] == []
    updated = db.update_profile(p["id"], launch_args=["--new-flag"])
    assert updated["launch_args"] == ["--new-flag"]


def test_update_profile_launch_args_none_becomes_empty(tmp_db: Path):
    p = db.create_profile("Args", launch_args=["--flag"])
    updated = db.update_profile(p["id"], launch_args=None)
    assert updated["launch_args"] == []


def test_list_profiles_includes_launch_args(tmp_db: Path):
    db.create_profile("A", launch_args=["--arg1"])
    db.create_profile("B")
    profiles = db.list_profiles()
    args_by_name = {p["name"]: p["launch_args"] for p in profiles}
    assert args_by_name["A"] == ["--arg1"]
    assert args_by_name["B"] == []


# ── get_profile ──────────────────────────────────────────────────────────────


def test_get_profile_exists(sample_profile: dict):
    p = db.get_profile(sample_profile["id"])
    assert p is not None
    assert p["name"] == "Test Profile"
    assert p["fingerprint_seed"] == 12345


def test_get_profile_not_found(tmp_db: Path):
    assert db.get_profile("nonexistent") is None


def test_get_profile_includes_tags(tmp_db: Path):
    p = db.create_profile("Tagged", tags=[{"tag": "test", "color": "#aaa"}])
    fetched = db.get_profile(p["id"])
    assert len(fetched["tags"]) == 1
    assert fetched["tags"][0]["tag"] == "test"


# ── list_profiles ────────────────────────────────────────────────────────────


def test_list_profiles_empty(tmp_db: Path):
    assert db.list_profiles() == []


def test_list_profiles_ordered(tmp_db: Path):
    db.create_profile("First")
    time.sleep(0.01)  # ensure different timestamps
    db.create_profile("Second")
    profiles = db.list_profiles()
    assert len(profiles) == 2
    assert profiles[0]["name"] == "Second"  # newest first


def test_list_profiles_includes_tags(tmp_db: Path):
    db.create_profile("Tagged", tags=[{"tag": "x"}])
    profiles = db.list_profiles()
    assert len(profiles[0]["tags"]) == 1


# ── update_profile ───────────────────────────────────────────────────────────


def test_update_profile_partial(sample_profile: dict):
    updated = db.update_profile(sample_profile["id"], name="Renamed")
    assert updated["name"] == "Renamed"
    assert updated["fingerprint_seed"] == 12345  # unchanged


def test_update_profile_tags_replace(tmp_db: Path):
    p = db.create_profile("Tagged", tags=[{"tag": "old"}])
    updated = db.update_profile(p["id"], tags=[{"tag": "new", "color": "#fff"}])
    assert len(updated["tags"]) == 1
    assert updated["tags"][0]["tag"] == "new"


def test_update_profile_not_found(tmp_db: Path):
    assert db.update_profile("nonexistent", name="x") is None


def test_update_profile_no_fields(sample_profile: dict):
    # No-op update — profile should be unchanged
    updated = db.update_profile(sample_profile["id"])
    assert updated["name"] == sample_profile["name"]


def test_update_profile_updates_timestamp(sample_profile: dict):
    time.sleep(0.01)
    updated = db.update_profile(sample_profile["id"], name="New")
    assert updated["updated_at"] > sample_profile["created_at"]


# ── delete_profile ───────────────────────────────────────────────────────────


def test_delete_profile_exists(sample_profile: dict):
    assert db.delete_profile(sample_profile["id"]) is True
    assert db.get_profile(sample_profile["id"]) is None


def test_delete_profile_not_found(tmp_db: Path):
    assert db.delete_profile("nonexistent") is False


def test_delete_profile_cascades_tags(tmp_db: Path):
    p = db.create_profile("Tagged", tags=[{"tag": "a"}, {"tag": "b"}])
    db.delete_profile(p["id"])
    # Verify tags are gone
    with db.get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM profile_tags WHERE profile_id = ?", (p["id"],)
        ).fetchall()
    assert len(rows) == 0


# ── Phase 2: upsert_profile_by_vendor / list_profiles_filtered ─────────────


import json as _json
import sqlite3 as _sqlite3
from unittest.mock import patch as _patch

from backend.database import (
    NoTemplateError,
    create_template,
    list_profiles_filtered,
    update_template,
    upsert_profile_by_vendor,
)


def _seed_template(vendor_type: str = "acme", **blueprint_overrides) -> dict:
    blueprint = {
        "timezone": "America/New_York",
        "locale": "en-US",
        "platform": "windows",
        "screen_width": 1920,
        "screen_height": 1080,
        "humanize": False,
        "human_preset": "default",
        "launch_args": [],
        "clipboard_sync": False,
    }
    blueprint.update(blueprint_overrides)
    return create_template(
        vendor_type=vendor_type,
        label=f"{vendor_type} template",
        notes=None,
        blueprint_json=_json.dumps(blueprint),
    )


def test_upsert_creates_new_profile_when_template_exists(tmp_db: Path):
    template = _seed_template("acme", timezone="UTC")
    profile = upsert_profile_by_vendor("acme", "user-1")
    assert profile["vendor_type"] == "acme"
    assert profile["vendor_connection_id"] == "user-1"
    assert profile["template_id"] == template["id"]
    assert profile["timezone"] == "UTC"
    with db.get_db() as conn:
        rows = conn.execute(
            "SELECT id FROM profiles WHERE vendor_type=? AND vendor_connection_id=?",
            ("acme", "user-1"),
        ).fetchall()
    assert len(rows) == 1


def test_upsert_returns_existing_profile_unchanged(tmp_db: Path):
    template = _seed_template("acme", timezone="UTC")
    first = upsert_profile_by_vendor("acme", "user-1")
    update_template(
        template["id"],
        blueprint_json=_json.dumps(
            {
                "timezone": "Europe/London",
                "locale": "en-GB",
                "platform": "windows",
                "screen_width": 1920,
                "screen_height": 1080,
                "humanize": False,
                "human_preset": "default",
                "launch_args": [],
                "clipboard_sync": False,
            }
        ),
    )
    second = upsert_profile_by_vendor("acme", "user-1")
    assert second["id"] == first["id"]
    assert second["timezone"] == "UTC"
    with db.get_db() as conn:
        rows = conn.execute(
            "SELECT id FROM profiles WHERE vendor_type=? AND vendor_connection_id=?",
            ("acme", "user-1"),
        ).fetchall()
    assert len(rows) == 1


def test_upsert_raises_no_template_error_when_no_template(tmp_db: Path):
    with pytest.raises(NoTemplateError) as exc_info:
        upsert_profile_by_vendor("nonexistent", "user-1")
    assert exc_info.value.vendor_type == "nonexistent"
    assert "nonexistent" in str(exc_info.value)


def test_upsert_handles_integrity_error_via_reselect(tmp_db: Path):
    _seed_template("acme")
    pre_existing = upsert_profile_by_vendor("acme", "user-1")
    with db.get_db() as conn:
        conn.execute("DELETE FROM profiles WHERE id = ?", (pre_existing["id"],))
        conn.commit()

    inserted_id = {"id": None}

    def _race_insert(template, vendor_connection_id, name=None):
        with db.get_db() as conn:
            new_id = "race-winner-id"
            inserted_id["id"] = new_id
            conn.execute(
                "INSERT INTO profiles (id, name, fingerprint_seed, vendor_type, "
                "vendor_connection_id, template_id, user_data_dir, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))",
                (
                    new_id,
                    "racer",
                    99999,
                    template["vendor_type"],
                    vendor_connection_id,
                    template["id"],
                    "/tmp/racer",
                ),
            )
            conn.commit()
        raise _sqlite3.IntegrityError("UNIQUE constraint failed: idx_profiles_vendor_pair")

    with _patch("backend.database.create_profile_from_template", side_effect=_race_insert):
        result = upsert_profile_by_vendor("acme", "user-1")

    assert result["id"] == inserted_id["id"]
    assert result["vendor_type"] == "acme"


def test_list_profiles_filtered_returns_empty_for_no_match(tmp_db: Path):
    _seed_template("acme")
    upsert_profile_by_vendor("acme", "user-1")
    out = list_profiles_filtered(vendor_type="other")
    assert out == []


def test_list_profiles_filtered_returns_match_for_pair(tmp_db: Path):
    _seed_template("acme")
    profile = upsert_profile_by_vendor("acme", "user-1")
    out = list_profiles_filtered(vendor_type="acme", vendor_connection_id="user-1")
    assert len(out) == 1
    assert out[0]["id"] == profile["id"]


def test_list_profiles_filtered_returns_all_for_no_filter(tmp_db: Path):
    _seed_template("acme")
    _seed_template("globex")
    upsert_profile_by_vendor("acme", "user-1")
    upsert_profile_by_vendor("globex", "user-2")
    out = list_profiles_filtered()
    assert len(out) == 2


def test_unique_constraint_enforced_at_db_layer(tmp_db: Path):
    _seed_template("acme")
    upsert_profile_by_vendor("acme", "user-1")
    with db.get_db() as conn:
        with pytest.raises(_sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO profiles (id, name, fingerprint_seed, vendor_type, "
                "vendor_connection_id, user_data_dir, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))",
                ("dup-id", "dup", 11111, "acme", "user-1", "/tmp/dup"),
            )
            conn.commit()
