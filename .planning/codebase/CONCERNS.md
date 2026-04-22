# Codebase Concerns

**Analysis Date:** 2026-04-22

## Security Considerations

**WebSocket Origin Validation:**
- Issue: CSWSH (Cross-Site WebSocket Hijacking) protection implemented but depends on Origin header presence
- Files: `backend/main.py` (lines 89-136)
- Impact: Non-browser clients (Playwright, curl) bypass origin checks because they don't send Origin headers — by design
- Current mitigation: Origin validation for browser clients, but design assumes non-browser clients are trusted (internal API consumption)
- Recommendations: Document this trust boundary clearly; ensure FastAPI auth middleware is the primary defense for external access

**Authentication via Environment Variable:**
- Issue: `AUTH_TOKEN` stored in environment; if exposed, provides single credentials for all routes
- Files: `backend/main.py` (line 51)
- Impact: Auth token stored in plain environment variable; container-based deployment mitigates some risk
- Current mitigation: Token is optional; auth-disabled mode for local dev
- Recommendations: Consider supporting OAuth/JWT for production; hash token comparisons use `hmac.compare_digest()` which is correct

**RFB Protocol Filtering Complexity:**
- Issue: Custom RFB message parser to strip unsupported encoding types sent by noVNC to KasmVNC
- Files: `backend/main.py` (lines 230-369)
- Impact: Complex binary protocol parsing with hard-coded message sizes and extension types; if sizes are wrong, message boundaries desynchronize and entire VNC stream breaks
- Current mitigation: Extensive logging and fallback drop-on-unknown
- Recommendations: Consider using a tested RFB parsing library instead of custom implementation; thorough fuzzing of concatenated message batches

**Clipboard Text Truncation:**
- Issue: Clipboard reads capped at 1MB via `_CLIPBOARD_MAX_READ`
- Files: `backend/main.py` (line 577, 636)
- Impact: Large clipboard contents silently truncated without error indication
- Current mitigation: 1MB cap is practical limit for most use cases
- Recommendations: Return error status if clipboard exceeds limit; client should see warning

**xclip Process Lifecycle:**
- Issue: xclip processes for clipboard operations persist to serve paste requests but may leak if not terminated
- Files: `backend/main.py` (lines 579-611)
- Impact: xclip process killed only when new clipboard content is pushed; orphaned processes accumulate if profile stops unexpectedly
- Current mitigation: Old process is killed before new one starts
- Recommendations: Add explicit cleanup on profile stop to terminate lingering xclip processes

---

## Performance Bottlenecks

**Single-threaded Profile Cleanup:**
- Issue: `cleanup_stale()` uses blocking `subprocess.run()` with pkill to find orphan Xvnc processes
- Files: `backend/vnc_manager.py` (lines 119-129)
- Impact: Runs at startup and may block event loop if many orphan processes exist or pkill hangs
- Current mitigation: Wrapped in try/except for FileNotFoundError
- Recommendations: Move to async subprocess call or run in thread pool; consider cgroup/namespace cleanup instead of pkill

**RFB Message Rewriting on Every Frame:**
- Issue: Every client→server RFB message is parsed and potentially rewritten (SetEncodings filtered, PointerEvent expanded)
- Files: `backend/main.py` (lines 330-369)
- Impact: Linear scan of message boundaries in each WebSocket frame; SetEncodings rewrite allocates new bytearray
- Current mitigation: Only non-standard types are rewritten; most frames are pass-through
- Recommendations: Profile CPU usage under heavy mouse/keyboard input; consider caching encoding whitelist in client

**Large Profile Dataset (N profiles → N database queries):**
- Issue: `list_profiles()` fetches all profiles then iterates N times to get tags
- Files: `backend/database.py` (lines 151-164)
- Impact: For 100+ profiles, one SELECT + N SELECT queries per list; no pagination
- Current mitigation: SQLite in-process, fast enough for typical deployments
- Recommendations: Implement JOIN to fetch tags in single query; add pagination for future scaling

---

## Fragile Areas

**Browser Launch Error Recovery:**
- Issue: If VNC starts but Chrome launch fails, display is allocated but may not fully release
- Files: `backend/browser_manager.py` (lines 164-288)
- Impact: Partial failure leaves Xvnc running; subsequent launch attempts skip that display number
- Current mitigation: Exception handler calls `vnc.stop_vnc()` and re-raises
- Recommended improvement: Add timeout or explicit state validation after launch to catch partial failures

