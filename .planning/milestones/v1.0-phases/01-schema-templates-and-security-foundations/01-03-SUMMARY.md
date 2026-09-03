---
phase: 01-schema-templates-and-security-foundations
plan: 03
subsystem: security
tags: [security, fail-closed, lifespan, env-check, sec-06, d-17]

requires:
  - phase: 01-schema-templates-and-security-foundations
    provides: existing FastAPI lifespan, AUTH_TOKEN env-read pattern, logger setup
provides:
  - Module-level reads for VIEWER_SECRET, MAIN_APP_API_KEY, DEV_MODE in backend/main.py
  - _check_required_env() helper that fails-closed in production and warns in DEV_MODE
  - lifespan integration: helper runs as the FIRST line, before db.init_db()
  - DEV_MODE parser limited to 1/true/yes (case-insensitive, whitespace-trimmed)
affects:
  - 01-04 (machine API-key auth — relies on MAIN_APP_API_KEY presence)
  - 02 (sessions, warm-pool — runs only when MAIN_APP_API_KEY is set)
  - 03 (signed viewer URLs — relies on VIEWER_SECRET presence and HMAC signing)

tech-stack:
  added: []  # No new libraries — pure stdlib (os, logging, RuntimeError)
  patterns:
    - "Fail-closed startup boundary: secrets validated in lifespan before db.init_db() so uvicorn never accepts traffic with missing config"
    - "Explicit DEV_MODE escape hatch: opt-in via 1/true/yes ONLY, no truthy-fuzzy matching"
    - "Import-safe env check: helper called at lifespan, not at import — keeps unit tests importable without DEV_MODE shimming"

key-files:
  created: []
  modified:
    - backend/main.py — VIEWER_SECRET/MAIN_APP_API_KEY/DEV_MODE module reads, _check_required_env(), lifespan integration

key-decisions:
  - "Fail-closed check lives only in lifespan; no belt-and-suspenders import-time raise (CONTEXT.md A6 / Pitfall 5). Keeps `from backend.main import app` usable in tests without DEV_MODE shimming."
  - "DEV_MODE parser whitelists exactly {1, true, yes} after strip+lower; everything else (0, false, empty, unset, anything-else) is production. Avoids accidental bypass via 'falsey-truthy' values like the literal string '0'."
  - "Whitespace-only secret values are treated as missing (.strip() check on the value, not just truthiness). Prevents accidental bypass via env-file artifacts like VIEWER_SECRET=' '."

patterns-established:
  - "Pattern: env-validation helpers live next to their env reads at module top, not in a separate config module — colocation matches the existing AUTH_TOKEN read style."
  - "Pattern: dev-mode warning copy explicitly names the missing variables in the WARNING line so operators can act without cross-referencing source."
  - "Pattern: RuntimeError message points operator at the escape hatch (DEV_MODE=1) without endorsing it for production."

requirements-completed: [SEC-06]

duration: 2min
completed: 2026-05-08
---

# Phase 01 Plan 03: Fail-Closed Startup Check Summary

**RuntimeError-on-missing-secret guard wired into the FastAPI lifespan: service refuses to bind a port unless VIEWER_SECRET and MAIN_APP_API_KEY are both set, with DEV_MODE=1 as the explicit local-dev escape hatch.**

## Performance

- **Duration:** ~2 min
- **Started:** 2026-05-08T04:59:39Z
- **Completed:** 2026-05-08T05:01:30Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments

- Closed SEC-06 at the startup boundary: no machine route (Phase 2) or viewer route (Phase 3) can ever execute without secrets configured, because uvicorn never reaches the request-handling state when lifespan raises.
- Added DEV_MODE escape hatch with strict whitelist parsing — case-insensitive, whitespace-trimmed, accepts only `1`/`true`/`yes`. Avoids the `bool("0") is True` Python pitfall.
- Preserved every existing lifespan behavior: db.init_db(), browser_mgr.cleanup_stale(), startup log, shutdown cleanup_all() — only added the guard call as the new first line.
- Module remains importable with no env vars set, so unit tests using `from backend.main import app` (or any module-level reference) do not need DEV_MODE shimming in conftest.

## Task Commits

Each task was committed atomically:

1. **Task 1: Add module-level env reads and _check_required_env() to backend/main.py** — `e390452` (feat)

_No final metadata commit in worktree mode — orchestrator owns the SUMMARY.md commit after all wave-1 agents complete._

## Files Created/Modified

- `backend/main.py` — Added module-level reads (VIEWER_SECRET, MAIN_APP_API_KEY, DEV_MODE), the `_DEV_MODE_WARNING` copy, the `_check_required_env()` helper at line 66, and the `_check_required_env()` call as the first line of `lifespan` at line 411 (before `db.init_db()`).

## Decisions Made

None beyond the locked decisions in the plan. All three "Claude's Discretion" items in 01-CONTEXT.md were resolved as the plan prescribed:

