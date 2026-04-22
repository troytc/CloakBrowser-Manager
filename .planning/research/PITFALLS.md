# Pitfalls Research

**Domain:** Warm-pool headless-browser service with signed-iframe viewer and vendor-portal automation
**Researched:** 2026-04-22
**Confidence:** HIGH (all critical items verified against official sources, GitHub issues, or production post-mortems)

---

## Critical Pitfalls

### Pitfall 1: Chromium SingletonLock Not Released on Unclean Shutdown

**What goes wrong:**
When a Chromium process is killed with SIGKILL (container OOM, Docker stop, or host crash), the `SingletonLock`, `SingletonSocket`, and `SingletonCookie` files remain in the profile directory. On the next warm-pool wake, `launchPersistentContext` silently exits without error or launches successfully but fails to read cookies, localStorage, or cached sessions from the profile — meaning the session looks alive to Playwright but the login state is gone.

**Why it happens:**
Chromium uses filesystem-based singleton locks. SIGKILL gives Chrome zero cleanup time. The lock files are advisory — Chromium checks for them on startup, sees them, and either bails or opens a fresh empty profile. The Playwright call often returns success even when Chrome opened a blank profile instead of the persisted one.

**How to avoid:**
1. Always attempt SIGTERM with a 10-second grace period before any SIGKILL. In `browser_manager.py`, replace `proc.kill()` with a SIGTERM + wait + SIGKILL escalation.
2. On warm-pool wake, before calling `launchPersistentContext`, check for and remove stale lock files: `SingletonLock`, `SingletonSocket`, `SingletonCookie` in the profile dir. Do this unconditionally — if Chrome is actually running, Playwright will detect it by other means.
3. After launch, immediately verify session state by checking a known cookie name or `localStorage` key specific to the vendor portal. If missing, mark the profile as `needs_reauth` and surface this to the Main App in the `POST /sessions` response.

**Warning signs:**
- `launchPersistentContext` succeeds but automation immediately reaches a login page instead of a logged-in state
- Profile directory timestamps show a `Default/Cookies` file with a very recent mtime (Chrome recreated it)
- Warm-pool wake latency spikes to >10s (Chrome doing first-run profile init)

**Phase to address:** Sessions-and-warm-pool phase

---

### Pitfall 2: Concurrent POST /sessions for the Same (vendor_type, vendor_connection_id) Creates Two Profiles

**What goes wrong:**
If the Main App sends two simultaneous `POST /sessions` requests for the same `(vendor_type, vendor_connection_id)` — during a retry storm, network glitch, or client-side double-click — both requests pass the "does profile exist?" check before either has committed the INSERT. Result: two profile rows, two Chrome processes launched, two VNC displays allocated, both burning memory. Neither gets cleaned up cleanly because the service now thinks there are two valid profiles.

**Why it happens:**
The existing codebase has no per-key advisory lock. The check-then-insert pattern in application code is not atomic. SQLite with WAL mode still allows two readers to pass through the existence check before either writer commits. Even with a UNIQUE constraint on the column pair, the application code will raise an unhandled `IntegrityError` that propagates as a 500 to one caller rather than a 200 with the existing profile.

**How to avoid:**
1. Add a UNIQUE constraint on `(vendor_type, vendor_connection_id)` to the profiles table as a hard guarantee.
2. In the `POST /sessions` handler, use `INSERT OR IGNORE` followed by `SELECT` (upsert pattern) wrapped in a single SQLite transaction, not a Python-level check-then-insert.
3. Add an in-process asyncio lock keyed by `(vendor_type, vendor_connection_id)` — an `asyncio.Lock` stored in a dict — so that concurrent requests for the same profile serialize rather than race.
4. Return 200 (not 201) if the profile already existed and is running, with the existing `cdp_url` and `vnc_viewer_url`.

**Warning signs:**
- Duplicate rows in the `profiles` table with the same vendor/connection pair
- Memory usage growing faster than the number of unique vendor connections
- `display_number` allocation gaps (two displays allocated, only one returned to caller)

