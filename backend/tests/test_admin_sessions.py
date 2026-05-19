"""Tests for GET /api/admin/sessions (ADM-02)."""

from __future__ import annotations

import datetime
import json

import pytest
from fastapi.testclient import TestClient

from backend import database as db
from backend.browser_manager import RunningProfile
from backend.database import create_template
def _seed_profile(vendor_type: str = "acme", conn: str = "user-1") -> dict:
    tpl = create_template(
        vendor_type=vendor_type,
        label="t",
        notes=None,
        blueprint_json=json.dumps({
            "timezone": "UTC", "locale": "en-US", "platform": "windows",
            "screen_width": 1920, "screen_height": 1080, "humanize": False,
            "human_preset": "default", "launch_args": [], "clipboard_sync": False,
        }),
    )
    return db.upsert_profile_by_vendor(vendor_type, conn)


def test_admin_sessions_requires_auth(client_auth: TestClient):
    resp = client_auth.get("/api/admin/sessions")
    assert resp.status_code == 401


def test_admin_sessions_empty(client_auth: TestClient):
    client_auth.cookies.set("auth_token", "test-secret")
    resp = client_auth.get("/api/admin/sessions")
    assert resp.status_code == 200
    assert resp.json() == []


def test_admin_sessions_stopped_profile(client_auth: TestClient):
    client_auth.cookies.set("auth_token", "test-secret")
    row = _seed_profile()
    resp = client_auth.get("/api/admin/sessions")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    item = data[0]
    assert item["profile_id"] == row["id"]
    assert item["vendor_type"] == "acme"
    assert item["vendor_connection_id"] == "user-1"
    assert item["state"] == "stopped"
    assert item["cdp_attach_count"] == 0
    assert item["viewer_attach_count"] == 0


def test_admin_sessions_running_profile(client_auth: TestClient):
    client_auth.cookies.set("auth_token", "test-secret")
    row = _seed_profile()
    pid = row["id"]
    sm = client_auth.app.state.session_manager
    sm._browser.running[pid] = RunningProfile(
        profile_id=pid,
        context=object(),
        cdp_port=9222,
        ws_port=5900,
        display=99,
    )
    sm._browser.running[pid].last_launched_at = datetime.datetime.now(
        datetime.timezone.utc
    )

    resp = client_auth.get("/api/admin/sessions")
    assert resp.status_code == 200
    item = next(x for x in resp.json() if x["profile_id"] == pid)
    assert item["state"] in ("running", "idle")
    assert item["uptime_seconds"] is not None
