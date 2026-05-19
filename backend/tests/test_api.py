"""Tests for FastAPI routes via TestClient."""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.testclient import TestClient

from backend import main
from backend.browser_manager import RunningProfile
from backend.tests.factories import create_test_profile


# ── Legacy admin CRUD removed (OPS-02) ───────────────────────────────────────


def test_list_profiles_returns_410(app_client: TestClient):
    resp = app_client.get("/api/profiles")
    assert resp.status_code == 410


def test_create_profile_returns_410(app_client: TestClient):
    resp = app_client.post("/api/profiles", json={"name": "Test"})
    assert resp.status_code == 410


def test_get_profile_returns_410(app_client: TestClient):
    p = create_test_profile(name="Get Me")
    resp = app_client.get(f"/api/profiles/{p['id']}")
    assert resp.status_code == 410


def test_update_profile_returns_410(app_client: TestClient):
    p = create_test_profile(name="Original")
    resp = app_client.put(f"/api/profiles/{p['id']}", json={"name": "Renamed"})
    assert resp.status_code == 410


def test_delete_profile(app_client: TestClient):
    p = create_test_profile(name="Delete Me")
    pid = p["id"]
    resp = app_client.delete(f"/api/profiles/{pid}")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_delete_profile_not_found(app_client: TestClient):
    resp = app_client.delete("/api/profiles/nonexistent")
    assert resp.status_code == 404


def test_delete_profile_stops_running(app_client: TestClient):
    """Deleting a running profile should stop it first."""
    p = create_test_profile(name="Running")
    pid = p["id"]

    # Inject mock running profile
    mock_running = MagicMock(spec=RunningProfile)
    mock_running.display = 100
    mock_running.ws_port = 6100
    mock_running.cdp_port = 5100
    main.browser_mgr.running[pid] = mock_running
    main.browser_mgr.stop = AsyncMock()

    resp = app_client.delete(f"/api/profiles/{pid}")
    assert resp.status_code == 200
    main.browser_mgr.stop.assert_called_once_with(pid)


# ── Profile Status ───────────────────────────────────────────────────────────


def test_get_profile_status_stopped(app_client: TestClient):
    p = create_test_profile(name="Status")
    pid = p["id"]
    resp = app_client.get(f"/api/profiles/{pid}/status")
    assert resp.status_code == 200
    assert resp.json()["status"] == "stopped"


def test_get_profile_status_not_found(app_client: TestClient):
    resp = app_client.get("/api/profiles/nonexistent/status")
    assert resp.status_code == 404


# ── Launch / Stop ────────────────────────────────────────────────────────────


def test_launch_returns_410(app_client: TestClient):
    p = create_test_profile(name="X")
    resp = app_client.post(f"/api/profiles/{p['id']}/launch")
    assert resp.status_code == 410


def test_stop_returns_410(app_client: TestClient):
    p = create_test_profile(name="X")
    resp = app_client.post(f"/api/profiles/{p['id']}/stop")
    assert resp.status_code == 410


# ── System Status ────────────────────────────────────────────────────────────


