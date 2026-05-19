"""End-to-end warm-pool tests (D-19 layer 3, SESS-12, SC2, SC5).

Marked slow: requires real CloakBrowser binary + real KasmVNC. Default CI
runs (pytest) skip via addopts="-m 'not slow'". Run explicitly with
`pytest -m slow` for nightly / pre-release verification.
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.slow


def _cloakbrowser_real() -> bool:
    mod = sys.modules.get("cloakbrowser")
    if mod is None:
        return False
    fn = getattr(mod, "launch_persistent_context_async", None)
    if fn is None:
        return False
    from unittest.mock import AsyncMock

    return not isinstance(fn, AsyncMock)


_HAS_CLOAKBROWSER = _cloakbrowser_real()
skip_no_real_chromium = pytest.mark.skipif(
    not _HAS_CLOAKBROWSER,
    reason="real CloakBrowser binary not available; mock is in place",
)


@skip_no_real_chromium
@pytest.mark.asyncio
async def test_idle_sleep_then_wake_persists_cookies(monkeypatch, tmp_path):
    """SESS-12 / SC2: profile idle -> stopped -> wake -> state preserved."""
    monkeypatch.setenv("IDLE_TIMEOUT_SECONDS", "2")
    monkeypatch.setenv("MAIN_APP_API_KEY", "test-key-e2e")
    monkeypatch.setenv("VIEWER_SECRET", "test-viewer-e2e")

    from backend import database as db

    monkeypatch.setattr(db, "DB_PATH", tmp_path / "profiles.db")
    monkeypatch.setattr(db, "DATA_DIR", tmp_path)
    db.init_db()

    import json as _json

    blueprint = {
        "timezone": "UTC",
        "locale": "en-US",
        "platform": "windows",
        "screen_width": 1280,
        "screen_height": 720,
        "humanize": False,
        "human_preset": "default",
        "launch_args": [],
        "clipboard_sync": False,
    }
    db.create_template(
        vendor_type="acme",
        label="acme",
        notes=None,
        blueprint_json=_json.dumps(blueprint),
    )

    for m in list(sys.modules):
        if m.startswith("backend.main"):
            sys.modules.pop(m, None)
    from backend import main
    from httpx import ASGITransport, AsyncClient

    auth = {"X-API-Key": "test-key-e2e"}
    transport = ASGITransport(app=main.app)

    async with main.app.router.lifespan_context(main.app):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.post(
                "/sessions",
                json={"vendor_type": "acme", "vendor_connection_id": "u1"},
                headers=auth,
            )
            assert r.status_code == 200, r.text
            profile_id_1 = r.json()["profile_id"]
            assert r.json()["state"] == "running"

            profile = db.get_profile(profile_id_1)
            udd = Path(profile["user_data_dir"])
            (udd / "e2e_marker.txt").write_text("present")

            sm = main.app.state.session_manager
            sm.on_all_detached(profile_id_1)
            await asyncio.sleep(3.0)

            r = await client.get(f"/sessions/{profile_id_1}", headers=auth)
            assert r.status_code == 200
            assert r.json()["state"] == "stopped"

            r = await client.post(
                "/sessions",
                json={"vendor_type": "acme", "vendor_connection_id": "u1"},
                headers=auth,
            )
            assert r.status_code == 200, r.text
            assert r.json()["profile_id"] == profile_id_1
            assert r.json()["state"] == "running"

            assert (udd / "e2e_marker.txt").exists()
            assert (udd / "e2e_marker.txt").read_text() == "present"


@skip_no_real_chromium
@pytest.mark.asyncio
async def test_restart_safety_first_post_after_lifespan_wakes_within_timeout(
    monkeypatch, tmp_path
):
    """SC5: post-restart, browser_mgr.running == {}, first POST wakes in time."""
    monkeypatch.setenv("MAIN_APP_API_KEY", "test-key-e2e")
    monkeypatch.setenv("VIEWER_SECRET", "test-viewer-e2e")

    from backend import database as db

    monkeypatch.setattr(db, "DB_PATH", tmp_path / "profiles.db")
    monkeypatch.setattr(db, "DATA_DIR", tmp_path)
    db.init_db()

    import json as _json

    db.create_template(
        vendor_type="acme",
        label="acme",
        notes=None,
        blueprint_json=_json.dumps(
            {
                "timezone": "UTC",
                "locale": "en-US",
                "platform": "windows",
                "screen_width": 1280,
                "screen_height": 720,
                "humanize": False,
                "human_preset": "default",
                "launch_args": [],
                "clipboard_sync": False,
            }
        ),
    )

    for m in list(sys.modules):
        if m.startswith("backend.main"):
            sys.modules.pop(m, None)
    from backend import main
    from backend.browser_manager import BrowserManager
    from httpx import ASGITransport, AsyncClient

    auth = {"X-API-Key": "test-key-e2e"}
    transport = ASGITransport(app=main.app)

    async with main.app.router.lifespan_context(main.app):
        assert main.browser_mgr.running == {}

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            t0 = time.monotonic()
            r = await client.post(
                "/sessions",
                json={"vendor_type": "acme", "vendor_connection_id": "u1"},
                headers=auth,
            )
            elapsed = time.monotonic() - t0

            assert r.status_code == 200, r.text
            assert r.json()["state"] == "running"
            assert elapsed < BrowserManager.LAUNCH_TIMEOUT_SECS, (
                f"first POST after restart took {elapsed:.1f}s, "
                f"exceeds LAUNCH_TIMEOUT_SECS={BrowserManager.LAUNCH_TIMEOUT_SECS}"
            )
