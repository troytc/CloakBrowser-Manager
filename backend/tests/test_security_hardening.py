"""Phase 3 security hardening tests (SEC-02, SEC-03, SEC-07)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from backend import main
from backend.browser_manager import RunningProfile
from backend.viewer_tokens import mint_viewer_token


def test_admin_api_csp_frame_ancestors_none(app_client: TestClient) -> None:
    resp = app_client.get("/api/status")
    assert resp.status_code == 200
    csp = resp.headers.get("content-security-policy", "")
    assert "frame-ancestors 'none'" in csp


def test_machine_sessions_no_admin_csp(
    app_client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = app_client.get("/sessions", headers=auth_headers)
    assert resp.status_code == 200
    csp = resp.headers.get("content-security-policy", "")
    assert "frame-ancestors 'none'" not in csp


def test_clipboard_api_key_only_forbidden(
    app_client: TestClient, auth_headers: dict[str, str]
) -> None:
    from backend.tests.factories import create_test_profile

    p = create_test_profile(name="SecClip")
    pid = p["id"]
    resp = app_client.get(f"/profiles/{pid}/clipboard", headers=auth_headers)
    assert resp.status_code == 403


def test_clipboard_viewer_token_allowed(
    app_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("VIEWER_SECRET", "test-viewer-secret-phase3")
    main.VIEWER_SECRET = "test-viewer-secret-phase3"

    from backend.tests.factories import create_test_profile

    p = create_test_profile(name="ViewerClip")
    pid = p["id"]

    token = mint_viewer_token(pid)
    import asyncio

    from backend import viewer_tokens as vt

    asyncio.get_event_loop().run_until_complete(
        vt.validate_viewer_token(token, pid, consume_jti=True)
    )

    mock_page = AsyncMock()
    mock_page.evaluate = AsyncMock(return_value="secret otp")
    mock_context = MagicMock()
    mock_context.pages = [mock_page]
    mock_running = MagicMock(spec=RunningProfile)
    mock_running.display = 100
    mock_running.context = mock_context
    main.browser_mgr.running[pid] = mock_running

    resp = app_client.get(
        f"/profiles/{pid}/clipboard",
        headers={"X-Viewer-Token": token},
    )
    assert resp.status_code == 200
    assert resp.json()["text"] == "secret otp"
    main.browser_mgr.running.pop(pid, None)


def test_auth_login_cookie_samesite_strict_httponly(
    app_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SEC-03: admin auth cookie flags."""
    monkeypatch.setenv("AUTH_TOKEN", "admin-test-token")
    main.AUTH_TOKEN = "admin-test-token"
    resp = app_client.post("/api/auth/login", json={"token": "admin-test-token"})
    assert resp.status_code == 200
    cookie = resp.headers.get("set-cookie", "").lower()
    assert "httponly" in cookie
    assert "samesite=strict" in cookie