def test_system_status(app_client: TestClient):
    # Clear any leaked running profiles from prior tests
    main.browser_mgr.running.clear()

    # Create a profile so profiles_total > 0
    create_test_profile(name="Status Test")
    resp = app_client.get("/api/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["running_count"] == 0
    assert data["binary_version"] == "0.0.0-test"
    assert data["profiles_total"] >= 1


# ── Launch Args ─────────────────────────────────────────────────────────────


def test_profile_launch_args_default_empty(app_client: TestClient):
    p = create_test_profile(name="NoArgs")
    assert p.get("launch_args") in ([], "[]", None)


def test_profile_launch_args_create_via_db(app_client: TestClient):
    p = create_test_profile(
        name="WithArgs",
        launch_args=["--load-extension=/data/ext", "--disable-features=Foo"],
    )
    assert "--load-extension=/data/ext" in str(p.get("launch_args"))


def test_profile_launch_args_update_returns_410(app_client: TestClient):
    p = create_test_profile(name="UpdateArgs")
    resp = app_client.put(
        f"/api/profiles/{p['id']}", json={"launch_args": ["--new-flag"]}
    )
    assert resp.status_code == 410


# ── Clipboard Sync Setting ──────────────────────────────────────────────────


def test_profile_clipboard_sync_default_false(app_client: TestClient):
    """New profiles default to clipboard_sync=false (SEC-05 / D-18)."""
    p = create_test_profile(name="Clipboard Test")
    assert not p.get("clipboard_sync")


def test_profile_clipboard_sync_update_returns_410(app_client: TestClient):
    p = create_test_profile(name="Clipboard Toggle")
    resp = app_client.put(
        f"/api/profiles/{p['id']}", json={"clipboard_sync": False}
    )
    assert resp.status_code == 410


# ── Clipboard ────────────────────────────────────────────────────────────────


def test_set_clipboard_not_running(app_client: TestClient):
    resp = app_client.post("/api/profiles/nonexistent/clipboard", json={"text": "hello"})
    assert resp.status_code == 404


def test_get_clipboard_not_running(app_client: TestClient):
    """Admin clipboard GET returns 404 when profile is not running."""
    p = create_test_profile(name="ClipStopped", clipboard_sync=True)
    pid = p["id"]
    resp = app_client.get(f"/api/profiles/{pid}/clipboard")
    assert resp.status_code == 404


def test_set_clipboard_success(app_client: TestClient):
    """Mock a running profile and patch xclip subprocess."""
    p = create_test_profile(name="Clip")
    pid = p["id"]

    # Inject mock running profile
    mock_running = MagicMock(spec=RunningProfile)
    mock_running.display = 100
    mock_running.cdp_port = 5100
    main.browser_mgr.running[pid] = mock_running

    # Mock asyncio.create_subprocess_exec to avoid actual xclip
    mock_proc = AsyncMock()
    mock_proc.returncode = None
    mock_proc.stdin = MagicMock()
    mock_proc.stdin.write = MagicMock()
    mock_proc.stdin.drain = AsyncMock()
    mock_proc.stdin.close = MagicMock()

    with patch("backend.main.asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_proc):
        resp = app_client.post(f"/api/profiles/{pid}/clipboard", json={"text": "test clipboard"})
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}

    # Cleanup
    main.browser_mgr.running.pop(pid, None)


def test_get_clipboard_admin_route_success(app_client: TestClient):
    """Admin /api/profiles clipboard read works for running profile with clipboard_sync."""
    p = create_test_profile(name="ClipRead", clipboard_sync=True)
    pid = p["id"]

    mock_page = AsyncMock()
    mock_page.evaluate = AsyncMock(return_value="otp-code")
    mock_context = MagicMock()
    mock_context.pages = [mock_page]
    mock_running = MagicMock(spec=RunningProfile)
    mock_running.display = 100
    mock_running.context = mock_context
    main.browser_mgr.running[pid] = mock_running

    resp = app_client.get(f"/api/profiles/{pid}/clipboard")
    assert resp.status_code == 200
    assert resp.json()["text"] == "otp-code"
    main.browser_mgr.running.pop(pid, None)


def test_get_clipboard_admin_route_disabled_sync(app_client: TestClient):
    p = create_test_profile(name="ClipOff", clipboard_sync=False)
    pid = p["id"]
    mock_running = MagicMock(spec=RunningProfile)
    mock_running.display = 100
    main.browser_mgr.running[pid] = mock_running
    resp = app_client.get(f"/api/profiles/{pid}/clipboard")
    assert resp.status_code == 403
    main.browser_mgr.running.pop(pid, None)


# ── Response shape ───────────────────────────────────────────────────────────


def test_admin_sessions_list_has_state_field(app_client: TestClient):
    create_test_profile(name="Shape")
    resp = app_client.get("/api/admin/sessions")
    assert resp.status_code == 200
    for row in resp.json():
        assert row["state"] in ("running", "idle", "stopped")


def test_status_stopped_has_cdp_url_null(app_client: TestClient):
    p = create_test_profile(name="CdpStatus")
    pid = p["id"]
    resp = app_client.get(f"/api/profiles/{pid}/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["cdp_url"] is None


def test_running_profile_has_cdp_url(app_client: TestClient):
    """Running profile status should expose cdp_url."""
    p = create_test_profile(name="CdpRunning")
    pid = p["id"]

    mock_running = MagicMock(spec=RunningProfile)
    mock_running.display = 100
    mock_running.ws_port = 6100
    mock_running.cdp_port = 5100
    mock_running.profile_id = pid
    main.browser_mgr.running[pid] = mock_running

    resp = app_client.get(f"/api/profiles/{pid}/status")
    data = resp.json()
    assert data["status"] == "running"
    assert data["cdp_url"] == f"/api/profiles/{pid}/cdp"

    main.browser_mgr.running.pop(pid, None)


# ── CDP Proxy ───────────────────────────────────────────────────────────────


def test_cdp_json_version_not_running(app_client: TestClient):
    resp = app_client.get("/api/profiles/nonexistent/cdp/json/version")
    assert resp.status_code == 404


def test_cdp_json_list_not_running(app_client: TestClient):
    resp = app_client.get("/api/profiles/nonexistent/cdp/json/list")
    assert resp.status_code == 404


def _mock_running_profile(pid: str) -> MagicMock:
    """Create a mock RunningProfile and register it in browser_mgr."""
    mock = MagicMock(spec=RunningProfile)
    mock.display = 100
    mock.ws_port = 6100
    mock.cdp_port = 5100
    mock.profile_id = pid
    main.browser_mgr.running[pid] = mock
    return mock


def test_cdp_json_version_rewrites_ws_url(app_client: TestClient):
    """GET /cdp/json/version rewrites webSocketDebuggerUrl through our proxy."""
    p = create_test_profile(name="CdpVer")
    pid = p["id"]
    _mock_running_profile(pid)

    chrome_response = MagicMock()
    chrome_response.json.return_value = {
        "webSocketDebuggerUrl": "ws://127.0.0.1:5100/devtools/browser/abc-123",
        "Browser": "Chrome/145.0.0.0",
    }
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=chrome_response)

    with patch("httpx.AsyncClient", return_value=mock_client):
        resp = app_client.get(f"/api/profiles/{pid}/cdp/json/version")

    assert resp.status_code == 200
    data = resp.json()
    assert data["webSocketDebuggerUrl"] == f"ws://testserver/api/profiles/{pid}/cdp"
    assert data["Browser"] == "Chrome/145.0.0.0"
    main.browser_mgr.running.pop(pid, None)


def test_cdp_json_version_uses_wss_behind_https(app_client: TestClient):
    """X-Forwarded-Proto: https should produce wss:// URLs."""
    p = create_test_profile(name="CdpWss")
    pid = p["id"]
    _mock_running_profile(pid)

    chrome_response = MagicMock()
    chrome_response.json.return_value = {
        "webSocketDebuggerUrl": "ws://127.0.0.1:5100/devtools/browser/abc",
    }
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=chrome_response)

    with patch("httpx.AsyncClient", return_value=mock_client):
        resp = app_client.get(
            f"/api/profiles/{pid}/cdp/json/version",
            headers={"X-Forwarded-Proto": "https"},
        )

    assert resp.status_code == 200
    assert resp.json()["webSocketDebuggerUrl"].startswith("wss://")
    main.browser_mgr.running.pop(pid, None)


