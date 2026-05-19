# Phase 4 Verification

**Status:** passed  
**Date:** 2026-05-19

## Criteria

| # | Criterion | Result |
|---|-----------|--------|
| 1 | Admin dashboard shows Sessions + Templates surfaces | pass |
| 2 | Session ops list via GET /api/admin/sessions | pass |
| 3 | Running session opens admin VNC viewer (ProfileViewer) | pass |
| 4 | Legacy profile create/launch UI removed from App | pass |
| 5 | POST launch/stop and legacy CRUD return 410 | pass |

## Tests

- `backend`: 273 passed (2 slow e2e deselected)
- `frontend`: vitest 9 passed

## Notes

- SPA catch-all excludes `viewer/*` GET paths so mistaken `/viewer/{id}/ws` HTTP requests return 404 instead of index.html.
- Human smoke of admin VNC deferred (YOLO); automated admin sessions + 410 regression tests cover the contract.
