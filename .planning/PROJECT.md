# CloakBrowser-Manager

## What This Is

CloakBrowser-Manager is a single-host headless-profile service that sits behind one downstream application (the "Main App"). It manages one durable Chromium profile per `(vendor_type, vendor_connection_id)` — driven by vendor templates that lock in fingerprint, locale, timezone, platform, and launch flags per vendor — and exposes a single API call that returns a CDP URL for automation plus a signed iframe viewer URL for end-user intervention (e.g., 2FA).

The Main App uses it as infrastructure to programmatically log into vendor portals on behalf of its users, keeping each vendor account cleanly isolated in its own persistent browser profile.

## Core Value

**One idempotent API call gives the Main App a live CDP URL + a scoped iframe viewer URL for a vendor-specific browser profile, with session state (cookies, localStorage, cache) preserved across automation runs via a warm pool.**

If everything else fails, that one call — `POST /sessions` with `(vendor_type, vendor_connection_id)` — must work.

## Requirements

### Validated

<!-- Capabilities already in the existing codebase, confirmed by the codebase map (2026-04-22). These are the foundation v1 builds on; changing them is a breaking change. -->

- ✓ Launch and stop Chromium profiles via CloakBrowser + Playwright — existing
- ✓ Per-profile configuration of fingerprint seed, proxy, timezone, locale, platform, screen dims, GPU, humanize, launch_args, clipboard_sync — existing
- ✓ Persistent profile storage in SQLite — existing
- ✓ VNC streaming over WebSocket with KasmVNC + noVNC, including RFB protocol filtering and PointerEvent expansion — existing
- ✓ CSWSH-protected WebSocket VNC proxy with origin checking — existing
- ✓ Clipboard read/write bridge between browser and host — existing
- ✓ React admin dashboard for profile CRUD and live VNC viewing — existing
- ✓ Bearer-token / auth-cookie admin authentication — existing
- ✓ Docker single-host deployment (x86_64 + ARM64) — existing

### Active

<!-- v1 scope for the refocus. All hypotheses until shipped. -->

- [ ] Vendor Template entity: CRUD model that locks a full blueprint (fingerprint rules, timezone, locale, platform, screen dims, launch_args, humanize, clipboard_sync) keyed by `vendor_type`
- [ ] Admin UI screens in the existing dashboard for creating/editing/deleting vendor templates
- [ ] Profile identity model: `(vendor_type, vendor_connection_id)` — unique per pair, created by inheriting the vendor template
- [ ] `POST /sessions` one-call API: upsert profile by `(vendor_type, vendor_connection_id)`, wake from warm pool, return `{profile_id, cdp_url, vnc_viewer_url}`
- [ ] Warm-pool lifecycle: profile stays alive while either a CDP client or a viewer iframe is attached; sleeps after N minutes of *both* disconnected; wakes transparently on the next `/sessions` call
- [ ] Signed, short-lived, profile-scoped viewer URLs minted by the service for iframe embedding in the Main App
- [ ] API key / shared-secret authentication for the Main App, distinct from the existing admin login
- [ ] Profile query / update / delete API for the Main App (by `profile_id` or `(vendor_type, vendor_connection_id)`)
- [ ] Replace the existing `/api/profiles/*` and `/api/profiles/{id}/launch` endpoints entirely — old surface deprecated/removed
- [ ] Session state persistence across warm-pool sleep/wake cycles (cookies, localStorage, cache — whatever Chromium persists in the profile directory)
- [ ] Admin dashboard pivots from end-user browser-farm UI to ops-and-templates UI (list profiles, debug, manage templates)

### Out of Scope

<!-- v1 exclusions with reasoning. -->

- **Upstream proxies / residential IPs** — deferred. Ship v1 without; revisit if vendors start fingerprinting or geoblocking. Proxy fields already exist per-profile but won't be wired to a provider.
- **Multi-tenancy** — single downstream consumer (one Main App, one API key). No per-tenant isolation, quotas, or OAuth flows.
- **Distributed / horizontally scaled deployment** — single-box, <20 concurrent. In-memory `running` dict stays. No Redis/routing layer.
- **Automation logic / selectors / vendor-specific scrapers** — lives in the Main App. This service only provides the browser; it doesn't know what vendor portals look like or how to log in.
- **End-user identity in this service** — the service knows only `vendor_connection_id` (opaque string from the Main App). It has no notion of who the human is.
- **OAuth / SSO for API consumer** — shared secret is sufficient for one trusted consumer.
- **Public deployment / external exposure** — assumed to run on a network the Main App can reach (private VPC, internal DNS, or behind a reverse proxy the Main App controls). Not a public SaaS.
- **View-only / read-only viewer mode** — v1 ships interactive-only. Can add later if needed.
- **Profile cloning / export / migration tooling** — not in v1 scope.
- **Webhooks / push events to Main App** — Main App polls / checks status on demand. No event bus.

