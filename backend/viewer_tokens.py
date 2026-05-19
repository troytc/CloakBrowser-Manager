"""Signed viewer JWT minting and validation (Phase 3: VIEW-02, VIEW-03).

Tokens use HS256 with VIEWER_SECRET. Claims: profile_id, exp, iat, jti.
Viewer URLs use URL fragment (#token=) so tokens never hit querystring logs.
"""

from __future__ import annotations

import asyncio
import logging
import os
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

logger = logging.getLogger("vendorbrowser.viewer_tokens")

VIEWER_SECRET: str | None = os.environ.get("VIEWER_SECRET")
DEFAULT_TTL_SECS = int(os.environ.get("VIEWER_TOKEN_TTL_SECS", "300"))


class ViewerTokenError(Exception):
    """Base for viewer token validation failures."""


class ViewerTokenExpired(ViewerTokenError):
    pass


class ViewerTokenInvalid(ViewerTokenError):
    pass


class ViewerTokenReplay(ViewerTokenError):
    pass


class ViewerTokenProfileMismatch(ViewerTokenError):
    pass


class JtiRegistry:
    """In-process one-time JTI store (VIEW-03). Thread-safe via asyncio.Lock."""

    def __init__(self) -> None:
        self._used: dict[str, float] = {}  # jti -> exp unix
        self._lock = asyncio.Lock()

    async def consume(self, jti: str, exp: int) -> None:
        """Mark jti as used. Raises ViewerTokenReplay if already consumed."""
        async with self._lock:
            self._purge_locked(time.time())
            if jti in self._used:
                raise ViewerTokenReplay(f"JTI already consumed: {jti!r}")
            self._used[jti] = float(exp)

    async def is_consumed(self, jti: str) -> bool:
        async with self._lock:
            self._purge_locked(time.time())
            return jti in self._used

    def _purge_locked(self, now: float) -> None:
        expired = [j for j, exp in self._used.items() if exp <= now]
        for j in expired:
            del self._used[j]


# Module singleton — lifespan could reset on restart (VIEW-03: in-process only).
jti_registry = JtiRegistry()


def _secret() -> str:
    if DEV_MODE and not (VIEWER_SECRET and VIEWER_SECRET.strip()):
        return "dev-viewer-secret-not-for-production"
    if not VIEWER_SECRET or not VIEWER_SECRET.strip():
        raise RuntimeError("VIEWER_SECRET is not configured")
    return VIEWER_SECRET


# Import DEV_MODE from main would be circular; mirror check.
DEV_MODE: bool = os.environ.get("DEV_MODE", "").strip().lower() in ("1", "true", "yes")


def mint_viewer_token(profile_id: str, ttl_seconds: int | None = None) -> str:
    """Mint HS256 JWT for viewer access to profile_id."""
    ttl = DEFAULT_TTL_SECS if ttl_seconds is None else ttl_seconds
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "profile_id": profile_id,
        "jti": secrets.token_urlsafe(16),
        "iat": now,
        "exp": now + timedelta(seconds=max(1, ttl)),
    }
    return jwt.encode(payload, _secret(), algorithm="HS256")


def mint_viewer_url(profile_id: str, ttl_seconds: int | None = None) -> str:
    """Relative viewer iframe URL with token in fragment (VIEW-04)."""
    token = mint_viewer_token(profile_id, ttl_seconds=ttl_seconds)
    return f"/viewer/{profile_id}#token={token}"


async def validate_viewer_token(
    token: str,
    expected_profile_id: str,
    *,
    consume_jti: bool = True,
) -> dict[str, Any]:
    """Decode JWT, verify profile_id, optionally consume JTI (VIEW-03).

    When consume_jti=False, the JTI must already be consumed (e.g. clipboard
    after WebSocket activation).

    Raises ViewerTokenError subclasses on failure.
    """
    try:
        payload = jwt.decode(
            token,
            _secret(),
            algorithms=["HS256"],
            options={"require": ["exp", "iat", "jti", "profile_id"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise ViewerTokenExpired("Token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise ViewerTokenInvalid(str(exc)) from exc

    profile_id = payload.get("profile_id")
    if profile_id != expected_profile_id:
        raise ViewerTokenProfileMismatch(
            f"Token profile_id={profile_id!r} != path {expected_profile_id!r}"
        )

    jti = payload["jti"]
    exp = int(payload["exp"])
    if consume_jti:
        await jti_registry.consume(jti, exp)
    elif not await jti_registry.is_consumed(jti):
        raise ViewerTokenInvalid("Viewer token not active — connect WebSocket first")
    return payload