def test_cdp_json_list_rewrites_page_urls(app_client: TestClient):
    """GET /cdp/json/list rewrites per-page webSocketDebuggerUrl."""
    p = create_test_profile(name="CdpList")
    pid = p["id"]
    _mock_running_profile(pid)

    chrome_response = MagicMock()
    chrome_response.json.return_value = [
        {
            "id": "page1",
            "webSocketDebuggerUrl": "ws://127.0.0.1:5100/devtools/page/DEADBEEF",
        },
        {
            "id": "page2",
            "title": "No WS URL",
        },
    ]
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=chrome_response)

    with patch("httpx.AsyncClient", return_value=mock_client):
        resp = app_client.get(f"/api/profiles/{pid}/cdp/json/list")

    assert resp.status_code == 200
    data = resp.json()
    assert data[0]["webSocketDebuggerUrl"] == (
        f"ws://testserver/api/profiles/{pid}/cdp/devtools/page/DEADBEEF"
    )
    assert "webSocketDebuggerUrl" not in data[1]
    main.browser_mgr.running.pop(pid, None)


def test_cdp_json_version_chrome_unreachable(app_client: TestClient):
    """502 when Chrome CDP endpoint is down."""
    p = create_test_profile(name="CdpDown")
    pid = p["id"]
    _mock_running_profile(pid)

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(side_effect=ConnectionError("refused"))

    with patch("httpx.AsyncClient", return_value=mock_client):
        resp = app_client.get(f"/api/profiles/{pid}/cdp/json/version")

    assert resp.status_code == 502
    main.browser_mgr.running.pop(pid, None)


