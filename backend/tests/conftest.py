"""Shared test fixtures for backend tests."""

from __future__ import annotations

import os
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

# ---------------------------------------------------------------------------
# Set DEV_MODE BEFORE `from backend import main` happens anywhere — main.py's
# lifespan calls _check_required_env() which raises RuntimeError when
# MAIN_APP_API_KEY or VIEWER_SECRET is unset and DEV_MODE is not 1
# (SEC-06 / D-17 / T-01-23). DEV_MODE=1 keeps the import + TestClient lifespan
# usable in tests without shipping real secrets.
# ---------------------------------------------------------------------------

os.environ.setdefault("DEV_MODE", "1")

# ---------------------------------------------------------------------------
# Mock cloakbrowser BEFORE any backend module is imported.
# browser_manager.py does `from cloakbrowser import launch_persistent_context_async`
# at module level, and main.py imports BrowserManager which triggers it.
# main.py:381 also does `from cloakbrowser.config import CHROMIUM_VERSION`.
# ---------------------------------------------------------------------------

_mock_cloakbrowser = types.ModuleType("cloakbrowser")
_mock_cloakbrowser.launch_persistent_context_async = AsyncMock()  # type: ignore[attr-defined]

_mock_config = types.ModuleType("cloakbrowser.config")
_mock_config.CHROMIUM_VERSION = "0.0.0-test"  # type: ignore[attr-defined]

sys.modules.setdefault("cloakbrowser", _mock_cloakbrowser)
sys.modules.setdefault("cloakbrowser.config", _mock_config)


from backend import database as db  # noqa: E402


@pytest.fixture()
def tmp_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Point database module at a temp directory and init schema."""
    db_file = tmp_path / "profiles.db"
    monkeypatch.setattr(db, "DB_PATH", db_file)
    monkeypatch.setattr(db, "DATA_DIR", tmp_path)
    db.init_db()
    return tmp_path


@pytest.fixture()
def sample_profile(tmp_db: Path):
    """Create and return a sample profile dict."""
    return db.create_profile(name="Test Profile", fingerprint_seed=12345)


@pytest.fixture()
def app_client(tmp_db: Path, monkeypatch: pytest.MonkeyPatch):
    """FastAPI TestClient with mocked DB and browser manager."""
    from backend import main

    # Patch lifespan-called methods to avoid subprocess calls (pkill, Xvnc)
    monkeypatch.setattr(main.browser_mgr, "cleanup_stale", AsyncMock())
    monkeypatch.setattr(main.browser_mgr, "cleanup_all", AsyncMock())
    monkeypatch.setattr(main.browser_mgr.vnc, "cleanup_stale", AsyncMock())

    from starlette.testclient import TestClient

    with TestClient(main.app) as client:
        yield client


# ---------------------------------------------------------------------------
# Phase 2 fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_browser_manager(monkeypatch):
    """A MagicMock-flavored browser_mgr swap-in for integration tests."""
    import asyncio
    from unittest.mock import AsyncMock, MagicMock
    from backend import main as _main
    from backend.browser_manager import RunningProfile

    bm = MagicMock()
    bm.running = {}
    bm._lock = asyncio.Lock()
    bm._launch_sem = asyncio.Semaphore(3)

    async def _default_launch(profile: dict):
        rp = RunningProfile(
            profile_id=profile["id"],
            context=AsyncMock(),
            display=99,
            ws_port=6199,
            cdp_port=5100,
        )
        bm.running[profile["id"]] = rp
        return rp

    bm.launch = AsyncMock(side_effect=_default_launch)
    bm.stop = AsyncMock()
    bm._stop_locked = AsyncMock()
    bm.cleanup_stale = AsyncMock()
    bm.cleanup_all = AsyncMock()
    bm.vnc = MagicMock()
    bm.vnc.cleanup_stale = AsyncMock()

    monkeypatch.setattr(_main, "browser_mgr", bm)
    return bm


@pytest.fixture()
def auth_headers(monkeypatch):
    """Set MAIN_APP_API_KEY and return a header dict for authenticated requests."""
    monkeypatch.setenv("MAIN_APP_API_KEY", "test-key-12345")
    monkeypatch.setenv("VIEWER_SECRET", "test-viewer-secret")
    monkeypatch.delenv("DEV_MODE", raising=False)
    return {"X-API-Key": "test-key-12345"}


@pytest.fixture()
async def async_client(tmp_db, mock_browser_manager):
    """httpx.AsyncClient with ASGITransport — required for SESS-07 race test."""
    from httpx import ASGITransport, AsyncClient
    from backend import main

    transport = ASGITransport(app=main.app)
    async with main.app.router.lifespan_context(main.app):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
