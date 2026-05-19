# VendorBrowser

## What This Is

VendorBrowser (powered by CloakBrowser) is a single-host headless-profile service that sits behind one downstream application (the "Main App"). It manages one durable Chromium profile per `(vendor_type, vendor_connection_id)` — driven by vendor templates that lock in fingerprint, locale, timezone, platform, and launch flags per vendor — and exposes a single API call that returns a CDP URL for automation plus a signed iframe viewer URL for end-user intervention (e.g., 2FA).

The Main App uses it as infrastructure to programmatically log into vendor portals on behalf of its users, keeping each vendor account cleanly isolated in its own persistent browser profile.

## Core Value

**One idempotent API call gives the Main App a live CDP URL + a scoped iframe viewer URL for a vendor-specific browser profile, with session state (cookies, localStorage, cache) preserved across automation runs via a warm pool.**

If everything else fails, that one call — `POST /sessions` with `(vendor_type, vendor_connection_id)` — must work.

## Current State (v1.0 shipped 2026-05-19)

- Machine API: `POST/GET/DELETE /sessions`, `GET/PATCH/DELETE /profiles` with `X-API-Key` auth
- Signed viewer: `/viewer/{profile_id}#token=…` with JWT + JTI single-use, CSP, external embed script
- Admin: templates CRUD, `GET /api/admin/sessions`, admin VNC + clipboard for ops (warm-pool aware)
- Legacy admin profile CRUD and launch/stop return **410**; dashboard is sessions + templates only
- Tests: 281 backend (pytest), 10 frontend (vitest); slow Chromium e2e behind `pytest -m slow`

## Next Milestone Goals

Define via `/gsd-new-milestone`. Likely candidates from v2 backlog: keepalive heartbeat (SAFE-01), read-only viewer mode (SAFE-02), per-template idle timeout (SAFE-03), template soft-disable (GOV-01).

## Requirements

### Validated

**Pre-v1 baseline (brownfield):**

- ✓ Launch and stop Chromium profiles via CloakBrowser + Playwright
- ✓ Per-profile fingerprint, proxy, locale, timezone, platform, screen, GPU, humanize, launch_args, clipboard_sync
- ✓ Persistent profile storage in SQLite
- ✓ VNC streaming (KasmVNC + noVNC + RFB filter)
- ✓ CSWSH-protected WebSocket VNC proxy
- ✓ Clipboard read/write bridge
- ✓ React admin dashboard shell + bearer/cookie admin auth
- ✓ Docker single-host deployment (x86_64 + ARM64)

**v1.0 milestone:**

- ✓ Vendor templates CRUD keyed by `vendor_type` with snapshot profiles — v1.0
- ✓ `POST /sessions` idempotent upsert + warm-pool wake — v1.0
- ✓ Dual attach-count idle detection + `SessionManager` — v1.0
- ✓ Machine `/profiles` API + API-key auth segregation — v1.0
- ✓ Signed `vnc_viewer_url` (fragment token, HS256, JTI) — v1.0
- ✓ CSP hardening (viewer `frame-ancestors`, admin `none`) — v1.0
- ✓ Admin ops dashboard (sessions list, templates, admin VNC) — v1.0
- ✓ Legacy `/api/profiles` CRUD/launch removed (410) — v1.0
- ✓ `clipboard_sync` defaults false; viewer-token-only machine clipboard — v1.0
- ✓ Production fail-closed without `MAIN_APP_API_KEY` / `VIEWER_SECRET` — v1.0

### Active

_(Empty — run `/gsd-new-milestone` to add v1.1+ requirements.)_

### Out of Scope

- **Upstream proxies / residential IPs** — deferred; proxy fields exist but no provider wiring
- **Multi-tenancy** — single Main App consumer
- **Distributed deployment** — single-box, in-process warm pool
- **Automation / vendor scrapers** — Main App responsibility
- **End-user identity in this service** — opaque `vendor_connection_id` only
- **OAuth for machine auth** — shared API key sufficient
- **Public internet exposure** — private network deployment assumed
- **Webhooks to Main App** — poll-based status
- **Profile cloning / export** — not planned
- **View-only viewer (v1)** — deferred to v2 (SAFE-02)

## Context

**Shipped v1.0** on 2026-05-19 after brownfield refocus from v0.0.7 browser-farm dashboard. Planning archives: [milestones/v1.0-ROADMAP.md](milestones/v1.0-ROADMAP.md), [milestones/v1.0-REQUIREMENTS.md](milestones/v1.0-REQUIREMENTS.md).

**Codebase intelligence:** `.planning/codebase/` snapshot + phase verification docs under `.planning/phases/`.

**Integration:** Main App is a separate codebase; consumes HTTP + WebSocket APIs documented in README.

**Accepted tech debt at v1.0 close:** VIEW-09 human iframe smoke; SESS-12 slow e2e deselected in CI; optional admin VNC manual QA. See [milestones/v1.0-MILESTONE-AUDIT.md](milestones/v1.0-MILESTONE-AUDIT.md).

## Constraints

- **Tech stack**: Python 3.12 / FastAPI / React 19 / TypeScript / SQLite / Docker
- **Browser engine**: CloakBrowser + Playwright
- **VNC stack**: KasmVNC + noVNC + custom RFB filter
- **Deployment**: Single host, <20 concurrent profiles
- **Consumers**: Exactly one trusted downstream app
- **Auth**: API key (machine) + admin bearer/cookie (dashboard), strictly segregated by path prefix
- **Persistence**: On-disk Chromium profile directories on mounted volume

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Templates are full blueprints keyed by `vendor_type` | Consistent vendor fingerprints | ✓ Good — shipped v1.0 |
| Profile identity = `(vendor_type, vendor_connection_id)` | Idempotent upsert for Main App | ✓ Good — UNIQUE + per-key lock |
| Warm-pool idle when both attach counts zero | Preserve login state; 2FA keeps alive | ✓ Good — SessionManager + WS proxies |
| `POST /sessions` canonical API | Hide warm-pool complexity | ✓ Good |
| Service mints viewer URLs | No shared signing keys with Main App | ✓ Good — PyJWT HS256 |
| API-key auth for machine routes | Single trusted consumer | ✓ Good |
| Replace legacy `/api/profiles/*` admin CRUD | One API surface | ✓ Good — 410 stubs |
| Admin dashboard → templates + ops | Humans configure vendors; Main App uses machine API | ✓ Good |
| Token in URL fragment only | Avoid proxy log leakage | ✓ Good |
| `clipboard_sync` default false | Security for vendor logins | ✓ Good |

<details>
<summary>Pre-v1.0 planning context (archived)</summary>

Brownfield refocus started 2026-04-22 from codebase map. v1 scope was 48 requirements across 5 phases (templates, sessions, viewer, admin pivot, admin VNC integration).

</details>

---
*Last updated: 2026-05-19 after v1.0 milestone*
