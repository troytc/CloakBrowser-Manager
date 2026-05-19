"""Warm-pool session orchestrator (Phase 2 keystone).

Sits between routers/sessions.py and BrowserManager. Owns:
- Per-(vendor_type, vendor_connection_id) asyncio.Lock for upsert serialization (D-02)
- _idle_tasks dict keyed by profile_id; one asyncio.Task per profile that
  sleeps IDLE_TIMEOUT_SECONDS then stops the profile under browser_mgr._lock (D-08)

Calls into BrowserManager.launch / _stop_locked only — never spawns Chromium
directly. RunningProfile state lives on BrowserManager.running.

Single-process / single-uvicorn-worker assumption (CONTEXT.md Deferred Ideas).
The cross-process safety net is database.upsert_profile_by_vendor's UNIQUE
constraint + IntegrityError swallow.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import os
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from . import database as db
from .browser_manager import BrowserLaunchError, BrowserManager

if TYPE_CHECKING:
    from .browser_manager import RunningProfile

logger = logging.getLogger("vendorbrowser.session_manager")


# CONTEXT.md D-06: default 600s; env override read at schedule time (not __init__).
_DEFAULT_IDLE_TIMEOUT_SECS = 600


def _idle_timeout_secs() -> int:
    """Read IDLE_TIMEOUT_SECONDS at scheduling time so monkeypatch.setenv
    works in tests (RESEARCH.md open question 3, A5 assumption)."""
    raw = os.environ.get("IDLE_TIMEOUT_SECONDS", str(_DEFAULT_IDLE_TIMEOUT_SECS))
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        logger.warning("Invalid IDLE_TIMEOUT_SECONDS=%r, defaulting to %d", raw, _DEFAULT_IDLE_TIMEOUT_SECS)
        return _DEFAULT_IDLE_TIMEOUT_SECS


@dataclass
class SessionResult:
    """Return shape from get_or_wake — feeds routers/sessions.py POST response."""
    profile_id: str
    cdp_url: str
    state: Literal["running", "idle", "stopped"]
    vnc_viewer_url: str = ""  # Phase 3 wires the signed URL


@dataclass
class SessionStatusEnvelope:
    """Return shape from status_envelope — feeds GET /sessions/{id}."""
    state: Literal["running", "idle", "stopped"]
    cdp_attach_count: int
    viewer_attach_count: int
    idle_expires_at: str | None  # ISO-8601 UTC or None
    last_launched_at: str | None  # ISO-8601 UTC or None


def _isoformat_or_none(dt: datetime.datetime | None) -> str | None:
    return dt.isoformat() if dt is not None else None


def _now_utc() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


class SessionManager:
    """Lifespan singleton — constructed in main.py lifespan, attached to app.state.

    Constructed by FastAPI lifespan (D-01). Routes resolve via Depends(get_session_manager).
    """

    def __init__(self, browser_mgr: BrowserManager) -> None:
        self._browser = browser_mgr
        # Per-key locks for upsert serialization (D-02). _locks_mutex guards
        # the dict mutation; the locks themselves are held briefly inside
        # get_or_wake.
        self._key_locks: dict[tuple[str, str], asyncio.Lock] = {}
        self._locks_mutex = asyncio.Lock()
        # One asyncio.Task per profile_id (D-09).
        self._idle_tasks: dict[str, asyncio.Task[None]] = {}

    # ------------------------------------------------------------------
    # Public surface (routers + WS proxy call into these)
    # ------------------------------------------------------------------

    async def get_or_wake(
        self,
        vendor_type: str,
        vendor_connection_id: str,
    ) -> SessionResult:
        """Idempotent get-or-create-or-wake (SESS-01, SESS-03, SESS-07).

        Sequence:
        1. Acquire per-key lock for (vendor_type, vendor_connection_id).
        2. db.upsert_profile_by_vendor — get/create the profile row.
        3. If browser_mgr.running has the profile_id, return its state.
        4. Otherwise call browser_mgr.launch(profile) (Semaphore + about:blank
           probe inside).
        5. Cancel any pending idle timer for this profile_id (rare edge —
           idle task could be running when a new POST arrives).
        6. Return SessionResult with state=running.

        Raises:
        - database.NoTemplateError (-> 404 in router)
        - BrowserLaunchError (-> 503 in router)
        """
        t0 = time.monotonic()
        key = (vendor_type, vendor_connection_id)
        lock = await self._get_key_lock(key)
        async with lock:
            profile = db.upsert_profile_by_vendor(vendor_type, vendor_connection_id)
            profile_id: str = profile["id"]

            running = self._browser.running.get(profile_id)
            if running is None:
                # Cold path: launch (semaphore + about:blank probe).
                logger.info(
                    "event=upsert_wake vendor_type=%s vendor_connection_id=%s profile_id=%s",
                    vendor_type, vendor_connection_id, profile_id,
                )
                running = await self._browser.launch(profile)
            else:
                logger.debug(
                    "event=upsert_hit vendor_type=%s vendor_connection_id=%s profile_id=%s",
                    vendor_type, vendor_connection_id, profile_id,
                )

            # Cancel any pending idle timer (e.g. brief race between idle
            # scheduling and this POST). on_attach handles the count >= 1 case;
            # this is a belt-and-suspenders cancel for the just-woken case.
            self._cancel_idle(profile_id)

            elapsed_ms = int((time.monotonic() - t0) * 1000)
            logger.info(
                "event=upsert_done vendor_type=%s vendor_connection_id=%s profile_id=%s ms=%d",
                vendor_type, vendor_connection_id, profile_id, elapsed_ms,
            )

            return SessionResult(
                profile_id=profile_id,
                cdp_url=f"/api/profiles/{profile_id}/cdp",  # D-13
                state="running",
                vnc_viewer_url="",  # Phase 3 wires
            )

    def on_attach(self, profile_id: str) -> None:
        """Called from CDP/viewer WS proxy on connect. Cancels any pending
        idle timer (SESS-06, D-09).

        Caller MUST have already incremented the relevant attach count under
        browser_mgr._lock (RESEARCH.md §3 cancel-vs-fire ordering). The count
        mutation BEFORE this call is what makes the defense-in-depth re-check
        in _idle_sleep work.
        """
        self._cancel_idle(profile_id)

    def on_all_detached(self, profile_id: str) -> None:
        """Called from CDP/viewer WS proxy try/finally on disconnect when
        BOTH cdp_attach_count and viewer_attach_count have hit zero (SESS-05).

        Schedules a fresh idle task that sleeps IDLE_TIMEOUT_SECONDS and then
        stops the profile under browser_mgr._lock with a defense-in-depth
        re-check (D-08).
        """
        running = self._browser.running.get(profile_id)
        if running is None:
            # Already stopped; nothing to schedule.
            return

        # Cancel any prior task; only one timer per profile (D-09).
        self._cancel_idle(profile_id)

        delay = _idle_timeout_secs()
        running.idle_started_at = _now_utc()
        task = asyncio.create_task(
            self._idle_sleep(profile_id, delay),
            name=f"idle_sleep:{profile_id}",
        )
        self._idle_tasks[profile_id] = task

    async def shutdown(self) -> None:
        """Cancel all pending idle tasks. Called from main.py lifespan
        BEFORE BrowserManager.cleanup_all so the timers don't try to run
        during cleanup (D-08, RESEARCH.md §8)."""
        tasks = list(self._idle_tasks.values())
        self._idle_tasks.clear()
        for t in tasks:
            if not t.done():
                t.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def status_envelope(self, profile_id: str) -> SessionStatusEnvelope:
        """Compute the GET /sessions/{id} envelope on demand (SESS-13, D-18).

        Caller (router) is responsible for the 404 path: if db.get_profile
        returns None, raise 404 BEFORE calling this. If db has the profile
        but browser_mgr.running does not, state=stopped with zeros.
        """
        running = self._browser.running.get(profile_id)
        idle_task = self._idle_tasks.get(profile_id)

        if running is None:
            return SessionStatusEnvelope(
                state="stopped",
                cdp_attach_count=0,
                viewer_attach_count=0,
                idle_expires_at=None,
                last_launched_at=None,
            )

        has_attach = (running.cdp_attach_count > 0 or running.viewer_attach_count > 0)

        if has_attach:
            state: Literal["running", "idle", "stopped"] = "running"
            idle_expires_at: datetime.datetime | None = None
        elif idle_task is not None and not idle_task.done():
            state = "idle"
            if running.idle_started_at is not None:
                idle_expires_at = running.idle_started_at + datetime.timedelta(
                    seconds=_idle_timeout_secs()
                )
            else:
                idle_expires_at = None
        else:
            # Edge: process alive but no attach yet, no idle task scheduled.
            # Treat as running (the WS proxy hasn't connected yet).
            state = "running"
            idle_expires_at = None

        return SessionStatusEnvelope(
            state=state,
            cdp_attach_count=running.cdp_attach_count,
            viewer_attach_count=running.viewer_attach_count,
            idle_expires_at=_isoformat_or_none(idle_expires_at),
            last_launched_at=_isoformat_or_none(running.last_launched_at),
        )

    def remove_key_lock(self, vendor_type: str, vendor_connection_id: str) -> None:
        """Drop the per-key lock entry. Called by routers/profiles.py DELETE
        handler after the profile row is gone (Claude's discretion in CONTEXT.md
        — prevents unbounded growth)."""
        self._key_locks.pop((vendor_type, vendor_connection_id), None)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get_key_lock(self, key: tuple[str, str]) -> asyncio.Lock:
        """Get-or-create the per-key Lock under _locks_mutex (D-02 dict-mutation guard)."""
        async with self._locks_mutex:
            return self._key_locks.setdefault(key, asyncio.Lock())

    def _cancel_idle(self, profile_id: str) -> None:
        """Cancel and pop any pending idle task for profile_id (fire-and-forget).

        Per the asyncio docs: task.cancel() schedules CancelledError on the
        next await point. The idle task's only post-sleep action is to
        re-acquire browser_mgr._lock and re-check counts — both safe under
        cancel. We don't await: caller is on_attach (sync from WS handler).
        """
        task = self._idle_tasks.pop(profile_id, None)
        if task is not None and not task.done():
            task.cancel()

    async def _idle_sleep(self, profile_id: str, delay: int) -> None:
        """Sleep then stop, with defense-in-depth re-check (D-08).

        Sequence:
        1. await asyncio.sleep(delay) — cancellable.
        2. Acquire browser_mgr._lock.
        3. Re-check counts; if any > 0, exit (the cancel may have lost the
           race but the count truth wins).
        4. browser_mgr._stop_locked(profile_id) — caller holds the lock,
           so we use the lock-held variant to avoid deadlock (Pitfall C).
        5. Pop self from _idle_tasks.
        6. Log warm_pool_sleep.
        """
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            # Normal cancellation path; exit silently.
            return

        try:
            running = self._browser.running.get(profile_id)
            if running is None:
                # Already gone — nothing to do.
                self._idle_tasks.pop(profile_id, None)
                return

            async with self._browser._lock:
                # Re-fetch under lock — the race window between sleep return
                # and lock acquire could see a stale snapshot.
                running = self._browser.running.get(profile_id)
                if running is None:
                    return
                if running.cdp_attach_count > 0 or running.viewer_attach_count > 0:
                    # Defense-in-depth: a concurrent attach incremented but
                    # the cancel never reached us. Don't stop.
                    return
                idle_started = running.idle_started_at
                vendor_type = "?"
                vendor_connection_id = "?"
                # Pull from DB row only if needed; running has profile_id.
                # Logging hint: lookup once, swallow on miss.
                try:
                    prof = db.get_profile(profile_id)
                    if prof:
                        vendor_type = prof.get("vendor_type", "?")
                        vendor_connection_id = prof.get("vendor_connection_id", "?")
                except Exception:  # pragma: no cover — log-only path
                    pass

                # Stop while holding the lock (RESEARCH.md §3 Option 1).
                await self._browser._stop_locked(profile_id)

            idle_seconds = (
                (_now_utc() - idle_started).total_seconds()
                if idle_started is not None else delay
            )
            logger.info(
                "event=warm_pool_sleep profile_id=%s vendor_type=%s vendor_connection_id=%s idle_seconds=%.1f reason=idle_timeout",
                profile_id, vendor_type, vendor_connection_id, idle_seconds,
            )
        finally:
            self._idle_tasks.pop(profile_id, None)
