---
phase: 01-schema-templates-and-security-foundations
plan: 02
subsystem: infra
tags: [docker, entrypoint, env-vars, bash, compose, gitignore]

# Dependency graph
requires:
  - phase: 01-schema-templates-and-security-foundations
    provides: phase context, env-var inventory (CLAUDE.md), Pitfall 10 finding
provides:
  - chown step in entrypoint.sh that loud-fails on UID-mismatched /data/profiles
  - docker-compose.yml environment block declaring all 7 new env vars alongside existing AUTH_TOKEN
  - .env.example runbook documenting every env var with placeholder values
  - .env entry in .gitignore so operator copies don't leak into git
affects: [01-03 (fail-closed startup check reads these env vars), 02-* (sessions API consumes MAIN_APP_API_KEY), 03-* (viewer endpoints consume VIEWER_SECRET / MAIN_APP_ORIGIN / VIEWER_TOKEN_TTL_SECS)]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Empty-string fallback (${VAR:-}) for required secrets so missing env triggers fail-closed in startup check"
    - "Numeric defaults (${VAR:-600}, ${VAR:-300}, ${VAR:-0}) for optional config knobs"
    - "Tracked .env.example with obviously-placeholder values (change-me-...) as the operator runbook"

key-files:
  created:
    - .env.example
  modified:
    - entrypoint.sh
    - docker-compose.yml
    - .gitignore

key-decisions:
  - "chown runs before all stale-process / Singleton cleanup so subsequent rm/find/pkill operations on /data/profiles inherit correct ownership"
  - "No || true tail on chown; set -e aborts startup loudly if the volume is not chown-able (e.g., the future USER 1000 flip)"
  - ".env was missing from .gitignore — appended it as part of Task 3 (Rule 2: missing critical security control before secrets land in production .env files)"
  - "DEV_MODE uses empty-string fallback (not 0) so unset → falsy in the startup check; .env.example sets DEV_MODE=0 explicitly for clarity"
  - "MAIN_APP_ORIGIN sample value is http://localhost:3000 (Main App default) so devs can run end-to-end without editing the file"

patterns-established:
  - "Pattern: Required secrets in compose use ${VAR:-} (empty-string fallback) to feed fail-closed startup checks"
  - "Pattern: Operator-facing env-var documentation lives in tracked .env.example with section dividers and one-line comments per var"
  - "Pattern: entrypoint.sh runs ownership fix BEFORE any read/write/delete operation on the data volume"

requirements-completed: [OPS-03, OPS-04]

# Metrics
duration: 2m23s
completed: 2026-05-08
---

# Phase 01 Plan 02: Docker Entrypoint chown Fix and Env-Var Scaffolding Summary

**Docker entrypoint chown -R /data/profiles inserted before stale-process kill; docker-compose declares 7 new env vars (MAIN_APP_API_KEY, VIEWER_SECRET, MAIN_APP_ORIGIN, IDLE_TIMEOUT_SECONDS, VIEWER_TOKEN_TTL_SECS, CHROME_UID, DEV_MODE) with empty-string / numeric fallbacks; new .env.example runbook ships with placeholder secrets and `.env` added to .gitignore.**

## Performance

- **Duration:** 2m23s
- **Started:** 2026-05-08T04:59:34Z
- **Completed:** 2026-05-08T05:01:57Z
- **Tasks:** 3
- **Files modified:** 4 (1 created, 3 modified)

## Accomplishments
- Closed OPS-04 / Pitfall 10: Chromium cookie-flush failures from UID-mismatched volume mounts will now loud-fail at container startup instead of silently corrupting profile state.
- Pre-declared every env var Plan 03's fail-closed startup check will read, with the correct fallback semantics (empty string for required secrets → triggers fail-closed; numeric defaults for optional knobs).
- Gave operators a single tracked `.env.example` runbook so a `cp .env.example .env` is the canonical first step; placeholder values are obvious (`change-me-...`) so an unedited copy still trips the fail-closed check.

## Task Commits

Each task was committed atomically:

1. **Task 1: Insert chown step into entrypoint.sh between mkdir and pkill** — `22fa245` (fix)
2. **Task 2: Extend docker-compose.yml environment block with new env var declarations** — `a1e4a27` (feat)
3. **Task 3: Create .env.example at repo root documenting every env var** — `306c85b` (feat, also adds `.env` to .gitignore)

_No final metadata commit yet — orchestrator commits SUMMARY.md after this worktree merges back._