## Context

**Brownfield refocus, not a greenfield build.** The repo already ships a working user-facing browser dashboard (v0.0.7 as of 2026-04-22). This milestone pivots it into an infrastructure service consumed by a separate application.

**Codebase map** completed 2026-04-22 and committed (see `.planning/codebase/`):
- `ARCHITECTURE.md` — FastAPI + React + Playwright + KasmVNC layered architecture
- `STACK.md` — Python 3.12 / FastAPI 0.115+ / React 19 / TypeScript 5.7 / Vite 6 / Tailwind / SQLite / CloakBrowser 0.3.14+
- `STRUCTURE.md`, `CONVENTIONS.md`, `INTEGRATIONS.md`, `TESTING.md`, `CONCERNS.md`

**What stays and what changes:**
- **Stays:** Chromium lifecycle (CloakBrowser + Playwright), VNC pipeline (KasmVNC + noVNC + RFB filtering), SQLite persistence, Docker deployment, admin auth, per-profile fingerprint config surface, React dashboard shell
- **Changes:** Primary API surface (replaces `/api/profiles/*` with `/sessions` + `/templates`), adds Vendor Template entity, adds warm-pool idle tracking, adds signed viewer URLs with scoped tokens, admin dashboard pivots to ops-and-templates use
- **New from zero:** Vendor Templates, API-key auth for Main App, signed-URL minting, warm-pool state machine

**Recent work informing this refocus:**
- `bd15b06` — Added `launch_args` to the profile API (needed per-vendor customization already)
- `013ef48` — Added per-profile `clipboard_sync` (similar per-profile policy pattern)

**Integration posture:** The Main App is a separate codebase not in this repo. This service exposes an HTTP+WebSocket API contract the Main App consumes. The Main App's end users only ever see this service indirectly, via the iframe viewer embedded in the Main App's own UI.

## Constraints

- **Tech stack**: Python 3.12 / FastAPI / React 19 / TypeScript / SQLite / Docker — locked by existing codebase, no migrations in v1
- **Browser engine**: CloakBrowser (+ Playwright) — locked; all fingerprint/humanize features come from here
- **VNC stack**: KasmVNC server + noVNC client + custom RFB filter — locked; iframe viewer reuses this pipeline
- **Deployment**: Single host, <20 concurrent profiles — no horizontal scaling, no shared state outside the box
- **Consumers**: Exactly one trusted downstream app — no multi-tenancy, no per-tenant quotas
- **Network**: Service and Main App reach each other over a private/internal network — not hardened for public internet
- **Auth**: Shared-secret (API key) for Main App + existing admin login for dashboard — no OAuth, no mTLS in v1
- **Persistence**: Profile state lives in on-disk Chromium profile directories — must survive container restart (volume-mounted)

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Templates are full blueprints keyed by `vendor_type` | Consistency across all users of the same vendor; new profiles inherit everything without per-call config | — Pending |
| Profile identity = `(vendor_type, vendor_connection_id)`; service enforces uniqueness via idempotent upsert | Main App already has `vendor_connection_id`; service stays stateless re: who the human is | — Pending |
| Warm-pool lifecycle; idle = no CDP client AND no viewer iframe | Preserves login state cheaply; human 2FA in iframe keeps session alive; no explicit "release" call needed | — Pending |
| One-call `/sessions` API as the canonical happy path | Minimizes Main App complexity; service hides warm-pool mechanics and upsert logic | — Pending |
| Service mints signed viewer URLs (not Main App) | No signing keys shared with Main App; service controls TTL and revocation | — Pending |
| API-key / shared-secret auth for Main App | Single trusted consumer; OAuth would be over-engineered | — Pending |
| No upstream proxies in v1 | Reduce v1 complexity and external dependencies; revisit if vendors block | — Pending |
| Single-box, <20 concurrent | Matches current infra budget; avoids premature multi-node architecture | — Pending |
| Replace existing `/api/profiles/*` API entirely | Clean surface area, single source of truth, no dual-API support burden | — Pending |
| Admin dashboard pivots to template management + ops | Humans add vendors there; API consumers never touch template CRUD; reuses existing React shell | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-04-22 after initialization*
