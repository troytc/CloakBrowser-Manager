# Milestones

## v1.0 Warm-pool / Templates / Signed-Viewer (Shipped: 2026-05-19)

**Phases completed:** 5 phases, 25 plans

**Stats:** 85 commits since codebase map; 281 backend + 10 frontend tests passing (2026-05-19)

**Key accomplishments:**

- Vendor template CRUD with snapshot profiles, `clipboard_sync=false` defaults, Docker UID fix, and fail-closed production env checks (`MAIN_APP_API_KEY`, `VIEWER_SECRET`).
- `POST /sessions` idempotent warm-pool: per-key locks, dual attach-count idle detection, machine `/profiles` API, and API-key auth on `/sessions` / `/profiles` / CDP WebSocket.
- Signed viewer URLs: HS256 JWT in URL fragment, JTI single-use, CSP `frame-ancestors`, viewer-scoped clipboard, external embed script for CSP compliance.
- Admin dashboard pivot: `SessionList` ops view, templates surface, legacy admin profile CRUD returns 410.
- Admin VNC integrated with warm-pool (`viewer_attach_count`, idle timer, admin clipboard, idle-session viewer).
- Merged upstream fixes: VNC wheel containment, CDP port rotation, profile auto-launch on container start.

**Tech debt (accepted at close):** VIEW-09 human iframe smoke on Main App origin; SESS-12 slow e2e deselected in default CI; ADM-03 admin VNC not manually QA'd. See [milestones/v1.0-MILESTONE-AUDIT.md](milestones/v1.0-MILESTONE-AUDIT.md).

Known deferred items at close: 1 (see STATE.md Deferred Items)

---
