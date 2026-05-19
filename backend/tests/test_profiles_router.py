"""Integration tests for backend/routers/profiles.py (PROF-01..04)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from backend import database as db
from backend.database import create_template


def _seed_template(vendor_type: str = "acme") -> dict:
    blueprint = {
        "timezone": "UTC", "locale": "en-US", "platform": "windows",
        "screen_width": 1920, "screen_height": 1080, "humanize": False,
        "human_preset": "default", "launch_args": [], "clipboard_sync": False,
    }
    return create_template(
        vendor_type=vendor_type,
        label=f"{vendor_type} template",
        notes=None,
        blueprint_json=json.dumps(blueprint),
    )


@pytest.mark.asyncio
async def test_get_profiles_returns_empty_list_when_no_profiles(async_client, auth_headers):
    r = await async_client.get("/profiles", headers=auth_headers)
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_get_profiles_no_filter_returns_all(async_client, auth_headers):
    _seed_template("acme")
    _seed_template("globex")
    db.upsert_profile_by_vendor("acme", "u1")
    db.upsert_profile_by_vendor("globex", "u2")
    r = await async_client.get("/profiles", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 2


@pytest.mark.asyncio
async def test_get_profiles_filter_by_vendor_type(async_client, auth_headers):
    _seed_template("acme")
    _seed_template("globex")
    db.upsert_profile_by_vendor("acme", "u1")
    db.upsert_profile_by_vendor("globex", "u2")
    r = await async_client.get("/profiles?vendor_type=acme", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["vendor_type"] == "acme"


@pytest.mark.asyncio
async def test_get_profiles_filter_by_pair(async_client, auth_headers):
    _seed_template("acme")
    db.upsert_profile_by_vendor("acme", "u1")
    db.upsert_profile_by_vendor("acme", "u2")
    r = await async_client.get(
        "/profiles?vendor_type=acme&vendor_connection_id=u1", headers=auth_headers
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["vendor_connection_id"] == "u1"


@pytest.mark.asyncio
async def test_get_profiles_filter_no_match_returns_empty_list(async_client, auth_headers):
    _seed_template("acme")
    db.upsert_profile_by_vendor("acme", "u1")
    r = await async_client.get("/profiles?vendor_type=nonexistent", headers=auth_headers)
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_get_profile_by_id_returns_match(async_client, auth_headers):
    _seed_template("acme")
    profile = db.upsert_profile_by_vendor("acme", "u1")
    r = await async_client.get(f"/profiles/{profile['id']}", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == profile["id"]
    assert body["vendor_type"] == "acme"


@pytest.mark.asyncio
async def test_get_profile_by_id_404_on_miss(async_client, auth_headers):
    r = await async_client.get("/profiles/nonexistent", headers=auth_headers)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_patch_profile_updates_notes(async_client, auth_headers):
    _seed_template("acme")
    profile = db.upsert_profile_by_vendor("acme", "u1")
    r = await async_client.patch(
        f"/profiles/{profile['id']}",
        json={"notes": "hello world"},
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert r.json()["notes"] == "hello world"
    r2 = await async_client.get(f"/profiles/{profile['id']}", headers=auth_headers)
    assert r2.json()["notes"] == "hello world"


@pytest.mark.asyncio
async def test_patch_profile_rejects_clipboard_sync(async_client, auth_headers):
    _seed_template("acme")
    profile = db.upsert_profile_by_vendor("acme", "u1")
    r = await async_client.patch(
        f"/profiles/{profile['id']}",
        json={"clipboard_sync": True},
        headers=auth_headers,
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_patch_profile_rejects_vendor_type(async_client, auth_headers):
    _seed_template("acme")
    profile = db.upsert_profile_by_vendor("acme", "u1")
    r = await async_client.patch(
        f"/profiles/{profile['id']}",
        json={"vendor_type": "globex"},
        headers=auth_headers,
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_patch_profile_rejects_vendor_connection_id(async_client, auth_headers):
    _seed_template("acme")
    profile = db.upsert_profile_by_vendor("acme", "u1")
    r = await async_client.patch(
        f"/profiles/{profile['id']}",
        json={"vendor_connection_id": "different"},
        headers=auth_headers,
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_patch_profile_404_on_unknown_id(async_client, auth_headers):
    r = await async_client.patch(
        "/profiles/nonexistent",
        json={"notes": "x"},
        headers=auth_headers,
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_delete_profile_returns_204_drops_row_and_dir(async_client, auth_headers, tmp_db):
    _seed_template("acme")
    profile = db.upsert_profile_by_vendor("acme", "u1")
    user_data_dir = Path(profile["user_data_dir"])
    user_data_dir.mkdir(parents=True, exist_ok=True)
    (user_data_dir / "marker.txt").write_text("present")

    r = await async_client.delete(f"/profiles/{profile['id']}", headers=auth_headers)
    assert r.status_code == 204
    assert db.get_profile(profile["id"]) is None
    assert not user_data_dir.exists()


@pytest.mark.asyncio
async def test_delete_profile_stops_running_browser_first(async_client, auth_headers, mock_browser_manager):
    from backend.browser_manager import RunningProfile
    _seed_template("acme")
    profile = db.upsert_profile_by_vendor("acme", "u1")
    rp = RunningProfile(
        profile_id=profile["id"], context=None, display=99,
        ws_port=6199, cdp_port=5100,
    )
    mock_browser_manager.running[profile["id"]] = rp

    r = await async_client.delete(f"/profiles/{profile['id']}", headers=auth_headers)
    assert r.status_code == 204
    mock_browser_manager.stop.assert_awaited_with(profile["id"])
    assert db.get_profile(profile["id"]) is None


@pytest.mark.asyncio
async def test_delete_profile_404_when_unknown(async_client, auth_headers):
    r = await async_client.delete("/profiles/nonexistent", headers=auth_headers)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_delete_profile_removes_per_key_lock(async_client, auth_headers):
    from backend import main
    _seed_template("acme")
    profile = db.upsert_profile_by_vendor("acme", "u1")
    sm = main.app.state.session_manager
    # Force-create a key lock
    await sm._get_key_lock(("acme", "u1"))
    assert ("acme", "u1") in sm._key_locks

    r = await async_client.delete(f"/profiles/{profile['id']}", headers=auth_headers)
    assert r.status_code == 204
    assert ("acme", "u1") not in sm._key_locks


@pytest.mark.asyncio
async def test_get_profiles_401_when_no_api_key(async_client, monkeypatch):
    monkeypatch.setenv("MAIN_APP_API_KEY", "test-key-12345")
    monkeypatch.delenv("DEV_MODE", raising=False)
    r = await async_client.get("/profiles")
    assert r.status_code == 401