**Clipboard Init Script Evaluation:**
- Issue: If clipboard init script fails on existing pages, error is logged but silently swallowed
- Files: `backend/browser_manager.py` (lines 252-257)
- Impact: Clipboard capturing may not work for pre-existing tabs (e.g., about:blank)
- Current mitigation: Script is injected via `add_init_script()` for future pages
- Recommended fix: Ensure script is added before any pages navigate

**Profile Deletion Race Condition:**
- Issue: Database delete succeeds, then filesystem cleanup uses `ignore_errors=True` on `shutil.rmtree()`
- Files: `backend/main.py` (lines 493-512)
- Impact: If disk cleanup fails silently, orphaned profile directories accumulate
- Current mitigation: DB is transactional; filesystem cleanup is last step
- Recommended fix: Log failures explicitly; consider deferring disk cleanup to background task with retry

**Type Ignore Comments:**
- Issue: Multiple `# type: ignore` comments for Playwright subprocess stdin operations
- Files: `backend/main.py` (lines 605-607)
- Impact: Type checker bypassed; actual type is union that could be None
- Current mitigation: Code validates `proc` returns a valid subprocess
- Recommended fix: Explicitly assert `proc.stdin is not None` instead of ignoring type

**Frontend Form State Coherence:**
- Issue: `ProfileForm.tsx` has no validation that conflicting settings (e.g., `humanize=false` but `human_preset=careful`) are consistent
- Files: `frontend/src/components/ProfileForm.tsx`
- Impact: Frontend allows nonsensical profile states; backend does no validation
- Current mitigation: Defaults are sensible; form hides `human_preset` when `humanize=false`
- Recommended fix: Add backend validation to reject `human_preset` when `humanize` is false

---

## Test Coverage Gaps

**WebSocket Origin Validation:**
- What's not tested: Full CSWSH attack scenario (spoofed Origin header on cross-origin request)
- Files: `backend/main.py` (lines 89-136)
- Risk: Regression in origin checking could allow cross-origin VNC hijacking
- Priority: High

**RFB Message Filtering:**
- What's not tested: Concatenated frames with multiple unknown message types; boundary cases (incomplete messages)
- Files: `backend/main.py` (lines 330-369)
- Risk: Message desynchronization causes VNC stream to become unusable; hard to debug
- Priority: High

**Clipboard Encoding Edges:**
- What's not tested: Non-UTF-8 clipboard content; characters outside Latin-1 range
- Files: `backend/main.py` (lines 217-224, 663)
- Risk: Silent data corruption or decode errors in clipboard relay
- Priority: Medium

**Profile Lifecycle Under Stress:**
- What's not tested: Rapid launch/stop cycles; OOM conditions during profile launch
- Files: `backend/browser_manager.py`
- Risk: Resource leaks or orphaned processes under heavy load
- Priority: Medium

**Frontend Auth Flow:**
- What's not tested: Token refresh on 401 during long-lived session
- Files: `frontend/src/lib/api.ts` (line 98-100)
- Risk: User gets stuck on login page if token expires mid-session
- Priority: Low

---

## Known Bugs / Workarounds

**NoVNC Extension Messages Breaking KasmVNC:**
- Symptoms: VNC stream disconnects with "unknown message type" error
- Cause: noVNC 1.4+ sends ExtensionMessages (types 150, 248, 252, 255) that KasmVNC 1.3.3 doesn't recognize
- Workaround: Custom RFB filter strips extension types and rewrites PointerEvents (lines 230-369 in `main.py`)
- Note: Extension type sizes are hard-coded; any change to noVNC protocol requires update

**Chrome Native Copy Not Captured:**
- Symptoms: User copies text via native Chrome menu or Ctrl+C in web app, clipboard endpoint returns empty
- Cause: Chrome doesn't write to X11 clipboard; only DOM copy events trigger `window.__clipboardText`
- Workaround: Fallback to `xclip` for non-Chrome clipboard owners (lines 643-664 in `main.py`)
- Note: This is a fundamental limitation of VNC + headless Chrome; workaround is best effort

**Xvnc Log File Not Cleaned Up:**
- Symptoms: `/tmp/xvnc-{display}.log` files accumulate after container restarts
- Cause: No log rotation; files only removed by manual cleanup
- Impact: /tmp disk usage grows unbounded in long-running containers
- Recommendations: Implement log rotation or clear on startup

---

## Scaling Limits

**Display Number Space:**
- Current capacity: 900 profiles (displays 100–999 to avoid 2-digit displays)
- Limit: Hard-coded `BASE_DISPLAY = 100`, no wrapping
- Scaling path: Implement display number recycling or use unallocated ranges above 1000