**Phase to address:** Sessions-and-warm-pool phase

---

### Pitfall 3: Warm-Pool Idle Detection False-Positives Kill Live Sessions

**What goes wrong:**
The idle timer fires based on "no CDP client AND no viewer iframe attached." In practice, the Main App holds the CDP URL to automate the browser and may pause between automation steps (waiting on a network response, human thinking time). During that pause, the service incorrectly sees zero active CDP connections and starts the shutdown countdown — or worse, immediately sleeps the profile. The next automation call from the Main App hits a dead browser.

**Why it happens:**
Playwright's `browser.connected` and active CDP sessions are not the same as "the Main App is actively using this profile." There is no heartbeat from the Main App to this service, and the service has no way to distinguish "paused automation" from "caller abandoned the session."

**How to avoid:**
1. Use a "last activity" timestamp updated on every CDP command, VNC frame, or explicit keepalive, not a binary "connected/disconnected" flag.
2. Add a `keepalive` endpoint (`POST /sessions/{id}/keepalive`) that the Main App calls during long automation pauses. Document the expected call interval.
3. Set the idle timeout to at least 5 minutes (not seconds), configurable via environment variable, with a sane default that survives a 2FA page load + human response time.
4. Distinguish between "Playwright connection closed" (CDP client disconnected cleanly) and "Playwright connection never opened" (wake request received but nothing connected yet). The latter should not start the idle clock immediately.

**Warning signs:**
- Main App logs showing frequent "session expired, re-authenticating" events
- Warm-pool wake latency spikes occurring mid-automation-sequence
- `POST /sessions` calls followed immediately by a second `POST /sessions` from the same caller within the same automation sequence

**Phase to address:** Sessions-and-warm-pool phase

---

### Pitfall 4: Thundering-Herd Wake on Service Restart

**What goes wrong:**
The service restarts (deploy, crash, OOM). All warm-pool profiles are in `stopped` state. The Main App — which has been retrying the `POST /sessions` call — immediately sends 10–20 simultaneous wake requests. Launching 20 Chromium processes + 20 KasmVNC instances at the same time saturates CPU and memory for 30–60 seconds. The first few launches fail (OOM or timeout), leaving their profiles in a corrupted partially-launched state. The retry storm makes recovery worse.

**Why it happens:**
The existing codebase has no launch queue or concurrency cap. `BrowserManager.running` is rebuilt from scratch on restart with no launch serialization. At 20 concurrent profiles, each Chrome process consumes 300–800MB on startup; 20 simultaneous launches can require 6–16GB in the first 60 seconds.

**How to avoid:**
1. Add an asyncio semaphore (e.g., `asyncio.Semaphore(3)`) that limits concurrent launches to 3 at a time. Queue the rest. The `POST /sessions` call blocks until a slot is available (use an appropriate timeout, e.g., 30s).
2. On service startup, do NOT auto-wake any profiles. Wake lazily, on demand, when `POST /sessions` is called.
3. Track `LAUNCH_IN_PROGRESS` as an explicit profile state (not just `stopped` vs `running`) so concurrent wake attempts for the same profile see the in-progress state and wait rather than starting a second launch.

**Warning signs:**
- Post-restart, `docker stats` shows memory peaking above 80% immediately
- Multiple `launchPersistentContext` calls failing with `spawn ENOMEM` or `timeout` errors in the first 60 seconds after restart
- Profiles stuck in "running" state in the database but absent from `BrowserManager.running`

**Phase to address:** Sessions-and-warm-pool phase

---

### Pitfall 5: Signed Viewer Token in the URL Querystring Gets Logged by Every Proxy

**What goes wrong:**
The signed viewer URL is embedded in an iframe: `<iframe src="https://service/viewer?token=eyJ...">`. The token is in the querystring. Every nginx access log, CDN edge log, application server log, and browser history on the Main App side now contains the full token. Tokens are valid for their TTL (however long that is). An attacker with log access can replay the token to get an interactive VNC session viewing a real vendor-portal login.

