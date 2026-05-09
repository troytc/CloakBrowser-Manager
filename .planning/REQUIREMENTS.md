# Requirements: VendorBrowser

**Defined:** 2026-04-22
**Core Value:** One idempotent API call gives the Main App a live CDP URL + a scoped iframe viewer URL for a vendor-specific browser profile, with session state preserved across automation runs via a warm pool.

## v1 Requirements

Requirements for the first release of the refocused service. Each maps to roadmap phases (traceability at the bottom).

### Templates

- [ ] **TMPL-01**: Admin can create vendor templates via the admin dashboard with a full blueprint (`fingerprint_seed` rules, `timezone`, `locale`, `platform`, `screen` dimensions, `gpu`, `humanize`, `launch_args`, `clipboard_sync`, `proxy` fields)
- [ ] **TMPL-02**: Templates are uniquely keyed by `vendor_type`; the database rejects duplicates
- [ ] **TMPL-03**: Admin can edit vendor templates; edits apply to profiles created after the edit and do not mutate snapshots of existing profiles
- [ ] **TMPL-04**: Admin can delete vendor templates; deletion is blocked while any profiles exist for that `vendor_type`
- [ ] **TMPL-05**: Template fields are snapshot-copied into the profile row at creation; the warm pool never re-reads the live template on wake

### Sessions

- [ ] **SESS-01**: `POST /sessions` with `{vendor_type, vendor_connection_id}` performs idempotent upsert — creates a profile from the matching template if none exists, otherwise returns the existing profile
- [ ] **SESS-02**: `POST /sessions` response includes `{profile_id, cdp_url, vnc_viewer_url}` and the current session `state`
- [ ] **SESS-03**: `POST /sessions` wakes a profile from warm-pool sleep if it is currently `STOPPED` or `IDLE`, returning only after the browser is viable
- [ ] **SESS-04**: A profile remains `RUNNING` while `cdp_attach_count > 0` OR `viewer_attach_count > 0`
- [ ] **SESS-05**: A profile transitions to `IDLE` when both attach counts reach zero; transitions to `STOPPED` after `IDLE_TIMEOUT_SECONDS` (default 600) of uninterrupted idle
- [ ] **SESS-06**: The idle timer cancels immediately when either CDP or viewer reattaches
- [ ] **SESS-07**: Concurrent `POST /sessions` calls for the same `(vendor_type, vendor_connection_id)` serialize via a per-key `asyncio.Lock`; no duplicate launches occur
- [ ] **SESS-08**: The `profiles` table enforces `UNIQUE(vendor_type, vendor_connection_id)` at the database layer
- [ ] **SESS-09**: Chromium launches are guarded by `asyncio.Semaphore(3)` to cap simultaneous launches and prevent thundering-herd OOM
- [ ] **SESS-10**: After every launch, the service probes `about:blank` to confirm the Chromium process is live and responsive; silent wake failures raise a clean error
- [ ] **SESS-11**: Before every launch, the service removes stale Chromium `SingletonLock` / `SingletonCookie` / `SingletonSocket` files from the profile directory
- [ ] **SESS-12**: Profile state (cookies, localStorage, cache, IndexedDB — anything in the Chromium profile directory) persists across warm-pool sleep/wake cycles
- [ ] **SESS-13**: `GET /sessions/{profile_id}` returns `{state, cdp_attach_count, viewer_attach_count, idle_expires_at, last_launched_at}`
- [ ] **SESS-14**: `DELETE /sessions/{profile_id}` forcefully stops a running session (tears down Chromium and KasmVNC) without deleting the profile row

### Profiles

- [ ] **PROF-01**: `GET /profiles?vendor_type=X&vendor_connection_id=Y` returns the matching profile or 404
- [ ] **PROF-02**: `GET /profiles` returns all profiles; supports filtering by `vendor_type`
- [ ] **PROF-03**: `PATCH /profiles/{id}` updates admin-owned fields (notes / explicit template overrides); cannot change identity keys
- [ ] **PROF-04**: `DELETE /profiles/{id}` deletes the profile row, stops the session if running, and removes the on-disk profile directory

### Viewer