**WebSocket Proxy Memory:**
- Current capacity: Each VNC connection keeps WebSocket frame buffers in memory
- Limit: `max_size=None` in websockets library means unbounded frame sizes (but RFB frames are typically <10MB)
- Scaling path: Add configurable frame size limit or implement frame chunking

**Database Connections:**
- Current capacity: SQLite with no connection pooling (one-off connections per operation)
- Limit: Concurrent requests scale linearly; write lock contention on busy databases
- Scaling path: Migrate to PostgreSQL for production multi-instance deployments

---

## Dependencies at Risk

**KasmVNC 1.3.3:**
- Risk: No longer actively developed; security fixes may not be available
- Impact: Upgrade path to newer VNC server requires testing RFB filtering logic
- Migration plan: Consider modern VNC alternatives like TigerVNC or Wayvnc; validate RFB compatibility

**noVNC Version Lock:**
- Risk: Frontend depends on specific noVNC version for extension message types
- Impact: Upgrading noVNC may introduce new extension types not in hard-coded whitelist
- Migration plan: Monitor noVNC releases; test with latest before upgrade

**CloakBrowser Binary Dependency:**
- Risk: Pre-built Chromium binary downloaded at Docker build; no checksum verification visible
- Impact: Corrupted or malicious binary could compromise all profiles
- Recommendations: Verify binary checksums; consider source-based build for sensitive deployments

---

## Architectural Concerns

**Tight Coupling of RFB Filtering to VNC Proxy:**
- Issue: Message type sizes and filtering logic are hard-coded in `main.py` VNC proxy
- Files: `backend/main.py` (lines 235-271)
- Impact: Changes to RFB protocol require modifying application code, not configuration
- Recommendation: Extract RFB codec into separate module or configuration file

**Mixed Responsibilities in `main.py`:**
- Issue: 1000+ lines combining API routing, auth, RFB filtering, VNC proxying, CDP proxying
- Files: `backend/main.py`
- Impact: Hard to test individual concerns; large surface area for bugs
- Recommendation: Split into `routes/`, `auth.py`, `rfb_filter.py`, `proxies.py` modules

**Profile State Machine Not Explicit:**
- Issue: Profile has implicit states (stopped, launching, running) tracked across multiple data structures
- Files: `backend/browser_manager.py` (lines 159-171)
- Impact: Race conditions possible if states get out of sync; no single source of truth
- Recommendation: Use explicit state machine (e.g., Enum) with state transition validation

---

## Missing Critical Features

**Profile Duplication:**
- Problem: No way to clone a profile; users must manually re-enter all settings
- Impact: High friction for creating variants (e.g., "Amazon Seller #1" → "Amazon Seller #2")
- Recommendation: Add POST `/api/profiles/{id}/clone` endpoint

**Batch Operations:**
- Problem: No way to launch/stop multiple profiles simultaneously
- Impact: Users must click launch for each profile individually
- Recommendation: Add POST `/api/profiles/launch-batch` with profile ID list

**Profile Templates:**
- Problem: No way to save and reuse custom settings across profiles
- Impact: Setup friction for users with many profiles
- Recommendation: Add `/api/templates` CRUD; allow profiles to inherit from template

**Audit Logging:**
- Problem: No record of who accessed/modified profiles and when
- Impact: Can't investigate unauthorized access or debug accidental changes
- Recommendation: Add audit log table; log all CRUD operations with timestamp and auth context

---

## Environment / Configuration Issues

**AUTH_TOKEN Complexity:**
- Risk: Token stored as plaintext in environment; no rotation mechanism
- Impact: If compromised, attacker has permanent access unless container is redeployed
- Recommendations: 
  - Add token rotation endpoint that updates AUTH_TOKEN
  - Or switch to JWT with short expiration
  - Or use OAuth provider for auth

**Hardcoded System Paths:**
- Risk: `/tmp/xvnc-{display}.log` and `/usr/share/kasmvnc/www` are hard-coded
- Impact: Breaks if container layout changes; no flexibility for alternative VNC servers
- Recommendations: Make configurable via environment variables

**Display Allocation Not Persisted:**
- Issue: Allocated display numbers start fresh at `BASE_DISPLAY` on each restart
- Impact: If container restarts mid-session, Xvnc on old display is orphaned but not reclaimed
- Recommendation: Persist allocation state or scan active displays on startup

---

*Concerns audit: 2026-04-22*
