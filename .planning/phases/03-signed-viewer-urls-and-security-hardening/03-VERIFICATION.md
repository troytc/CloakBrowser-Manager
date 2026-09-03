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

## Human Verification — COMPLETE (2026-09-03)

✓ **VIEW-09 iframe smoke** — confirmed by operator 2026-09-03. The signed viewer URL was
embedded in an iframe on the real Main App origin and rendered; CSP `frame-ancestors`
permitted the embed. Previously deferred at v1.0 close; automated coverage already exercised
mint, fragment URL, and the viewer page route (`routers/viewer.py`, external `embed.js` at
`:77-80` keeps `script-src 'self'` intact).
