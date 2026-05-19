"""Local dev ASGI entry when cwd is ``backend/``.

Use from the backend directory::

    uvicorn asgi:app --reload --port 8080

Production and Docker use ``uvicorn backend.main:app`` from the repo root
(see ``entrypoint.sh``).
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from backend.main import app  # noqa: E402

__all__ = ["app"]
