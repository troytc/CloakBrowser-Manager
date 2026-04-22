# Feature Research

**Domain:** Single-consumer headless browser profile service (browser-profile-as-a-service)
**Researched:** 2026-04-22
**Confidence:** HIGH (verified against Browserbase, Anchor Browser, Steel, Hyperbrowser, Kernel docs + PROJECT.md + existing codebase map)

---

## Context: What This Service Is

This is NOT a public SaaS. It is private infrastructure consumed by exactly one downstream app (the "Main App"). The primary contract is:

> `POST /sessions` with `(vendor_type, vendor_connection_id)` returns `{profile_id, cdp_url, viewer_url}`.

Everything else either enables that contract or supports human ops around it. Multi-tenancy, billing, quotas, and stealth-pro fingerprinting modes are explicitly not the job here.

---

## Feature Landscape

### Table Stakes (Service Fails Its Core Value Without These)

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| `POST /sessions` — idempotent upsert by `(vendor_type, vendor_connection_id)` | This is the entire value proposition; without it the Main App must manage its own profile lifecycle | MEDIUM | Returns `{profile_id, cdp_url, viewer_url}`; upserts profile if not exists, wakes from pool if sleeping, returns running instance if already live |
| CDP URL in session response | Main App uses Playwright/CDP for all automation; no CDP = no automation | LOW | Already produced by existing `launch_persistent_context_async`; route change only |
| Profile-scoped signed viewer URL | Main App embeds VNC in its own UI for human 2FA; unsigned URL leaks VNC access | MEDIUM | HMAC-signed token encoding `{profile_id, exp}`; validated at WS upgrade; minted by this service, never by Main App |
| Viewer URL TTL enforcement | Leaked URL must expire; without expiry a stolen token is permanent access | LOW | Validate `exp` claim at WebSocket connect time; 15–30 min default is table stakes; must survive the 2FA interaction window |
| Viewer URL revocation | If a user session ends abnormally, the iframe should stop working | LOW | Track issued tokens in SQLite (or in-memory set); `DELETE /sessions/{id}` or profile stop marks tokens revoked |
| Warm-pool sleep/wake | Session state (cookies, localStorage) must survive between automation runs; cold-starting a profile loses login state | MEDIUM | Idle = no CDP client AND no active viewer WS; sleep after N-minute timer; transparent wake on next `/sessions` call |
| Idle detection via dual-signal (CDP + viewer) | One signal alone gives false positives — active VNC + idle CDP means a human is still working | MEDIUM | Track `cdp_connected` (Playwright context) and `viewer_connected` (WS count) as separate booleans; idle timer resets when either goes nonzero |
| Session status endpoint `GET /sessions/{id}` | Main App must be able to poll: is this profile alive, sleeping, or crashed? | LOW | Returns `{profile_id, vendor_type, vendor_connection_id, status: running|sleeping|stopped|error, cdp_url?, uptime_s}` |
| Vendor Template CRUD (API + Admin UI) | New vendor = new template; without templates every profile needs manual config; templates enforce consistency | MEDIUM | `vendor_type` is the key; template stores full browser config blueprint; admin creates/edits via dashboard only (Main App never touches templates) |
| Template → Profile inheritance at create time | Profile created from template must snapshot all config values; template changes must NOT retroactively mutate running profiles | LOW | Copy all template fields into profile row at upsert time; profile is self-contained after creation |
| API-key authentication for Main App (separate from admin login) | Admin token is interactive; a shared secret carried in `Authorization: Bearer` header is the appropriate pattern for a single trusted machine client | LOW | `API_KEY` env var; checked on all `/sessions` and `/profiles` routes; admin cookie auth stays for dashboard routes |
| Profile query by `(vendor_type, vendor_connection_id)` | Main App identifies profiles by its own IDs, not our UUIDs; must be able to look up status and metadata | LOW | `GET /profiles?vendor_type=X&vendor_connection_id=Y` or `GET /sessions?vendor_type=X&vendor_connection_id=Y` |
| Profile update (selective field patch) | Main App may need to update proxy or clipboard_sync for a specific profile without recreating it | LOW | `PATCH /profiles/{id}` with partial ProfileUpdate; does not restart running instance until next wake |
| Profile delete | Stale vendor connections must be cleanable; disk and display resources must be reclaimable | LOW | Stop browser, delete VNC, delete profile dir, delete DB row; idempotent (404 on already-deleted) |
| Replace existing `/api/profiles/*` surface | Dual API surfaces create inconsistency and maintenance burden | LOW | Existing endpoints deprecated/removed; not a new feature per se, but a table-stakes contract cleanness requirement |
| Session state persistence across sleep/wake | The whole point of a warm pool is preserved login state; if Chromium profile dir is deleted on sleep, all value is lost | LOW | Profile dir at `/data/profiles/{id}/` stays on disk across sleep; only the browser process and VNC are torn down |