**Why it happens:**
Querystring tokens are the path of least resistance — easy to generate and embed in an `src` attribute. The logging problem is not obvious during development because logs are not being monitored.

**How to avoid:**
1. Pass the token as a URL fragment (`#token=...`) instead of a querystring. Fragments are not sent to servers and not logged by proxies. The noVNC client-side JavaScript reads `window.location.hash` to extract and present the token in the WebSocket upgrade request.
2. Alternatively, exchange the token via a POST to a dedicated `/viewer/exchange` endpoint that returns a short-lived session cookie scoped to the viewer path, then redirect to the viewer without the token in the URL.
3. If the token must be in the URL for technical reasons, set its TTL to 60 seconds (single-use redirect), not minutes. The viewer then negotiates a session cookie on first load.
4. Bind the token to the requesting IP address at mint time; reject if the IP at use-time differs.

**Warning signs:**
- nginx or CDN access logs showing `token=eyJ` in GET request URLs
- Token TTL longer than 5 minutes (any log rotation cycle will archive it)

**Phase to address:** Viewer-and-signed-URL phase

---

### Pitfall 6: Token Replay — Signed URL Used More Than Once by Attacker

**What goes wrong:**
A signed viewer URL is minted, used to open the VNC iframe, and the session remains valid for 15+ minutes. If the token is stolen (from logs, Referer header, browser history, or a compromised Main App), any party can open a second VNC session to the same profile concurrently — while the real user is also viewing it. Two VNC clients watching the same KasmVNC display is technically valid; neither is warned.

**Why it happens:**
Stateless signed tokens are easy to implement but have no revocation mechanism. The service validates the signature and TTL but does not track whether the token has already been used to establish a session.

**How to avoid:**
1. Maintain a server-side token registry (`used_tokens` table or in-memory dict with TTL eviction). On first WebSocket upgrade from the viewer, mark the token as consumed. Reject any subsequent upgrade with the same token JTI.
2. After a viewer WebSocket connects successfully, immediately revoke the URL token. The ongoing session is tied to the WebSocket connection, not the URL.
3. Set viewer token TTL to 60 seconds (time-to-connect window), not the session duration. The WebSocket session itself lives as long as it's connected.

**Warning signs:**
- Two concurrent WebSocket connections to the same profile's VNC endpoint
- VNC framebuffer showing cursor moving without a connected human (second ghost session)

**Phase to address:** Viewer-and-signed-URL phase

---

### Pitfall 7: Fingerprint Inconsistency on Sleep/Wake Breaks Vendor Anti-Bot Detection

**What goes wrong:**
A profile is warm — logged in, session active. It idles for 2 hours and is put to sleep. On wake, the browser relaunches. If the CloakBrowser fingerprint seed produces stable outputs (canvas hash, WebGL renderer, AudioContext values) but ANY of the following change between sleep and wake cycles, the vendor portal's anti-bot system sees a "new device" and triggers step-up auth or hard block: User-Agent (browser version update), screen resolution (profile config changed), timezone offset (host system TZ change), platform string (Docker container recreation).

**Why it happens:**
The fingerprint seed controls noise injected into canvas/WebGL/audio, but it does not control User-Agent string, screen dimensions, or navigator.platform — those come from the launch configuration. If the vendor template is edited between wake cycles, or if the CloakBrowser binary is updated between restarts, these values change while the session cookie attributes still claim the old identity.

**How to avoid:**
1. Treat the vendor template as immutable after the first profile for that vendor_type is created. Lock the fingerprint parameters used at profile creation time INTO the profile row (not just a template reference). "What was actually used" must survive template edits.
2. Pin the CloakBrowser binary version in the Docker image. Do not pull latest; pin to a specific version tag. Verify with a SHA checksum.
3. Add `--disable-webrtc` or equivalent launch arg to every vendor template to prevent WebRTC STUN requests revealing the Docker host's real IP, which would mismatch any claimed geolocation.
4. After any warm-pool wake, run a self-check: load `about:blank`, execute the fingerprint probe script, compare critical fields (UA, platform, screen dims, timezone) against what was stored at profile creation. Alert if any field changed; do not silently proceed.

