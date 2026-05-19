"""Machine-API authentication via X-API-Key header (SEC-01, CONTEXT.md D-11).

Mounted on routers/sessions.py and routers/profiles.py:

    from .auth_api_key import require_api_key
    router = APIRouter(prefix="/sessions", dependencies=[Depends(require_api_key)])

DO NOT use this on /admin/* — that's the existing AuthMiddleware surface
(CLAUDE.md security rule 3: two auth surfaces, strictly segregated).

The MAIN_APP_API_KEY value is read at REQUEST time, not at module import,
so test fixtures that monkeypatch.setenv work correctly (RESEARCH.md
Pitfall E).
"""

from __future__ import annotations

import hmac
import logging
import os

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

logger = logging.getLogger("vendorbrowser.auth_api_key")

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def _expected_key() -> str | None:
    raw = os.environ.get("MAIN_APP_API_KEY") or ""
    stripped = raw.strip()
    return stripped or None


def _dev_mode() -> bool:
    return os.environ.get("DEV_MODE", "").strip().lower() in ("1", "true", "yes")


async def require_api_key(api_key: str | None = Security(_api_key_header)) -> str:
    """Validate X-API-Key against MAIN_APP_API_KEY (constant-time compare)."""
    expected = _expected_key()

    if expected is None:
        if _dev_mode():
            logger.debug("DEV_MODE bypass for X-API-Key check")
            return "dev-mode"
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    if not hmac.compare_digest(api_key.encode("utf-8"), expected.encode("utf-8")):
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    return api_key
