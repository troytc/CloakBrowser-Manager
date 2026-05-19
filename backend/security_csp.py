"""Content-Security-Policy helpers (Phase 3: SEC-02)."""

from __future__ import annotations

import logging
import os

logger = logging.getLogger("vendorbrowser.security_csp")

DEV_MODE: bool = os.environ.get("DEV_MODE", "").strip().lower() in ("1", "true", "yes")


def viewer_frame_ancestors_header() -> str:
    """CSP for viewer embed pages — allow Main App origin in iframe (VIEW-04)."""
    origin = os.environ.get("MAIN_APP_ORIGIN", "").strip()
    if not origin and not DEV_MODE:
        logger.warning(
            "MAIN_APP_ORIGIN unset; viewer frame-ancestors limited to 'self' only"
        )
    frame_ancestors = f"'self' {origin}".strip() if origin else "'self'"
    return (
        "default-src 'self'; "
        "script-src 'self' https://cdn.jsdelivr.net; "
        "connect-src 'self' ws: wss:; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob:; "
        f"frame-ancestors {frame_ancestors};"
    )


def admin_frame_ancestors_none() -> dict[str, str]:
    """CSP for admin /api/* JSON — prevent clickjacking (SEC-02)."""
    return {"Content-Security-Policy": "frame-ancestors 'none'"}