### Differentiators (Worth Building in v1 at Low/Medium Effort Given Existing Infrastructure)

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Interactive viewer (full input pass-through) vs read-only mode on same URL | Commercial analogs (Anchor, Browserbase) treat these as separate URL types or separate session flags; having one URL that the Main App can switch between modes saves two separate token mints | LOW | Anchor uses `pointer-events: none` in the iframe; service can encode `interactive=true/false` in the viewer token claims and relay that as a CSS class or noVNC config; read-only mode defers to v1.x per PROJECT.md but costs almost nothing to design in the token |
| Explicit `POST /sessions/{id}/keepalive` heartbeat | Allows Main App to explicitly signal "the user is still in the iframe" even if the VNC WS briefly drops (reconnecting noVNC); prevents spurious idle-sleep during user interaction | LOW | Update `last_activity_at` in the running dict; cheap to add, prevents annoying UX where 2FA iframe puts the profile to sleep mid-task |
| `GET /sessions` active list (admin + API) | Ops visibility: how many profiles are currently running, which vendor_types, any stuck or crashed? Main App can also use this to warm profiles proactively | LOW | Already effectively available via `BrowserManager.running` dict; just needs an endpoint; commercial analogs (Browserless `/sessions` API) call this table stakes for enterprise/dedicated deployments |
| Admin dashboard: active session list with per-session debug link | Humans need to see what's running without SSH; existing React shell makes this cheap to add | LOW | List running profiles, show vendor_type + vendor_connection_id + uptime + CDP status; link to live VNC view; reuses existing ProfileViewer |
| Admin dashboard: template CRUD screens | New vendors require template creation; admin must be able to do this without hitting the API raw | MEDIUM | Form fields mirror the Profile form but saved as VendorTemplate; existing ProfileForm can be refactored to a shared FormFields component |
| Viewer URL `?navbar=false` suppression | When embedding as an iframe in the Main App's UI, the noVNC toolbar clutters the experience; commercial analogs (Browserbase) support this | LOW | Pass a flag in the signed token claims; noVNC config at WS connect time strips the toolbar |
| Explicit `DELETE /sessions/{id}/viewer-token` | Revoke viewer access immediately without stopping the profile; useful if the human closes the 2FA dialog | LOW | Mark token as revoked in-memory (or SQLite); cheap to implement; prevents stale iframe connections from blocking idle detection |
| `POST /sessions/{id}/stop` (explicit release) | Main App may want to force-sleep a profile early (e.g., user closed their session); without this only the idle timer terminates | LOW | Calls existing `stop()` on BrowserManager; rename from current `/api/profiles/{id}/stop` |
| Vendor template `default_ttl_minutes` field | Per-vendor idle timeout override; some vendors (banking) need aggressive sleep (5 min); others (social) can idle 30 min safely | LOW | Store `idle_timeout_minutes` on the template; profile inherits at creation; warm-pool uses this value instead of global constant |
| Template `is_active` flag (soft-disable) | Mark a template inactive when a vendor is deprecated; profiles using it continue to work but no new profiles can be created | LOW | Boolean on template row; `POST /sessions` returns 422 if template inactive |

### Anti-Features (Deliberately NOT Build)