- [ ] **VIEW-01**: `POST /sessions` response includes `vnc_viewer_url` — a signed, short-lived URL scoped to the returned `profile_id`
- [ ] **VIEW-02**: Viewer tokens are JWTs signed with HS256 using `VIEWER_SECRET`; claims are `{profile_id, exp, jti, iat}`
- [ ] **VIEW-03**: Viewer token TTL defaults to 300 seconds; configurable via `VIEWER_TOKEN_TTL_SECS`
- [ ] **VIEW-04**: Viewer tokens are delivered via URL fragment (`#token=...`), never querystring; the token never appears in proxy/access logs
- [ ] **VIEW-05**: `/viewer/{profile_id}/ws` WebSocket route validates token signature, expiry, and `profile_id` match on upgrade; rejects invalid/expired/wrong-profile tokens with 4401
- [ ] **VIEW-06**: Viewer tokens are single-use — a server-side JTI registry marks a token consumed on first successful WS upgrade; subsequent attempts with the same `jti` are rejected
- [ ] **VIEW-07**: The viewer WS route increments `viewer_attach_count` on connect and decrements on disconnect; the count feeds the warm-pool idle state machine
- [ ] **VIEW-08**: Viewer responses carry `Content-Security-Policy: frame-ancestors <MAIN_APP_ORIGIN>` (configurable) to restrict iframe embedding to the Main App origin
- [ ] **VIEW-09**: End-to-end iframe embed works: the Main App embeds `vnc_viewer_url`, noVNC extracts the fragment token, WS upgrade succeeds, VNC frames stream, keyboard/mouse/clipboard events flow

### Security

- [ ] **SEC-01**: Machine API routes (`/sessions/*`, `/profiles/*`) are protected by `APIKeyHeader` expecting the `MAIN_APP_API_KEY` value; missing/invalid keys return 401
- [ ] **SEC-02**: Admin routes (`/admin/*` and the dashboard shell) remain protected by the existing `AuthMiddleware` (bearer token / `auth_token` cookie); the two auth surfaces are strictly segregated by router prefix
- [ ] **SEC-03**: The admin `auth_token` cookie is set with `SameSite=Strict` and `HttpOnly`
- [ ] **SEC-04**: Admin API responses carry `Content-Security-Policy: frame-ancestors 'none'` — the admin surface cannot be framed by anything
- [ ] **SEC-05**: The service refuses to start when `VIEWER_SECRET` or `MAIN_APP_API_KEY` is unset (or blank) in production mode
- [ ] **SEC-06**: `clipboard_sync` defaults to `false` in the vendor template schema and in any profile created without an explicit value
- [ ] **SEC-07**: `GET /profiles/{id}/clipboard` requires a viewer-scoped signed token; requests authenticated only by the Main App API key are rejected

### Admin UI

- [ ] **ADM-01**: Admin dashboard has a Templates page: list, create, edit, delete vendor templates with inline validation
- [ ] **ADM-02**: Admin dashboard has a Sessions page: list all profiles with `vendor_type`, `vendor_connection_id`, `state`, `cdp_attach_count`, `viewer_attach_count`, uptime, last-launched-at
- [ ] **ADM-03**: Each session row in the admin dashboard opens an admin-authenticated live VNC viewer (uses existing `/api/profiles/{id}/vnc` admin route — not the signed-token viewer path)
- [ ] **ADM-04**: The old end-user profile-creation UI (direct field entry, Launch button) is removed; profiles only come into existence via `POST /sessions`

### Operations

- [ ] **OPS-01**: The old `/api/profiles/{id}/launch` and `/api/profiles/{id}/stop` endpoints are removed
- [ ] **OPS-02**: The old `/api/profiles/*` CRUD surface is replaced by the new machine API (`/profiles` with `(vendor_type, vendor_connection_id)` lookup + admin CRUD behind admin auth)
- [ ] **OPS-03**: Database schema migration adds the `vendor_templates` table and adds `vendor_type`, `vendor_connection_id`, and `template_snapshot` columns to `profiles`; existing rows get a one-time backfill or are dropped per the migration plan
- [ ] **OPS-04**: Docker entrypoint performs `chown -R` to the `CHROME_UID` on the mounted profile-state volume before the service starts, preventing Chromium cookie-flush failures from UID mismatch
- [ ] **OPS-05**: `docker-compose.yml` and `.env.example` document the new required env vars: `MAIN_APP_API_KEY`, `VIEWER_SECRET`, `MAIN_APP_ORIGIN`, `IDLE_TIMEOUT_SECONDS`, `VIEWER_TOKEN_TTL_SECS`

## v2 Requirements

Acknowledged but deferred to a later release.

### Resilience

- **SAFE-01**: `POST /sessions/{id}/keepalive` heartbeat endpoint — explicit safety valve if noVNC reconnect windows cause false-idle during 2FA
- **SAFE-02**: Read-only viewer mode (suppress pointer events + keyboard at WS layer; claim encoded in token)
- **SAFE-03**: Per-template `idle_timeout_minutes` override — let banking templates sleep aggressively, social templates idle longer

### Governance

- **GOV-01**: Template `is_active` soft-disable flag to block new profile creation from deprecated templates without deleting
- **GOV-02**: Viewer URL navbar-suppression flag (cleaner iframe embed experience)

### Future

