# Phase 3 Verification

**Status:** passed  
**Date:** 2026-05-19

## Criteria

| # | Criterion | Result |
|---|-----------|--------|
| 1 | `POST /sessions` returns `/viewer/{id}#token=` URL | pass |
| 2 | Viewer JWT HS256 with profile_id, exp, jti, iat | pass |
| 3 | JTI replay rejected on second WS use | pass |
| 4 | CSP frame-ancestors on viewer; `none` on `/api/*` | pass |
| 5 | Clipboard read requires viewer token (not API key alone) | pass |

## Tests

- `backend`: 273 passed (2 slow e2e deselected)
- Covers: `test_viewer_tokens.py`, `test_security_hardening.py`, `test_viewer_routes.py`, updated session router tests

## Note

Human VIEW-09 iframe smoke test deferred (YOLO); automated coverage exercises mint, fragment URL, and viewer page route.