**Warning signs:**
- Vendor portal redirecting to login page immediately on warm-pool wake despite valid cookies
- Vendor portal showing a "new device" 2FA challenge after a sleep/wake cycle that was not triggered by cookie expiry
- `navigator.userAgent` in the browser console showing a newer Chrome version than was used to establish the original login

**Phase to address:** Template-and-schema phase (lock fingerprint at creation); Sessions-and-warm-pool phase (self-check on wake)

---

### Pitfall 8: CDP URL Exposed to Main App Has No Expiry or Scope Binding

**What goes wrong:**
`POST /sessions` returns a `cdp_url` like `ws://service:9222`. The Main App connects Playwright to it. There is no mechanism to expire or revoke this CDP URL. If the Main App stores the `cdp_url` in its database or logs, any future holder of that URL can connect raw CDP to the browser — bypassing all auth, reading all page content, navigating to arbitrary URLs, and exfiltrating vendor session cookies.

**Why it happens:**
Raw CDP WebSocket URLs are implicit trust — whoever has the URL has full control. The existing service exposes KasmVNC's WebSocket port directly; the same risk applies to CDP.

**How to avoid:**
1. Do not expose the raw KasmVNC WebSocket port or Chromium's CDP port to the Main App directly. Instead, proxy them through the FastAPI app, which enforces auth on the WebSocket upgrade.
2. Scope the CDP proxy to the requesting API key and profile ID. Reject CDP connections that present a valid token for profile A while trying to control profile B.
3. Rotate the CDP proxy token on every `POST /sessions` call. The previous token should stop working when a new one is issued (or on profile sleep).
4. Document the `cdp_url` as a one-session credential, not a durable connection string. The Main App must call `POST /sessions` again after any disconnection rather than reconnecting to a stale URL.

**Warning signs:**
- Main App caching `cdp_url` values in its database with no TTL
- Playwright connection errors from Main App when it tries to reconnect to a stale `cdp_url` days later
- CDP proxy not checking authentication on the WebSocket upgrade request

**Phase to address:** Sessions-and-warm-pool phase

---

### Pitfall 9: Admin Auth Cookie and Main App API Key Share the Same Cookie Jar / CSRF Surface

**What goes wrong:**
The admin dashboard uses an `auth_token` cookie. The Main App uses a Bearer token in the `Authorization` header. If an admin user has the dashboard open in their browser while a vendor portal is displayed in an iframe, a vendor portal page with malicious JavaScript can issue a `fetch()` to the admin API (same-origin because the iframe viewer and admin dashboard are on the same host) with the admin cookie automatically attached. The vendor portal can then enumerate profiles, delete them, or read session state.

**Why it happens:**
The admin API and the viewer endpoint live on the same origin. Browser same-origin policy does not protect against `fetch()` from within the iframe's domain to the server's own API when cookies are in play. The existing `SameSite` cookie setting is not confirmed to be `Strict` or `Lax`.

**How to avoid:**
1. Set `SameSite=Strict` on the `auth_token` cookie. This prevents the cookie from being sent on any cross-site request, including `fetch()` from inside the iframe.
2. Separate the admin API routes under `/admin/` and set `frame-ancestors 'none'` on ALL admin API responses. This prevents any iframe context from loading admin pages.
3. The viewer endpoint's CSP must include `frame-ancestors <Main App origin>` but explicitly NOT include the admin origin or `*`.
4. Add CSRF token validation to all admin state-mutating endpoints (not just GET). The existing architecture skips this because it assumes Bearer token (not cookie) auth, but the cookie auth path needs CSRF protection.

**Warning signs:**
- `auth_token` cookie without explicit `SameSite` attribute (defaults to `Lax`, which is insufficient)
- Admin API accessible from within a viewer iframe in the browser console
- No `X-Frame-Options: DENY` on admin page responses

**Phase to address:** Viewer-and-signed-URL phase

---

### Pitfall 10: Docker Volume UID Mismatch Silently Corrupts Profile Persistence

