---
phase: 02-sessions-warm-pool-and-cdp-lifecycle
plan: 09
subsystem: testing
tags: [pytest, e2e, slow-marker]
provides:
  - slow-marked warm-pool E2E tests (skipped in default CI)
affects: []
requirements-completed: [SESS-12, SESS-03]
duration: 15min
completed: 2026-05-19
---

# Phase 2 Plan 09: Warm-Pool E2E Summary

**Slow pytest layer for real-Chromium sleep/wake persistence; default runs deselect 2 tests.**

## Task Commits
1. **E2E tests + pyproject marker** - `768be37`

## Deviations from Plan
None. E2E tests skip when cloakbrowser mock is active (typical dev/CI).