# ── WebSocket Origin Validation ──────────────────────────────────────────────


def test_vnc_ws_rejects_cross_origin(app_client: TestClient):
    """VNC WebSocket should reject cross-origin browser connections."""
    p = create_test_profile(name="OriginVnc")
    pid = p["id"]
    _mock_running_profile(pid)

    with pytest.raises(Exception):
        with app_client.websocket_connect(
            f"/api/profiles/{pid}/vnc",
            headers={"origin": "http://evil.com"},
        ):
            pass
    main.browser_mgr.running.pop(pid, None)


def test_cdp_ws_rejects_cross_origin(app_client: TestClient):
    """CDP WebSocket should reject cross-origin browser connections."""
    p = create_test_profile(name="OriginCdp")
    pid = p["id"]
    _mock_running_profile(pid)

    with pytest.raises(Exception):
        with app_client.websocket_connect(
            f"/api/profiles/{pid}/cdp",
            headers={"origin": "http://evil.com"},
        ):
            pass
    main.browser_mgr.running.pop(pid, None)


def test_ws_allows_same_origin(app_client: TestClient):
    """WebSocket from same origin should pass Origin check (not get 4403)."""
    p = create_test_profile(name="OriginOk")
    pid = p["id"]
    _mock_running_profile(pid)

    # Same-origin passes Origin check. VNC proxy then fails to connect to
    # real KasmVNC (not running), but that's fine — we're testing Origin only.
    # The connection is accepted (no 4403), then closes due to VNC connect error.
    try:
        with app_client.websocket_connect(
            f"/api/profiles/{pid}/vnc",
            headers={"origin": "http://testserver"},
        ) as ws:
            pass  # connection accepted = Origin check passed
    except Exception as exc:
        # Any error other than 4403 means Origin check passed
        assert "4403" not in str(exc)
    main.browser_mgr.running.pop(pid, None)


def test_ws_allows_no_origin(app_client: TestClient):
    """WebSocket without Origin header (Playwright/Puppeteer) should be accepted."""
    p = create_test_profile(name="NoOrigin")
    pid = p["id"]
    _mock_running_profile(pid)

    try:
        with app_client.websocket_connect(f"/api/profiles/{pid}/vnc") as ws:
            pass
    except Exception as exc:
        assert "4403" not in str(exc)
    main.browser_mgr.running.pop(pid, None)


def test_admin_vnc_ws_tracks_viewer_attach_count(app_client: TestClient, monkeypatch):
    """Admin VNC proxy must participate in warm-pool attach accounting (Phase 5)."""
    p = create_test_profile(name="VncAttach")
    pid = p["id"]
    rp = _mock_running_profile(pid)
    rp.cdp_attach_count = 0
    rp.viewer_attach_count = 0
    sm = main.app.state.session_manager
    on_attach = MagicMock()
    on_detach = MagicMock()
    monkeypatch.setattr(sm, "on_attach", on_attach)
    monkeypatch.setattr(sm, "on_all_detached", on_detach)

    async def fake_vnc(websocket, running, profile_id):
        await websocket.accept(subprotocol=None)
        await websocket.close()

    monkeypatch.setattr(main, "_run_vnc_proxy", fake_vnc)

    assert rp.viewer_attach_count == 0

    with app_client.websocket_connect(
        f"/api/profiles/{pid}/vnc",
        headers={"origin": "http://testserver"},
    ):
        pass

    assert rp.viewer_attach_count == 0
    on_attach.assert_called_once_with(pid)
    on_detach.assert_called_once_with(pid)
    main.browser_mgr.running.pop(pid, None)