**What goes wrong:**
The Chromium profile directories are volume-mounted from the host. Inside the container, Chrome runs as UID 1000 (or whatever the Dockerfile sets). On the host, the volume directory was created as root or a different UID. Chrome can write new profile data successfully during the session but fails to flush the `Cookies` SQLite database on graceful shutdown because it cannot `flock()` or rename temp files across UID boundaries. The profile appears to persist but the cookie database is always the stale version from before the session.

**Why it happens:**
Docker creates volume directories as root by default. If the container entrypoint does not `chown` the profile directories to the Chrome user UID before launching, Chrome writes to a tmpfs copy or fails silently when flushing. The failure is invisible because Chrome returns exit code 0.

**How to avoid:**
1. In the Docker entrypoint script, `chown -R ${CHROME_UID}:${CHROME_GID} /data/profiles` before starting the service.
2. Pin the UID in the Dockerfile with `USER 1000` and document it. Use the same UID for the host-side volume ownership.
3. After container startup, run a write-verify: create a sentinel file in each profile directory, confirm it's readable as the Chrome user, and log a startup error if it fails.
4. Mount profile volumes with explicit `uid` and `gid` options in `docker-compose.yml` (`user: "1000:1000"` on the service).

**Warning signs:**
- `Cookies` file mtime not updating after profile stop (Chrome couldn't flush)
- `Permission denied` in Chrome stderr logs for `Default/Cookies-journal` or `Default/Cookies`
- Container restart causing loss of login state that was present during the previous run

**Phase to address:** Template-and-schema phase (Dockerfile and volume config)

---

### Pitfall 11: Clipboard Sync Leaks Vendor Portal Credentials into the Main App

**What goes wrong:**
The existing `clipboard_sync` feature bridges the browser's clipboard to the host. When the iframe viewer is open and a vendor portal automator runs `Ctrl+A, Ctrl+C` to capture page content (including OTP codes, session tokens, or password fields), that clipboard content is readable via `GET /api/profiles/{id}/clipboard` — which is accessible to the Main App via its API key. An OTP copied inside the vendor portal is now available to any holder of the API key, not just the human in the iframe.

**Why it happens:**
The clipboard bridge was designed for the original single-user browser farm where the operator controls both the automation and the VNC viewer. In the new architecture, the Main App (trusted but not identical to the human) can poll the clipboard endpoint at any time.

**How to avoid:**
1. Make `clipboard_sync` default `false` for all vendor templates. Require explicit per-template opt-in with documentation of the security implication.
2. Scope clipboard read access: only the VNC viewer session (authenticated by the signed viewer URL) should be able to read clipboard content, not the Main App's API key.
3. Do not allow the Main App's API key to call `GET /api/profiles/{id}/clipboard` at all. This endpoint should be viewer-only.
4. If clipboard sync is needed for automation (pasting into forms), use Playwright's `page.fill()` instead — which writes directly to the input, never to the clipboard.

**Warning signs:**
- `clipboard_sync: true` in any vendor template (check on template creation)
- Main App code calling `GET /api/profiles/{id}/clipboard` in a polling loop
- OTP codes or session tokens appearing in application logs (from clipboard relay logging)

**Phase to address:** Template-and-schema phase

---

### Pitfall 12: Zombie Xvnc Processes After Partial Launch Failure

**What goes wrong:**
A profile launch sequence starts: (1) Xvnc starts on display :105, (2) CloakBrowser/Chrome launch fails (OOM, bad launch_args, missing binary). The exception handler calls `vnc.stop_vnc()` but this only sends SIGTERM to the Xvnc PID it tracked. If Xvnc spawned helper processes (websockify, stunnel, or auxiliary x11 processes), those survive. On the next restart, the display allocation scan skips :105 (allocated), allocates :106, and the orphan on :105 accumulates. Over dozens of partial failures, display space is exhausted and memory leaks steadily.

**Why it happens:**
The existing `cleanup_stale()` uses `pkill Xvnc` which catches the main process but may not reap all child processes. The display allocation map is rebuilt in memory at startup by scanning ports, not by querying a persistent record. A display number leaks if the Xvnc PID dies but a child process holds the socket open.

**How to avoid:**
1. Use a process group kill (`os.killpg(os.getpgid(proc.pid), signal.SIGTERM)`) so all children of Xvnc die together.
2. Persist display allocations in SQLite (`display_allocations` table with `profile_id`, `display_number`, `pid`, `allocated_at`). On startup, reconcile the table against actually-running processes. Release any entry whose PID is gone.
3. After `stop_vnc()`, verify the display socket (`/tmp/.X{N}-lock`) is deleted before marking the display as free. If it persists after 5 seconds, force-remove it and log a warning.

**Warning signs:**
- `ps aux | grep Xvnc` showing more processes than `len(BrowserManager.running)`
- `/tmp/.X{N}-lock` files present for display numbers not in the running dict
- Display numbers allocated monotonically increasing over successive restarts (never recycled)

**Phase to address:** Sessions-and-warm-pool phase

---

### Pitfall 13: Silent Wake Failure — Profile Reports Running But Browser Is Unreachable

**What goes wrong:**
The warm-pool wake sequence completes, `running[profile_id]` is populated, `POST /sessions` returns `{cdp_url, vnc_viewer_url}`. But the Playwright `BrowserContext` is stale — Chrome crashed silently after launch and the Playwright object has not detected it yet. The Main App connects, issues one CDP command, gets a `Target closed` exception, and now has to decide what to do with no guidance from the service. The service still believes the profile is running.

**Why it happens:**
Playwright's `browser.connected` property is not a live health probe — it reflects the last known state. A Chrome renderer crash that happens after the initial connection succeeds does not immediately surface through `browser.connected`. The service has no periodic health check loop for running profiles.

**How to avoid:**
1. After `launchPersistentContext` returns, immediately issue a probe: `await context.new_page(); await page.goto("about:blank"); await page.close()`. If this fails, the launch failed. Retry once; if still failing, mark the profile as `error` and return 503 from `POST /sessions`.
2. Add a background health-check coroutine that, for each running profile, periodically runs `await page.evaluate("1+1")` with a 5s timeout. On failure, mark the profile `crashed` in-memory and attempt recovery.
3. Expose a `GET /sessions/{id}/status` endpoint that returns real-time health, not just the DB state.

**Warning signs:**
- `POST /sessions` returning 200 followed immediately by a `Target closed` CDP error in the Main App
- `BrowserManager.running` dict growing but memory usage not growing proportionally (stale entries for dead browsers)
- Main App calling `POST /sessions` more than once per automation sequence for the same profile

**Phase to address:** Sessions-and-warm-pool phase

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| In-memory `running` dict for profile state | Simple, fast, no external dependencies | Lost on restart; requires full re-warm on every deploy | Never in production without a startup-recovery path |
| Application-level check-then-insert for idempotency | Readable code | Race condition under concurrent load | Never — use DB UNIQUE constraint + upsert always |
| Token in querystring for viewer URL | Easy iframe `src` attribute | Logged by every proxy; leaked via Referer | Never for auth tokens; use fragment or header |
| `SameSite=Lax` default on admin cookie | Browser default | Insufficient protection when iframe is embedded on the same origin | Never when iframes are in play — use Strict |
| No launch concurrency cap | Simple implementation | Thundering herd on restart exhausts memory | Acceptable for single profile at a time; never for 20 concurrent |

---

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| CloakBrowser binary | Pull latest in Docker build | Pin to a specific version SHA; test fingerprint outputs before upgrading |
| KasmVNC + noVNC | Assume noVNC version is stable | Pin noVNC version; hard-code extension message type whitelist is fragile on upgrade |
| Playwright `launchPersistentContext` | Trust return value as proof of successful launch | Probe `about:blank` after launch; check for SingletonLock leftovers before launch |
| SQLite under asyncio | Use standard `sqlite3` module | Use `aiosqlite` or run DB calls in a thread pool; raw `sqlite3` blocks the event loop |
| Docker volume mounts | Let Docker create volume directory as root | Explicitly `chown` profile dirs to Chrome UID in entrypoint before starting service |

---

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Launching all profiles simultaneously on restart | Memory spike to >80%, OOM kills | asyncio Semaphore(3) on launch slot | >5 simultaneous wakes on a 16GB host |
| No launch queue — every `POST /sessions` blocks until Chrome is ready | 30s HTTP timeout in Main App | Queue launches, return 202 + poll endpoint or use SSE | At 5+ concurrent wake requests |
| Full `list_profiles()` with N DB queries in the admin UI | Admin UI takes 2s to load at 50+ profiles | JOIN query or batch fetch in database layer | >50 profiles |
| Xvnc log files growing unbounded in `/tmp` | `/tmp` fills disk, new launches fail | Log rotation or fixed log file with O_TRUNC on startup | Months of uptime without a restart |

---

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Viewer token in querystring | Token in every proxy log; Referer header leak to vendor portal analytics | Use URL fragment (`#token=`) or POST-to-cookie exchange |
| No token single-use enforcement | Stolen token replays a full VNC session | Server-side JTI registry; mark token consumed on first WebSocket upgrade |
| Admin cookie without `SameSite=Strict` | Vendor portal iframe can issue authenticated admin API requests | Set `SameSite=Strict; Secure; HttpOnly` on all admin session cookies |
| `clipboard_sync=true` on vendor templates | Main App API key can read OTP codes and session tokens from vendor portal | Default `false`; scope clipboard read to viewer-only auth |
| Raw CDP port bound on 0.0.0.0 | Any process on host can connect to Chrome and exfiltrate session data | Bind CDP to `127.0.0.1` only; proxy through authenticated FastAPI WebSocket endpoint |
| No `frame-ancestors` on viewer response | Vendor portal could iframe the VNC viewer (clickjacking) | Set `Content-Security-Policy: frame-ancestors <Main App origin>` on viewer responses |
| WebRTC enabled in vendor portal profiles | STUN requests reveal Docker host's real public IP, contradicting any geolocation claim | Add `--disable-webrtc` or equivalent to all vendor templates |

---

## "Looks Done But Isn't" Checklist

- [ ] **Warm-pool sleep:** Often missing actual Playwright context close — verify Chrome process is gone (`ps aux | grep chrome`) after idle timeout fires, not just removed from `running` dict
- [ ] **Signed URL minting:** Often missing JTI (JWT ID) field — verify every minted token has a unique `jti` that is stored server-side for revocation
- [ ] **Session persistence:** Often "works" in happy path but fails after SIGKILL — verify by: `docker kill --signal=KILL <container>`, restart, call `POST /sessions`, check cookie state in browser
- [ ] **Idempotency:** Often tested with sequential calls only — verify with 10 simultaneous `POST /sessions` requests for the same `(vendor_type, vendor_connection_id)` and assert exactly one profile row and one Chrome process result
- [ ] **CSP frame-ancestors:** Often set on the HTML page but not on WebSocket upgrade responses — verify CSP is present on the initial HTTP response for the viewer endpoint
- [ ] **Admin CSRF:** Often no protection because "it's internal" — verify that a fetch from the viewer iframe origin to `/admin/profiles` returns 403 without a valid CSRF token
- [ ] **Xvnc cleanup:** Often only kills the main PID — verify `pgrep -a Xvnc` returns nothing after profile stop, not just that the specific PID is gone

---

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| SingletonLock corruption | LOW | `find /data/profiles -name "Singleton*" -delete`; restart affected profile |
| Duplicate profile rows from race condition | MEDIUM | Stop both processes; delete duplicate row (keep lower ID); clean up orphan profile directory |
| All profiles sleeping after restart | LOW | `POST /sessions` for each; stagger calls with 3s delay between groups of 3 |
| Viewer token stolen and replayed | MEDIUM | Revoke token in JTI registry; sleep and re-wake the profile (new CDP URL + new tokens) |
| Profile directory corrupted (Cookies DB) | HIGH | Delete `Default/Cookies`, `Default/Cookies-journal`; profile will need to re-authenticate |
| UID mismatch on volume after host migration | MEDIUM | `docker exec -u root <container> chown -R 1000:1000 /data/profiles` |

---

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| SingletonLock on unclean shutdown | Sessions-and-warm-pool | Integration test: SIGKILL container, restart, POST /sessions, verify cookies intact |
| Duplicate profiles from concurrent POST | Sessions-and-warm-pool | Load test: 10 simultaneous POST /sessions, assert 1 profile row |
| Idle detection false-positive | Sessions-and-warm-pool | Test: 90s automation pause, verify profile stays alive |
| Thundering herd on restart | Sessions-and-warm-pool | Test: stop service, POST 15 simultaneous /sessions, measure peak memory |
| Viewer token in querystring | Viewer-and-signed-URL | Code review: assert token is in URL fragment, not `?token=` querystring |
| Token replay | Viewer-and-signed-URL | Test: open viewer URL twice, second open should fail with 401 |
| Fingerprint inconsistency on wake | Template-and-schema phase + Sessions-and-warm-pool | Test: sleep profile, update CloakBrowser binary, wake, compare fingerprint probe output |
| CDP URL without expiry or scope | Sessions-and-warm-pool | Code review: CDP proxy requires per-request auth; old tokens rejected |
| Admin CSRF via viewer iframe | Viewer-and-signed-URL | Penetration test: fetch /admin/ from iframe context, assert 403 |
| Docker UID mismatch | Template-and-schema phase | Test: recreate container, POST /sessions, verify Cookies mtime updated after stop |
| Clipboard credential leak | Template-and-schema phase | Code review: clipboard_sync default=false; Main App API key blocked from clipboard endpoint |
| Zombie Xvnc processes | Sessions-and-warm-pool | Test: force Chrome crash mid-launch, assert Xvnc count matches running count |
| Silent wake failure | Sessions-and-warm-pool | Test: POST /sessions after Chrome force-crash, assert 503 with clear error |

---

## Sources

- Playwright GitHub issue #35466: persistent context cookie corruption and SingletonLock (2025) — https://github.com/microsoft/playwright/issues/35466
- Playwright GitHub issue #31849: closing all contexts disconnects the browser — https://github.com/microsoft/playwright/issues/31849
- Puppeteer zombie processes and memory leaks (6 months in production, 2026) — https://medium.com/@TheTechDude/puppeteer-memory-leaks-crashes-and-zombie-processes-6-months-of-screenshots-in-production-b2ae7e65df3f
- Browserless.io: 5 million headless sessions/week observations — https://www.browserless.io/blog/observations-running-more-than-5-million-headless-sessions-a-week
- TLS fingerprinting (JA3/JA4) for headless browser detection — https://www.browserless.io/blog/tls-fingerprinting-explanation-detection-and-bypassing-it-in-playwright-and-puppeteer
- Browser fingerprint strategy (identity design, not rotation) — https://scrapingant.com/blog/blog/browser-fingerprint-strategy-designing-identities-not-just
- JWT security best practices 2025 (token-in-querystring logging) — https://curity.io/resources/learn/jwt-best-practices/
- SQLite concurrent writes and "database is locked" errors — https://tenthousandmeters.com/blog/sqlite-concurrent-writes-and-database-is-locked-errors/
- Docker volume UID mismatch resolution — https://eastondev.com/blog/en/posts/dev/20251217-docker-mount-permissions-guide/
- FastAPI CSRF protection — https://www.stackhawk.com/blog/csrf-protection-in-fastapi/
- noVNC Browser-in-the-Browser phishing via iframe — https://bleekseeks.com/blog/novnc-and-browser-in-the-browser-phishing-attack-pocexplained
- Thundering herd problem causes and solutions — https://blog.carbonteq.com/the-thundering-herd-problem-causes-effects-and-solutions/
- Existing codebase concerns audit (2026-04-22) — `.planning/codebase/CONCERNS.md`

---
*Pitfalls research for: warm-pool headless-browser service with signed-iframe viewer and vendor-portal automation*
*Researched: 2026-04-22*