- **A6 (import-time second check):** Skipped (lifespan-only). Documented in plan action #3.
- **DEV_MODE parser shape:** Used the prescribed whitelist `{1, true, yes}` after strip+lower.
- **Warning copy:** Used the exact `⚠ DEV_MODE=1: VIEWER_SECRET and/or MAIN_APP_API_KEY not set. Authentication is bypassed. Do not use in production.` string from the plan, augmented with a second `Missing in dev mode: <names>` log line.

## Deviations from Plan

None — plan executed exactly as written.

## Verification

The plan's embedded Python script could not run via `import backend.main` because the project's runtime dependency `cloakbrowser` is not installed in the local Python environment (pre-existing — Docker is the canonical run target; no `.venv` ships with the repo). To verify the actual code under test, the verification logic was run by AST-extracting the env reads + `_check_required_env` definition from `backend/main.py` and exec'ing them into a synthetic module, then exercising every behavior the plan specified:

| Test | Input | Expected | Result |
|------|-------|----------|--------|
| 1 | both unset, DEV_MODE=False | `RuntimeError` naming both vars + DEV_MODE=1 | PASS |
| 2 | both set, DEV_MODE=False | returns None, no log | PASS |
| 3 | VIEWER_SECRET="   " (whitespace), DEV_MODE=False | RuntimeError | PASS |
| 4 | both unset, DEV_MODE=True | WARNING with DEV_MODE=1 + missing var names, no raise | PASS |
| 5 | DEV_MODE parsing table (`1`/`true`/`TRUE`/`Yes`/`yes`/`  1  ` → True; `0`/`false`/empty/`no`/`anything` → False) | as expected | PASS |
| 6 | one missing in DEV_MODE | WARNING names only the actually-missing var | PASS |

Additional structural checks:

- All 11 grep-based acceptance criteria pass (function defined exactly once, raise present, three module reads each present once, two `_check_required_env` occurrences total — definition + lifespan call, two `DEV_MODE=1` mentions in the file, AuthMiddleware/`_AUTH_EXEMPT` counts unchanged from baseline of 2).
- `awk` line-order check confirms `_check_required_env()` call appears AFTER `async def lifespan` and BEFORE `db.init_db()` inside the lifespan body.
- AST scan confirms there is no module-level call to `_check_required_env()`, so importing the module (when its other dependencies are installed) cannot trigger the raise — the check is reached only when uvicorn enters the lifespan context.

## Issues Encountered

- **Worktree was not based on the orchestrator's expected commit `7396814`.** The branch HEAD started at the older `bd15b06`. Resolved per the worktree_branch_check protocol with a `git reset --hard 7396814`. No work lost (worktree had no commits yet).
- **Plan + 01-PATTERNS.md were not present in the worktree** — they exist as untracked files in main but were never committed. Copied them into the worktree's `.planning/phases/01-…/` directory so the executor could read them. They remain untracked at the end of the run; not committed by this agent because they are out of scope for plan 01-03 (their commit is the orchestrator's responsibility or a separate planning commit).
- **Local Python environment lacks `cloakbrowser`**, so `python -c "import backend.main"` raises `ModuleNotFoundError`. Worked around by AST-extracting the relevant top-level statements and `_check_required_env` from `backend/main.py` and exec'ing them into a synthetic module — this validates the actual production code rather than a hand-rolled copy. All six test cases pass against the real source.

## User Setup Required

None — no external service configuration required for this plan. Operators must set `MAIN_APP_API_KEY` and `VIEWER_SECRET` in production (or `DEV_MODE=1` for local dev), but those are documented in the project root `CLAUDE.md` and were already part of the milestone's env contract.

## Next Phase Readiness

- **01-04 (or whichever plan adds APIKeyHeader on `/sessions/*`):** Ready. `MAIN_APP_API_KEY` is guaranteed non-blank by the time any route handler runs, so the header check can be a simple `hmac.compare_digest`.
- **Phase 2 / Phase 3:** Both can rely on `VIEWER_SECRET` and `MAIN_APP_API_KEY` being present at runtime. No additional defensive checks needed in the route handlers themselves.
- **No blockers.**

## Self-Check: PASSED

Verified before returning:

- `backend/main.py` modified — `git show --stat HEAD` lists `1 file changed, 38 insertions(+)`.
- Commit `e390452` exists in `git log --oneline`.
- SUMMARY.md exists at `.planning/phases/01-schema-templates-and-security-foundations/01-03-SUMMARY.md`.
- All 11 grep-based acceptance criteria from the plan pass.
- All 6 behavioral test cases from the plan's verification block pass.
- Line-order awk check passes.
- AST scan confirms no top-level `_check_required_env()` call.

---
*Phase: 01-schema-templates-and-security-foundations*
*Plan: 03*
*Completed: 2026-05-08*
