"""Unit tests for backend/auth_api_key.py (SEC-01)."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from backend.auth_api_key import require_api_key


@pytest.mark.asyncio
async def test_require_api_key_accepts_correct_key(monkeypatch):
    monkeypatch.setenv("MAIN_APP_API_KEY", "secret123")
    monkeypatch.delenv("DEV_MODE", raising=False)
    result = await require_api_key(api_key="secret123")
    assert result == "secret123"


@pytest.mark.asyncio
async def test_require_api_key_rejects_wrong_key(monkeypatch):
    monkeypatch.setenv("MAIN_APP_API_KEY", "secret123")
    monkeypatch.delenv("DEV_MODE", raising=False)
    with pytest.raises(HTTPException) as exc_info:
        await require_api_key(api_key="wrong")
    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Invalid or missing API key"
    assert exc_info.value.headers == {"WWW-Authenticate": "ApiKey"}


@pytest.mark.asyncio
async def test_require_api_key_rejects_missing_key(monkeypatch):
    monkeypatch.setenv("MAIN_APP_API_KEY", "secret123")
    monkeypatch.delenv("DEV_MODE", raising=False)
    with pytest.raises(HTTPException) as exc_info:
        await require_api_key(api_key=None)
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_require_api_key_rejects_empty_key(monkeypatch):
    monkeypatch.setenv("MAIN_APP_API_KEY", "secret123")
    monkeypatch.delenv("DEV_MODE", raising=False)
    with pytest.raises(HTTPException) as exc_info:
        await require_api_key(api_key="")
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_require_api_key_dev_mode_bypass(monkeypatch):
    monkeypatch.delenv("MAIN_APP_API_KEY", raising=False)
    monkeypatch.setenv("DEV_MODE", "1")
    result = await require_api_key(api_key=None)
    assert result == "dev-mode"


@pytest.mark.asyncio
async def test_require_api_key_production_unset_still_401s(monkeypatch):
    monkeypatch.delenv("MAIN_APP_API_KEY", raising=False)
    monkeypatch.delenv("DEV_MODE", raising=False)
    with pytest.raises(HTTPException) as exc_info:
        await require_api_key(api_key="anything")
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_require_api_key_reads_env_at_request_time(monkeypatch):
    monkeypatch.setenv("MAIN_APP_API_KEY", "A")
    monkeypatch.delenv("DEV_MODE", raising=False)
    assert await require_api_key(api_key="A") == "A"
    monkeypatch.setenv("MAIN_APP_API_KEY", "B")
    assert await require_api_key(api_key="B") == "B"
    with pytest.raises(HTTPException):
        await require_api_key(api_key="A")