## Files Created/Modified
- `entrypoint.sh` — Added 4 lines (2 comment, 1 blank, 1 chown) between `mkdir -p /data/profiles` and the first `pkill`. No existing line touched.
- `docker-compose.yml` — Added 7 env-var declarations under the existing `environment:` key, preserving AUTH_TOKEN as the first entry; service/build/ports/volumes blocks untouched.
- `.env.example` — New file at repo root: 8 env-var assignments grouped by 6 section dividers (admin, machine auth, viewer signing, viewer origin/TTL, warm-pool, runtime UID, dev-mode), each with a one-line comment.
- `.gitignore` — Appended `# Local environment` block with `.env` (NOT `.env.example`) under the existing categorized rules.

## Decisions Made
- **chown placement:** Immediately after `mkdir -p /data/profiles` and before the first `pkill` so any subsequent file operation on the volume runs with the correct ownership; matches the placement spec in `01-PATTERNS.md`.
- **No error swallowing on chown:** Plan explicitly forbids `|| true` / `2>/dev/null` on the chown line — this is the loud-failure design so the future USER 1000 flip cannot silently break Chromium cookie persistence.
- **DEV_MODE fallback:** `${DEV_MODE:-}` (empty string) rather than `${DEV_MODE:-0}` so the fail-closed check in Plan 03 can treat unset and "0" identically as falsy without reparsing.
- **MAIN_APP_ORIGIN placeholder:** Used `http://localhost:3000` (concrete dev default) instead of a `change-me-...` value because empty-or-bad origins must be caught by the CSP `frame-ancestors` validation in Plan 03 anyway.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 — Missing Critical Security Control] Append `.env` to .gitignore**
- **Found during:** Task 3 (creating .env.example)
- **Issue:** Plan threat model T-01-12 assumes `.env` is git-ignored ("pre-existing .gitignore rule assumed"). The actual `.gitignore` had no `.env` entry — operators following the runbook (`cp .env.example .env`) would create a file that `git add .` could capture, leaking real `MAIN_APP_API_KEY` / `VIEWER_SECRET` values.
- **Fix:** Appended a `# Local environment` block to `.gitignore` listing `.env` only. Did NOT add `.env.example` (it must remain tracked per the plan's `must_haves`).
- **Files modified:** .gitignore
- **Verification:** `grep -E '^\.env$' .gitignore` returns one match; `grep -E '^\.env\.example$' .gitignore` returns nothing.
- **Committed in:** 306c85b (Task 3 commit)

---

**Total deviations:** 1 auto-fixed (1 missing critical security control)
**Impact on plan:** Necessary to satisfy T-01-12 disposition. Plan's instruction in Task 3 explicitly anticipated this case ("if not, append `.env` to .gitignore"); fix tracked here for traceability. No scope creep.

## Issues Encountered

- `python3 -c "import yaml; ..."` failed in the worktree's PATH (no PyYAML in `~/.pyenv/shims/python` env). Used `docker compose config` instead, which validated the YAML and confirmed all 8 env vars are exposed correctly with the expected fallback values. Acceptance criteria are equivalently satisfied — the Python YAML parse was an alternate gate, not the primary one.

## User Setup Required

None — the only operator action is the existing convention of `cp .env.example .env` and filling production-ready values for `MAIN_APP_API_KEY`, `VIEWER_SECRET`, and `MAIN_APP_ORIGIN`. The fail-closed startup check that enforces this lands in Plan 03.

## Next Phase Readiness

- `entrypoint.sh` is ready for the Plan 03 follow-on (fail-closed env validation will run inside `backend/main.py` / startup hooks; entrypoint changes are complete for v1).
- `docker-compose.yml` exposes the entire env-var surface that Plan 03's startup check will read from `os.environ`. No further compose edits needed.
- `.env.example` placeholder values are intentionally non-functional so Plan 03's fail-closed check (Rule: empty string → refuse to start) trips on a verbatim copy. If Plan 03 adds a stronger "is this a placeholder?" check, it can grep for `change-me-` as a fast heuristic.
- No blockers for downstream waves.

## Self-Check: PASSED

Verified files exist:
- entrypoint.sh: FOUND (chown line at correct position, set -e preserved, no `|| true`)
- docker-compose.yml: FOUND (8 env entries verified by `docker compose config`)
- .env.example: FOUND (8 assignments, 6 section dividers, placeholder secrets)
- .gitignore: FOUND (.env listed, .env.example NOT listed)

Verified commits exist on this branch:
- 22fa245 (Task 1): FOUND
- a1e4a27 (Task 2): FOUND
- 306c85b (Task 3): FOUND

Plan-level verification block all green:
- `bash -n entrypoint.sh && test -f .env.example` → FILES_OK
- `grep -E '^[A-Z_]+=' .env.example | sort | uniq | wc -l` → 8
- `awk` ordering check on entrypoint.sh → ORDER_OK

---
*Phase: 01-schema-templates-and-security-foundations*
*Plan: 02*
*Completed: 2026-05-08*
