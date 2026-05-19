"""Integration tests for /viewer/* routes (Phase 3)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.viewer_tokens import mint_viewer_token


def test_viewer_page_returns_html(app_client: TestClient, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("VIEWER_SECRET", "test-viewer-secret-phase3")
    pid = "test-profile-id"
    resp = app_client.get(f"/viewer/{pid}")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    csp = resp.headers.get("content-security-policy", "").lower()
    assert "frame-ancestors" in csp
    assert "script-src 'self' https://cdn.jsdelivr.net" in csp
    assert "/viewer/static/embed.js" in resp.text
    assert "<script type=\"module\">" not in resp.text


def test_viewer_embed_js_served(app_client: TestClient):
    resp = app_client.get("/viewer/static/embed.js")
    assert resp.status_code == 200
    assert "javascript" in resp.headers.get("content-type", "")
    assert "location.pathname.match" in resp.text


def test_viewer_ws_requires_token_query(app_client: TestClient):
    """WebSocket route requires token query param (422 without it)."""
    resp = app_client.get("/viewer/some-id/ws")
    assert resp.status_code in (404, 422)