| Anti-Feature | Why It Seems Useful | Why It's a Problem for This Service | What to Do Instead |
|--------------|---------------------|--------------------------------------|--------------------|
| Multi-tenancy (per-tenant isolation, multiple API keys, RBAC) | "Future-proof" | Single consumer is the explicit design constraint; multi-tenancy adds auth complexity, data isolation overhead, and row-level scoping to every query with zero current benefit | Stay single-consumer; if a second consumer ever appears, revisit then |
| Billing / quota metering | "Monetization-ready" | Zero commercial consumers; no billing system to integrate with; adds a measurement layer to every session lifecycle event | Capacity limit is enforced by `<20 concurrent profiles` — hardware is the quota |
| Per-call fingerprint override (letting Main App pass fingerprint config at `/sessions` time) | "Flexibility for edge cases" | Breaks the template contract — if fingerprint varies per call, vendor consistency is lost; also opens the service to misconfiguration by the Main App | All fingerprint config lives in the template; Main App sends only `(vendor_type, vendor_connection_id)`; per-profile overrides belong in the admin dashboard, not the programmatic API |
| Webhooks / push events to Main App | "Event-driven architecture" | Main App polls; no infrastructure for an outgoing event bus; adds delivery reliability concerns (retries, dead-letter queues) for a single consumer who can just poll | `GET /sessions/{id}` for status; Main App polls on its schedule |
| Session recording / video replay | "Debug playback" | Adds storage burden (video files per session), complex streaming infrastructure, and a capture pipeline on top of VNC that doesn't exist today; commercial services charge extra for this | Live VNC viewer is sufficient for human intervention; CDP gives the Main App programmatic introspection |
| Proxy provider integration (residential IPs, rotating proxies) | "Anti-detection" | Per PROJECT.md: proxy fields exist per-profile but no v1 provider wiring; adds external dependency and cost; most vendor portals don't need it at this scale | Expose proxy fields in profile (already done); let admin set a static proxy manually if needed; defer auto-rotation |
| Stealth-pro / anti-detection fingerprinting modes beyond CloakBrowser | "Better evasion" | CloakBrowser already provides fingerprint spoofing; layering additional anti-detect tooling creates conflicts, maintenance burden, and is unverified to actually help at current scale | Use CloakBrowser's `fingerprint_seed` + `humanize` as shipped; revisit if specific vendors block |
| Profile cloning / export / import | "Disaster recovery" | Chromium profile dirs are not reliably portable across machine reboots, OS versions, or Chrome version changes; partial clone = broken profile | Vendor credentials live in the vendor portal (Main App's responsibility); treat profile corruption as "re-authenticate via iframe" |
| OAuth / OIDC for Main App authentication | "Enterprise-ready auth" | Single trusted consumer; shared secret is correct for a machine client; OAuth adds a token exchange round-trip and key rotation complexity with no security gain | `API_KEY` env var + Bearer header is correct and sufficient |
| End-user identity model inside this service | "Audit trail per user" | Service knows only `vendor_connection_id` (opaque string); assigning human identity creates PII in a service that isn't designed for it | Main App owns the `vendor_connection_id` → human user mapping; this service stays agnostic |
| Horizontal scaling / multi-node routing | "HA / reliability" | Single-box constraint is explicit; adding a routing layer (Redis, consistent hashing) before hitting that limit is premature; `BrowserManager.running` dict is the in-process state store | Scale vertically on the single host; the <20 concurrent ceiling is set by CloakBrowser resource usage, not architecture |
| Template inheritance chains (parent/child templates) | "DRY vendor configs" | Adds resolution complexity for a service with ~5–20 vendor types; a flat template per vendor_type is simpler, easier to debug, and sufficient | One template per vendor_type; copy all fields into profile at creation; no runtime resolution chain |
| REST API versioning (`/v2/`) | "API evolution" | Single consumer; breaking changes are negotiated OOB; version prefixes add routing overhead and dead-code maintenance | Bump the major version by coordinating with the Main App; document breaking changes in PROJECT.md |
| Public-internet exposure hardening (rate limiting, CORS wildcard, DDoS protection) | "Security" | Service is private-network only; rate limiting a single trusted consumer adds overhead with no threat model match | Put a reverse proxy (nginx/Caddy) in front if internet exposure ever becomes necessary; don't build it into the service |
| Captcha solving | "Automation convenience" | Not the service's job; the Main App handles automation logic including captcha detection; this service only provides the browser | Let the Main App detect and signal via iframe: hand off to human via viewer URL |

---

## Feature Dependencies

```
Vendor Template CRUD (admin UI)
    └──required-by──> POST /sessions idempotent upsert
                          └──required-by──> CDP URL in response
                          └──required-by──> Viewer URL in response
                                               └──required-by──> Viewer URL TTL enforcement
                                               └──required-by──> Viewer URL revocation
                                               └──enables──> Idle detection via viewer WS

Warm-pool sleep/wake
    └──requires──> Idle detection (CDP + viewer dual-signal)
    └──requires──> Session state persistence (profile dir survival)
    └──enables──> POST /sessions wake path
    └──enhanced-by──> POST /sessions/{id}/keepalive heartbeat
    └──enhanced-by──> vendor template default_ttl_minutes

API-key auth (Main App)
    └──required-by──> POST /sessions
    └──required-by──> GET /sessions/{id}
    └──required-by──> PATCH /profiles/{id}
    └──required-by──> DELETE /profiles/{id}

Profile inheritance from template
    └──requires──> Vendor Template CRUD
    └──required-by──> POST /sessions (upsert path creates profile)

Admin dashboard template screens
    └──requires──> Vendor Template CRUD API

Admin dashboard active session list
    └──requires──> GET /sessions active list endpoint
    └──enhanced-by──> per-session debug VNC link (existing VNC viewer)
```

### Dependency Notes

- **POST /sessions requires Vendor Template CRUD:** The upsert can only create a profile if a template exists for the `vendor_type`. Template must be created first via admin UI; the API call itself cannot create templates.
- **Viewer URL requires warm-pool idle detection:** The idle timer must subscribe to viewer WS connect/disconnect events. If the viewer URL is minted but never connected, the idle timer ignores it; if it's connected, the timer resets. These two features must be implemented together.
- **Profile dir survival requires warm-pool sleep design:** Sleep must tear down only the browser process + VNC display; it must never delete the profile directory. This is an implementation constraint, not a new API surface, but it must be designed explicitly.
- **Explicit keepalive enhances idle detection:** The keepalive POST is an additive safety valve; idle detection works without it, but keepalive prevents false-sleep during brief noVNC reconnect windows.
- **Template `default_ttl_minutes` enhances warm-pool:** Without it, there is one global idle timeout; with it, banking vendors can sleep aggressively while social vendors stay warm. The warm-pool implementation must read the profile's inherited value, not a global constant.

---

## MVP Definition

### Launch With (v1)

These are the features that make the service actually useful to the Main App. Without any of these, the Main App cannot use the service.

- [x] `POST /sessions` — idempotent upsert, wake from pool, return `{profile_id, cdp_url, viewer_url}` — the entire value proposition
- [x] Vendor Template entity with CRUD API — required to create any profile
- [x] Admin UI template CRUD screens — humans create vendor configs here
- [x] Profile inheritance from template at upsert time — ensures consistency
- [x] API-key auth for Main App (distinct from admin cookie) — security boundary between ops and consumer
- [x] Profile-scoped signed viewer URL with TTL enforcement — secure iframe embedding
- [x] Viewer URL revocation on profile stop — prevents stale viewer access
- [x] Warm-pool sleep/wake with dual-signal idle detection (CDP + viewer WS) — preserves login state
- [x] Session state persistence (profile dir survives sleep) — the whole point of the warm pool
- [x] `GET /sessions/{id}` — status polling for Main App
- [x] `GET /profiles?vendor_type=X&vendor_connection_id=Y` — lookup by Main App's own IDs
- [x] `PATCH /profiles/{id}` / `DELETE /profiles/{id}` — lifecycle management
- [x] Replace existing `/api/profiles/*` surface with new routes — clean API contract
- [x] Admin dashboard: active session list with per-session debug/viewer link — ops visibility

### Add After Validation (v1.x)

Add once v1 is shipping and the Main App is integrated.

- [ ] `POST /sessions/{id}/keepalive` heartbeat — add when/if spurious idle-sleeps are observed during real 2FA flows
- [ ] Read-only viewer mode (encode in token, suppress pointer events) — add if Main App needs to show view-only previews
- [ ] Vendor template `default_ttl_minutes` per-vendor override — add when different vendors show different inactivity patterns
- [ ] Template `is_active` soft-disable — add when first vendor is deprecated
- [ ] Viewer URL `?navbar=false` flag — add when Main App embeds viewer and complains about toolbar
- [ ] `DELETE /sessions/{id}/viewer-token` explicit revoke — add if Main App needs to revoke without stopping the profile

### Future Consideration (v2+)

Defer until there is concrete need.

- [ ] Proxy provider wiring (residential IPs) — defer until specific vendors actively block or fingerprint; proxy fields already exist
- [ ] Session recording / video replay — defer; substantial storage + pipeline cost with no current user requesting it
- [ ] Additional consumers / second API key — defer; re-evaluate multi-tenancy only when a second consumer actually exists

---

## Feature Prioritization Matrix

| Feature | Consumer Value | Implementation Cost | Priority |
|---------|---------------|---------------------|----------|
| `POST /sessions` idempotent upsert | HIGH | MEDIUM | P1 |
| CDP URL in response | HIGH | LOW | P1 |
| Signed viewer URL (TTL + revocation) | HIGH | MEDIUM | P1 |
| Warm-pool sleep/wake (dual-signal idle) | HIGH | MEDIUM | P1 |
| Session state persistence (profile dir) | HIGH | LOW | P1 |
| Vendor Template CRUD | HIGH | MEDIUM | P1 |
| Template → Profile inheritance | HIGH | LOW | P1 |
| API-key auth (Main App) | HIGH | LOW | P1 |
| `GET /sessions/{id}` status | HIGH | LOW | P1 |
| Profile query by `(vendor_type, vendor_connection_id)` | HIGH | LOW | P1 |
| `PATCH` / `DELETE /profiles/{id}` | MEDIUM | LOW | P1 |
| Admin UI: template CRUD screens | MEDIUM | MEDIUM | P1 |
| Admin UI: active session list | MEDIUM | LOW | P1 |
| `POST /sessions/{id}/keepalive` | MEDIUM | LOW | P2 |
| Read-only viewer mode (token flag) | MEDIUM | LOW | P2 |
| Per-template `idle_timeout_minutes` | MEDIUM | LOW | P2 |
| Template `is_active` flag | LOW | LOW | P2 |
| Viewer URL `?navbar=false` | LOW | LOW | P2 |
| Proxy provider wiring | LOW | HIGH | P3 |
| Session recording / video replay | LOW | HIGH | P3 |
| Multi-tenancy | NONE (single consumer) | HIGH | NEVER |
| Billing / quota metering | NONE | MEDIUM | NEVER |
| Per-call fingerprint overrides | LOW (breaks template contract) | LOW | NEVER |
| Webhooks / push events | LOW | MEDIUM | NEVER |

---

## Competitor Feature Analysis

| Feature | Browserbase | Anchor Browser | Steel.dev | Hyperbrowser | This Service |
|---------|-------------|----------------|-----------|--------------|--------------|
| Session creation API | `POST /v1/sessions` returns `wsEndpoint`, `debuggerUrl` | `POST /v1/sessions` returns `live_view_url`, WS | `POST /v1/sessions` returns CDP + viewer | `POST /sessions` returns `wsEndpoint`, `liveUrl`, `token` | `POST /sessions` idempotent by `(vendor_type, vendor_connection_id)` |
| Persistent profile / context | Contexts API (cookies, localStorage, sessionStorage) | Profiles with `persist: true`; created from sessions | Reusable contexts via cookie/LS injection | Profile ID with `persistChanges` | Profile dir on disk; survives sleep; inherits from vendor template |
| Session keepalive / warm pool | `keepAlive: true`; explicit `REQUEST_RELEASE` to terminate; paid feature | `idle_timeout` + `max_duration` per session | Not documented explicitly | `timeoutMinutes` per session | Implicit warm pool; idle = no CDP AND no viewer; transparent wake |
| Idempotent session by external ID | Not native; caller must track their own mapping | Not native; `metadata` tags for correlation | Not native | Not native | NATIVE — `(vendor_type, vendor_connection_id)` is the upsert key |
| Live / viewer URL | `debuggerUrl` / `debuggerFullscreenUrl`; no explicit TTL documented | `live_view_url`; `one_time_url` option (headful only); iframe sandbox | Session viewer; MP4 replay | `liveUrl` with per-session `token` | HMAC-signed, profile-scoped, TTL-enforced; minted by service; reusable within TTL |
| Read-only viewer | `pointer-events: none` in iframe (client-side only) | `pointer-events: none` (client-side only) | Not documented | `viewOnlyLiveView` parameter | To be encoded in viewer token and enforced at WS layer (P2) |
| Vendor templates | Not native; caller provides full config per session | Not native | Not native | Not native | NATIVE — `vendor_type` key; blueprint locked at template level |
| Template inheritance | N/A | N/A | N/A | N/A | Snapshot into profile at create time; template changes don't affect live profiles |
| Admin UI | Browserbase cloud dashboard; session inspector; video replay | Cloud dashboard | Cloud dashboard | Cloud dashboard | Self-hosted React dashboard; template CRUD + active session ops view |
| Multi-tenancy | Yes (team-level isolation) | Yes (SSO, RBAC, DPA) | Yes | Yes (team) | Deliberately NOT built; single consumer |
| Billing / quotas | Yes (credits per session) | Yes | Yes | Yes (credits) | Deliberately NOT built |
| Captcha solving | Yes (built-in) | Yes | Yes | Yes | NOT built; Main App handles via human iframe |
| Proxy integration | Yes (residential + rotating) | Yes (Anchor VPN) | Yes | Yes (country/city) | Proxy fields exist but no provider wired in v1 |
| Self-hosted / private deployment | Browserless is the self-hosted variant | No | Docker self-host | No | YES — single Docker host; entirely private |
| Scale | Thousands of concurrent sessions | Up to 5,000 per batch call | Fleet-scale | 10k+ concurrent | <20 concurrent (single box); intentional |

---

## Key Observations from Competitive Landscape

**What no commercial service does that this service will do natively:**

1. **Idempotent session by `(vendor_type, vendor_connection_id)`** — All commercial services require the caller to manage the mapping from their own IDs to session IDs. This service eliminates that entirely: the Main App never needs to track "which profile ID goes with which connection."

2. **Vendor template locking** — Commercial services treat every session as a fresh config. This service enforces that all profiles for `vendor_type=stripe` have identical fingerprint, locale, and timezone — governance the Main App never has to think about.

3. **Implicit warm-pool lifecycle (no explicit release)** — Browserbase requires `REQUEST_RELEASE` to terminate a keepalive session; Anchor uses explicit timeout config. This service's idle detection is signal-based (CDP + viewer WS), requiring zero Main App lifecycle calls beyond `POST /sessions`.

**What commercial services have that this service deliberately skips:**

- Multi-tenancy, billing, quotas, CAPTCHA solving, residential proxy rotation, video replay — all justified anti-features for a single-consumer private deployment.

---

## Sources

- [Browserbase Live View documentation](https://docs.browserbase.com/features/session-live-view) — MEDIUM confidence (live view URL shape, iframe sandbox, fullscreen/bordered variants)
- [Browserbase Observability](https://docs.browserbase.com/features/observability) — HIGH confidence (video recording, events timeline, CDP/console logs, dashboard)
- [Browserbase Long Sessions / keepAlive](https://docs.browserbase.com/guides/long-running-sessions) — HIGH confidence (keepAlive semantics, REQUEST_RELEASE, max 6h)
- [Anchor Browser API reference (llms-full.txt)](https://docs.anchorbrowser.io/llms-full.txt) — HIGH confidence (full endpoint list, session model, live_view_url, one_time_url, idle_timeout, profile model)
- [Anchor Browser Live View](https://docs.anchorbrowser.io/advanced/browser-live-view) — HIGH confidence (one-time URL, iframe sandbox, pointer-events read-only pattern)
- [Hyperbrowser Create Session](https://www.hyperbrowser.ai/docs/api-reference/create-new-session) — HIGH confidence (full parameter set, liveUrl + wsEndpoint in response, viewOnlyLiveView flag)
- [Steel.dev](https://steel.dev/) — MEDIUM confidence (session API shape, live viewer, persistent contexts)
- [Browserless /sessions API](https://docs.browserless.io/enterprise/utility-functions/sessions) — HIGH confidence (active session list endpoint, session object fields)
- [Scrapfly: Best Cloud Browser APIs 2026](https://scrapfly.io/blog/posts/best-cloud-browser-apis) — MEDIUM confidence (ecosystem overview)
- [Kernel vs Hyperbrowser comparison](https://www.kernel.sh/blog/kernel-vs-hyperbrowser) — LOW confidence (page 404'd at research time)
- PROJECT.md, ARCHITECTURE.md, INTEGRATIONS.md — HIGH confidence (existing codebase ground truth)

---

*Feature research for: CloakBrowser-Manager — single-consumer headless browser profile service*
*Researched: 2026-04-22*