- **FUT-01**: Upstream proxy provider wiring (residential IPs) — existing `proxy` fields get wired to a real provider
- **FUT-02**: Session recording / video replay
- **FUT-03**: Second Main App consumer — tenant-scoped API keys and profile isolation

## Out of Scope

Explicit exclusions. These are documented to prevent scope creep, not because they're bad ideas.

| Feature | Reason |
|---------|--------|
| Multi-tenancy / multiple downstream apps | Exactly one trusted Main App; per-tenant isolation would be over-engineering |
| OAuth for machine auth | Shared API key is sufficient for one consumer |
| Per-call fingerprint overrides from Main App | Breaks the template-governance contract; fingerprint stability is a core pitfall mitigation |
| Webhooks / push events to Main App | Main App polls `GET /sessions/{id}` on demand; no event bus needed |
| Distributed / horizontally scaled deployment | Target is single-box, <20 concurrent; in-memory state assumptions are acceptable |
| CAPTCHA solving | Out of service scope; Main App or human operator handles it |
| Session recording / video replay (v1) | Storage + pipeline cost without a current requester; deferred to v2+ |
| View-only / read-only viewer mode (v1) | Deferred; v1 ships interactive only |
| Profile cloning / export / migration tooling | Not in v1 scope |
| Template inheritance chains | Single-level templates per `vendor_type` are sufficient |
| Public / internet-exposed deployment | Service is deployed on a network the Main App can reach privately |
| End-user identity in this service | Service knows only `vendor_connection_id` (opaque); end-user identity lives in the Main App |

## Traceability

Populated by the roadmap agent.

| Requirement | Phase | Status |
|-------------|-------|--------|
| TMPL-01 | Phase 1 | Pending |
| TMPL-02 | Phase 1 | Pending |
| TMPL-03 | Phase 1 | Pending |
| TMPL-04 | Phase 1 | Pending |
| TMPL-05 | Phase 1 | Pending |
| SESS-01 | Phase 2 | Pending |
| SESS-02 | Phase 2 | Pending |
| SESS-03 | Phase 2 | Pending |
| SESS-04 | Phase 2 | Pending |
| SESS-05 | Phase 2 | Pending |
| SESS-06 | Phase 2 | Pending |
| SESS-07 | Phase 2 | Pending |
| SESS-08 | Phase 2 | Pending |
| SESS-09 | Phase 2 | Pending |
| SESS-10 | Phase 2 | Pending |
| SESS-11 | Phase 2 | Pending |
| SESS-12 | Phase 2 | Pending |
| SESS-13 | Phase 2 | Pending |
| SESS-14 | Phase 2 | Pending |
| PROF-01 | Phase 2 | Pending |
| PROF-02 | Phase 2 | Pending |
| PROF-03 | Phase 2 | Pending |
| PROF-04 | Phase 2 | Pending |
| VIEW-01 | Phase 3 | Pending |
| VIEW-02 | Phase 3 | Pending |
| VIEW-03 | Phase 3 | Pending |
| VIEW-04 | Phase 3 | Pending |
| VIEW-05 | Phase 3 | Pending |
| VIEW-06 | Phase 3 | Pending |
| VIEW-07 | Phase 3 | Pending |
| VIEW-08 | Phase 3 | Pending |
| VIEW-09 | Phase 3 | Pending |
| SEC-01 | Phase 2 | Pending |
| SEC-02 | Phase 3 | Pending |
| SEC-03 | Phase 3 | Pending |
| SEC-04 | Phase 3 | Pending |
| SEC-05 | Phase 1 | Pending |
| SEC-06 | Phase 1 | Pending |
| SEC-07 | Phase 3 | Pending |
| ADM-01 | Phase 4 | Pending |
| ADM-02 | Phase 4 | Pending |
| ADM-03 | Phase 4 | Pending |
| ADM-04 | Phase 4 | Pending |
| OPS-01 | Phase 4 | Pending |
| OPS-02 | Phase 4 | Pending |
| OPS-03 | Phase 1 | Pending |
| OPS-04 | Phase 1 | Pending |
| OPS-05 | Phase 1 | Pending |

**Coverage:**
- v1 requirements: 48 total
- Mapped to phases: 48
- Unmapped: 0

| Phase | Count | Requirements |
|-------|-------|-------------|
| Phase 1 | 10 | TMPL-01..05, SEC-05, SEC-06, OPS-03, OPS-04, OPS-05 |
| Phase 2 | 19 | SESS-01..14, PROF-01..04, SEC-01 |
| Phase 3 | 13 | VIEW-01..09, SEC-02, SEC-03, SEC-04, SEC-07 |
| Phase 4 | 6 | ADM-01..04, OPS-01, OPS-02 |

---
*Requirements defined: 2026-04-22*
*Last updated: 2026-04-22 — traceability filled by roadmap agent*
