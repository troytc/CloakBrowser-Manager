"""Tests for viewer JWT minting, JTI registry, and validation (Phase 3)."""

from __future__ import annotations

import asyncio
import os

import jwt
import pytest

from backend import viewer_tokens as vt


@pytest.fixture(autouse=True)
def viewer_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VIEWER_SECRET", "test-viewer-secret-phase3")
    monkeypatch.setenv("DEV_MODE", "0")
    # Reset module-level secret read
    vt.VIEWER_SECRET = "test-viewer-secret-phase3"
    vt.DEV_MODE = False
    vt.jti_registry = vt.JtiRegistry()


@pytest.mark.asyncio
async def test_mint_and_validate_consumes_jti() -> None:
    token = vt.mint_viewer_token("prof-1", ttl_seconds=60)
    payload = await vt.validate_viewer_token(token, "prof-1", consume_jti=True)
    assert payload["profile_id"] == "prof-1"
    assert "jti" in payload

    with pytest.raises(vt.ViewerTokenReplay):
        await vt.validate_viewer_token(token, "prof-1", consume_jti=True)


@pytest.mark.asyncio
async def test_validate_profile_mismatch() -> None:
    token = vt.mint_viewer_token("prof-a")
    with pytest.raises(vt.ViewerTokenProfileMismatch):
        await vt.validate_viewer_token(token, "prof-b", consume_jti=True)


@pytest.mark.asyncio
async def test_clipboard_requires_active_session() -> None:
    token = vt.mint_viewer_token("prof-1")
    with pytest.raises(vt.ViewerTokenInvalid):
        await vt.validate_viewer_token(token, "prof-1", consume_jti=False)

    await vt.validate_viewer_token(token, "prof-1", consume_jti=True)
    await vt.validate_viewer_token(token, "prof-1", consume_jti=False)


def test_mint_viewer_url_uses_fragment() -> None:
    url = vt.mint_viewer_url("abc-123")
    assert url.startswith("/viewer/abc-123#token=")
    assert "?" not in url.split("#")[0]


def test_expired_token_raises() -> None:
    secret = os.environ["VIEWER_SECRET"]
    token = jwt.encode(
        {
            "profile_id": "p1",
            "jti": "dead",
            "iat": 1,
            "exp": 1,
        },
        secret,
        algorithm="HS256",
    )

    async def _run() -> None:
        with pytest.raises(vt.ViewerTokenExpired):
            await vt.validate_viewer_token(token, "p1", consume_jti=True)

    asyncio.run(_run())
