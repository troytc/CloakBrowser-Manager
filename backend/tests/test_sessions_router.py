"""Integration tests for backend/routers/sessions.py (SESS-01, SESS-02, SESS-07,
SESS-13, SESS-14). Uses httpx.AsyncClient + ASGITransport (Pitfall D: avoid
TestClient for concurrency tests)."""

from __future__ import annotations

import asyncio
import datetime
import json

import pytest

from backend import database as db
from backend.browser_manager import BrowserLaunchError, RunningProfile
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
async def test_post_sessions_happy_path_returns_session_response(async_client, auth_headers):
    _seed_template("acme")
    r = await async_client.post(
        "/sessions",
        json={"vendor_type": "acme", "vendor_connection_id": "user-1"},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "profile_id" in body
    assert body["cdp_url"] == f"/api/profiles/{body['profile_id']}/cdp"
    assert body["vnc_viewer_url"].startswith(f"/viewer/{body['profile_id']}#token=")
    assert body["state"] == "running"


@pytest.mark.asyncio
async def test_post_session_returns_fresh_token_on_repeat(async_client, auth_headers, mock_browser_manager):
    _seed_template("acme")
    r1 = await async_client.post(
        "/sessions",
        json={"vendor_type": "acme", "vendor_connection_id": "u1"},
        headers=auth_headers,
    )
    r2 = await async_client.post(
        "/sessions",
        json={"vendor_type": "acme", "vendor_connection_id": "u1"},
        headers=auth_headers,
    )
    assert r1.status_code == 200 and r2.status_code == 200
    url1 = r1.json()["vnc_viewer_url"]
    url2 = r2.json()["vnc_viewer_url"]
    token1 = url1.split("#token=", 1)[1]
    token2 = url2.split("#token=", 1)[1]
    assert token1 != token2


@pytest.mark.asyncio
async def test_post_sessions_idempotent_returns_same_profile_id(async_client, auth_headers, mock_browser_manager):
    _seed_template("acme")
    r1 = await async_client.post("/sessions", json={"vendor_type": "acme", "vendor_connection_id": "u1"}, headers=auth_headers)
    r2 = await async_client.post("/sessions", json={"vendor_type": "acme", "vendor_connection_id": "u1"}, headers=auth_headers)
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["profile_id"] == r2.json()["profile_id"]
    assert mock_browser_manager.launch.await_count == 1


@pytest.mark.asyncio
async def test_post_sessions_concurrent_race_uses_per_key_lock(async_client, auth_headers, mock_browser_manager):
    """SESS-07 / Pitfall 2 regression guard."""
    _seed_template("acme")

    async def slow_launch(profile):
        await asyncio.sleep(0.05)
        rp = RunningProfile(
            profile_id=profile["id"],
            context=type("C", (), {"add_init_script": staticmethod(lambda *a, **k: None)})(),
            display=99, ws_port=6199, cdp_port=5100,
        )
        mock_browser_manager.running[profile["id"]] = rp
        return rp

    mock_browser_manager.launch.side_effect = slow_launch

    payload = {"vendor_type": "acme", "vendor_connection_id": "user-1"}
    responses = await asyncio.gather(*[
        async_client.post("/sessions", json=payload, headers=auth_headers) for _ in range(10)
    ])

    assert all(r.status_code == 200 for r in responses), [r.status_code for r in responses]

    profile_ids = {r.json()["profile_id"] for r in responses}
    assert len(profile_ids) == 1, f"Expected one profile_id, got: {profile_ids}"

    with db.get_db() as conn:
        rows = conn.execute(
            "SELECT id FROM profiles WHERE vendor_type=? AND vendor_connection_id=?",
            ("acme", "user-1"),
        ).fetchall()
    assert len(rows) == 1
    assert mock_browser_manager.launch.await_count == 1


@pytest.mark.asyncio
async def test_post_sessions_400_on_empty_vendor_type(async_client, auth_headers):
    r = await async_client.post(
        "/sessions",
        json={"vendor_type": "", "vendor_connection_id": "u1"},
        headers=auth_headers,
    )
    assert r.status_code == 422  # Pydantic validation error


@pytest.mark.asyncio
async def test_post_sessions_401_on_missing_api_key(async_client, auth_headers):
    # Deliberately omit X-API-Key
    r = await async_client.post(
        "/sessions",
        json={"vendor_type": "acme", "vendor_connection_id": "u1"},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_post_sessions_404_on_no_template(async_client, auth_headers):
    r = await async_client.post(
        "/sessions",
        json={"vendor_type": "missing", "vendor_connection_id": "u1"},
        headers=auth_headers,
    )
    assert r.status_code == 404
    detail = r.json().get("detail")
    if isinstance(detail, dict):
        assert "missing" in detail.get("vendor_type", "") or "missing" in str(detail)
    else:
        assert "missing" in str(detail)


@pytest.mark.asyncio
async def test_post_sessions_503_on_browser_launch_error(async_client, auth_headers, mock_browser_manager):
    _seed_template("acme")
    mock_browser_manager.launch.side_effect = BrowserLaunchError("probe failed")
    r = await async_client.post(
        "/sessions",
        json={"vendor_type": "acme", "vendor_connection_id": "u1"},
        headers=auth_headers,
    )
    assert r.status_code == 503
    detail = r.json()["detail"]
    if isinstance(detail, dict):
        assert detail.get("detail") == "Browser launch failed"
        assert "probe failed" in detail.get("reason", "")


@pytest.mark.asyncio
async def test_get_sessions_returns_empty_list_when_none_running(async_client, auth_headers):
    r = await async_client.get("/sessions", headers=auth_headers)
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_get_sessions_returns_running_profiles(async_client, auth_headers, mock_browser_manager):
    _seed_template("acme")
    r = await async_client.post("/sessions", json={"vendor_type": "acme", "vendor_connection_id": "u1"}, headers=auth_headers)
    assert r.status_code == 200
    rp = mock_browser_manager.running[r.json()["profile_id"]]
    rp.last_launched_at = datetime.datetime.now(datetime.timezone.utc)

    r2 = await async_client.get("/sessions", headers=auth_headers)
    assert r2.status_code == 200
    items = r2.json()
    assert len(items) == 1
    assert items[0]["vendor_type"] == "acme"


@pytest.mark.asyncio
async def test_get_session_status_returns_envelope(async_client, auth_headers, mock_browser_manager):
    _seed_template("acme")
    r = await async_client.post("/sessions", json={"vendor_type": "acme", "vendor_connection_id": "u1"}, headers=auth_headers)
    profile_id = r.json()["profile_id"]
    r2 = await async_client.get(f"/sessions/{profile_id}", headers=auth_headers)
    assert r2.status_code == 200
    body = r2.json()
    assert body["state"] == "running"
    assert body["cdp_attach_count"] == 0
    assert body["viewer_attach_count"] == 0


@pytest.mark.asyncio
async def test_get_session_status_returns_404_when_profile_unknown_to_db(async_client, auth_headers):
    r = await async_client.get("/sessions/nonexistent-id", headers=auth_headers)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_delete_sessions_204_when_running(async_client, auth_headers, mock_browser_manager):
    _seed_template("acme")
    r = await async_client.post("/sessions", json={"vendor_type": "acme", "vendor_connection_id": "u1"}, headers=auth_headers)
    profile_id = r.json()["profile_id"]
    r2 = await async_client.delete(f"/sessions/{profile_id}", headers=auth_headers)
    assert r2.status_code == 204
    mock_browser_manager.stop.assert_awaited_with(profile_id)


@pytest.mark.asyncio
async def test_delete_sessions_204_when_not_running_idempotent(async_client, auth_headers, mock_browser_manager):
    _seed_template("acme")
    r = await async_client.post("/sessions", json={"vendor_type": "acme", "vendor_connection_id": "u1"}, headers=auth_headers)
    profile_id = r.json()["profile_id"]
    # Remove from running but keep DB row (simulate already-stopped)
    mock_browser_manager.running.pop(profile_id, None)
    r2 = await async_client.delete(f"/sessions/{profile_id}", headers=auth_headers)
    assert r2.status_code == 204


@pytest.mark.asyncio
async def test_delete_sessions_404_when_profile_unknown_to_db(async_client, auth_headers):
    r = await async_client.delete("/sessions/nonexistent-id", headers=auth_headers)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_delete_sessions_does_not_drop_row_or_directory(async_client, auth_headers, mock_browser_manager):
    _seed_template("acme")
    r = await async_client.post("/sessions", json={"vendor_type": "acme", "vendor_connection_id": "u1"}, headers=auth_headers)
    profile_id = r.json()["profile_id"]
    await async_client.delete(f"/sessions/{profile_id}", headers=auth_headers)
    # Row still in DB
    assert db.get_profile(profile_id) is not None
