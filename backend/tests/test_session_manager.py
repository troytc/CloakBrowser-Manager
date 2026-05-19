"""Unit tests for backend/session_manager.py (Phase 2 keystone)."""

from __future__ import annotations

import asyncio
import datetime
import json
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend import database as db
from backend.browser_manager import BrowserLaunchError, RunningProfile
from backend.database import NoTemplateError, create_template
from backend.session_manager import (
    SessionManager,
    SessionResult,
    SessionStatusEnvelope,
    _idle_timeout_secs,
)


# ---------- helpers ----------

def _seed_template(vendor_type: str = "acme") -> dict:
    blueprint = {
        "timezone": "UTC", "locale": "en-US", "platform": "windows",
        "screen_width": 1920, "screen_height": 1080, "humanize": False,
        "human_preset": "default", "launch_args": [], "clipboard_sync": False,
    }
    return create_template(
        vendor_type=vendor_type,
        label=f"{vendor_type} template",
        notes=None,
        blueprint_json=json.dumps(blueprint),
    )


def _make_running(profile_id: str = "p1", cdp_count: int = 0, viewer_count: int = 0) -> RunningProfile:
    rp = RunningProfile(
        profile_id=profile_id,
        context=AsyncMock(),
        display=99,
        ws_port=6199,
        cdp_port=5100,
    )
    rp.cdp_attach_count = cdp_count
    rp.viewer_attach_count = viewer_count
    rp.last_launched_at = datetime.datetime.now(datetime.timezone.utc)
    return rp


@pytest.fixture
def mock_bm():
    """A MagicMock-flavored BrowserManager with the surfaces SessionManager touches."""
    bm = MagicMock()
    bm.running = {}
    bm._lock = asyncio.Lock()
    bm.launch = AsyncMock()
    bm.stop = AsyncMock()
    bm._stop_locked = AsyncMock()
    return bm


@pytest.fixture
def sm(mock_bm):
    return SessionManager(browser_mgr=mock_bm)


# ---------- get_or_wake ----------

@pytest.mark.asyncio
async def test_get_or_wake_creates_and_launches_when_no_running(tmp_db, sm, mock_bm):
    _seed_template("acme")
    rp = _make_running("will-be-set-after-launch")
    mock_bm.launch.return_value = rp

    result = await sm.get_or_wake("acme", "user-1")

    assert isinstance(result, SessionResult)
    assert result.state == "running"
    assert result.cdp_url == f"/api/profiles/{result.profile_id}/cdp"
    assert mock_bm.launch.await_count == 1
    # The dict passed to launch is the upserted profile
    profile_dict = mock_bm.launch.await_args.args[0]
    assert profile_dict["vendor_type"] == "acme"
    assert profile_dict["vendor_connection_id"] == "user-1"


@pytest.mark.asyncio
async def test_get_or_wake_returns_running_without_relaunching(tmp_db, sm, mock_bm):
    _seed_template("acme")
    profile = db.upsert_profile_by_vendor("acme", "user-1")
    mock_bm.running[profile["id"]] = _make_running(profile["id"])

    result = await sm.get_or_wake("acme", "user-1")

    assert result.profile_id == profile["id"]
    assert result.state == "running"
    assert mock_bm.launch.await_count == 0


@pytest.mark.asyncio
async def test_get_or_wake_serializes_concurrent_calls_for_same_key(tmp_db, sm, mock_bm):
    _seed_template("acme")

    async def slow_launch(profile_dict):
        # Slow enough that without a lock all 10 would race past the
        # bm.running.get check
        await asyncio.sleep(0.05)
        rp = _make_running(profile_dict["id"])
        # Important: simulate the lock-held registration that real launch does
        mock_bm.running[profile_dict["id"]] = rp
        return rp

    mock_bm.launch.side_effect = slow_launch

    results = await asyncio.gather(*[
        sm.get_or_wake("acme", "user-1") for _ in range(10)
    ])

    profile_ids = {r.profile_id for r in results}
    assert len(profile_ids) == 1
    assert mock_bm.launch.await_count == 1

    with db.get_db() as conn:
        rows = conn.execute(
            "SELECT id FROM profiles WHERE vendor_type=? AND vendor_connection_id=?",
            ("acme", "user-1"),
        ).fetchall()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_get_or_wake_concurrent_calls_for_different_keys_run_in_parallel(tmp_db, sm, mock_bm):
    _seed_template("acme")
    _seed_template("globex")

    async def slow_launch(profile_dict):
        await asyncio.sleep(0.1)
        rp = _make_running(profile_dict["id"])
        mock_bm.running[profile_dict["id"]] = rp
        return rp

    mock_bm.launch.side_effect = slow_launch

    t0 = time.monotonic()
    await asyncio.gather(
        sm.get_or_wake("acme", "user-1"),
        sm.get_or_wake("globex", "user-2"),
    )
    elapsed = time.monotonic() - t0

    # If sequential we'd see ~0.2s; in parallel <= 0.15s with comfortable margin
    assert elapsed < 0.18, f"Calls did not run in parallel: elapsed={elapsed:.3f}s"


@pytest.mark.asyncio
async def test_get_or_wake_raises_no_template_error(tmp_db, sm, mock_bm):
    with pytest.raises(NoTemplateError):
        await sm.get_or_wake("does-not-exist", "user-1")
    assert mock_bm.launch.await_count == 0


@pytest.mark.asyncio
async def test_get_or_wake_propagates_browser_launch_error(tmp_db, sm, mock_bm):
    _seed_template("acme")
    mock_bm.launch.side_effect = BrowserLaunchError("probe failed")
    with pytest.raises(BrowserLaunchError):
        await sm.get_or_wake("acme", "user-1")


# ---------- on_attach / _cancel_idle ----------

@pytest.mark.asyncio
async def test_on_attach_cancels_pending_idle_task(sm):
    async def long_sleep():
        await asyncio.sleep(60)

    task = asyncio.create_task(long_sleep())
    sm._idle_tasks["p1"] = task
    sm.on_attach("p1")
    # Allow the cancellation to propagate
    await asyncio.sleep(0)
    assert "p1" not in sm._idle_tasks
    assert task.cancelled() or task.done()


def test_on_attach_no_op_when_no_pending_task(sm):
    sm.on_attach("nonexistent")  # must not raise
    assert sm._idle_tasks == {}


# ---------- on_all_detached ----------

@pytest.mark.asyncio
async def test_on_all_detached_schedules_idle_task(monkeypatch, sm, mock_bm):
    monkeypatch.setenv("IDLE_TIMEOUT_SECONDS", "60")
    rp = _make_running("p1")
    mock_bm.running["p1"] = rp

    sm.on_all_detached("p1")

    assert "p1" in sm._idle_tasks
    assert isinstance(sm._idle_tasks["p1"], asyncio.Task)
    assert rp.idle_started_at is not None
    # Cleanup: cancel the long timer to avoid leak
    sm._idle_tasks["p1"].cancel()


def test_on_all_detached_no_op_when_not_running(sm, mock_bm):
    # bm.running is empty
    sm.on_all_detached("p1")
    assert "p1" not in sm._idle_tasks


# ---------- _idle_sleep ----------

@pytest.mark.asyncio
async def test_idle_task_fires_and_stops_after_timeout(monkeypatch, tmp_db, sm, mock_bm, caplog):
    _seed_template("acme")
    profile = db.upsert_profile_by_vendor("acme", "user-1")
    monkeypatch.setenv("IDLE_TIMEOUT_SECONDS", "1")
    rp = _make_running(profile["id"])
    mock_bm.running[profile["id"]] = rp

    import logging as _logging
    caplog.set_level(_logging.INFO, logger="vendorbrowser.session_manager")

    sm.on_all_detached(profile["id"])
    # Wait longer than timeout for the task to fire
    await asyncio.sleep(1.4)

    mock_bm._stop_locked.assert_awaited_once_with(profile["id"])
    assert profile["id"] not in sm._idle_tasks
    # The operator-relied warm_pool_sleep log line MUST be emitted on idle fire.
    # Locks the structured KV format (event=warm_pool_sleep ...) so a refactor
    # that breaks the shape gets caught here, not in production grep pipelines.
    assert any("event=warm_pool_sleep" in r.message for r in caplog.records), \
        f"warm_pool_sleep log line not emitted; got: {[r.message for r in caplog.records]}"


@pytest.mark.asyncio
async def test_idle_task_defense_in_depth_recheck_skips_stop_when_count_grew(monkeypatch, tmp_db, sm, mock_bm):
    _seed_template("acme")
    profile = db.upsert_profile_by_vendor("acme", "user-1")
    monkeypatch.setenv("IDLE_TIMEOUT_SECONDS", "1")
    rp = _make_running(profile["id"], cdp_count=0)
    mock_bm.running[profile["id"]] = rp

    sm.on_all_detached(profile["id"])
    # Simulate a concurrent attach during the sleep window — count > 0
    # but the cancel never reached us (lost-cancel scenario)
    rp.cdp_attach_count = 1
    await asyncio.sleep(1.4)

    # _stop_locked must NOT have been called — re-check saved us
    mock_bm._stop_locked.assert_not_awaited()


@pytest.mark.asyncio
async def test_idle_task_swallows_cancellation_silently(monkeypatch, sm, mock_bm):
    monkeypatch.setenv("IDLE_TIMEOUT_SECONDS", "60")
    rp = _make_running("p1")
    mock_bm.running["p1"] = rp

    sm.on_all_detached("p1")
    sm.on_attach("p1")
    await asyncio.sleep(0.05)

    assert "p1" not in sm._idle_tasks
    mock_bm._stop_locked.assert_not_awaited()


@pytest.mark.asyncio
async def test_only_one_idle_timer_per_profile(monkeypatch, sm, mock_bm):
    monkeypatch.setenv("IDLE_TIMEOUT_SECONDS", "60")
    rp = _make_running("p1")
    mock_bm.running["p1"] = rp

    sm.on_all_detached("p1")
    first_task = sm._idle_tasks["p1"]
    sm.on_all_detached("p1")
    second_task = sm._idle_tasks["p1"]

    assert first_task is not second_task
    await asyncio.sleep(0)  # let cancel propagate
    assert first_task.cancelled() or first_task.done()
    # Cleanup
    second_task.cancel()


@pytest.mark.asyncio
async def test_idle_timeout_seconds_read_at_schedule_time(monkeypatch, sm, mock_bm):
    monkeypatch.setenv("IDLE_TIMEOUT_SECONDS", "1")
    assert _idle_timeout_secs() == 1
    monkeypatch.setenv("IDLE_TIMEOUT_SECONDS", "5")
    assert _idle_timeout_secs() == 5
    # Invalid → default
    monkeypatch.setenv("IDLE_TIMEOUT_SECONDS", "garbage")
    assert _idle_timeout_secs() == 600


# ---------- status_envelope ----------

def test_status_envelope_running_with_attaches(sm, mock_bm):
    rp = _make_running("p1", cdp_count=1)
    mock_bm.running["p1"] = rp
    env = sm.status_envelope("p1")
    assert env.state == "running"
    assert env.cdp_attach_count == 1
    assert env.idle_expires_at is None
    assert env.last_launched_at is not None


def test_status_envelope_idle_when_zero_counts_with_pending_idle_task(sm, mock_bm):
    rp = _make_running("p1")
    rp.idle_started_at = datetime.datetime.now(datetime.timezone.utc)
    mock_bm.running["p1"] = rp

    fake_task = MagicMock()
    fake_task.done.return_value = False
    sm._idle_tasks["p1"] = fake_task

    env = sm.status_envelope("p1")
    assert env.state == "idle"
    assert env.idle_expires_at is not None  # ISO-8601 string


def test_status_envelope_stopped_when_not_running(sm, mock_bm):
    env = sm.status_envelope("p1")
    assert env.state == "stopped"
    assert env.cdp_attach_count == 0
    assert env.viewer_attach_count == 0
    assert env.idle_expires_at is None
    assert env.last_launched_at is None


# ---------- shutdown ----------

@pytest.mark.asyncio
async def test_shutdown_cancels_all_idle_tasks(sm, mock_bm):
    async def long_sleep():
        await asyncio.sleep(60)

    sm._idle_tasks["p1"] = asyncio.create_task(long_sleep())
    sm._idle_tasks["p2"] = asyncio.create_task(long_sleep())

    await sm.shutdown()

    assert sm._idle_tasks == {}
    mock_bm._stop_locked.assert_not_awaited()


# ---------- remove_key_lock ----------

def test_remove_key_lock_drops_entry(sm):
    sm._key_locks[("acme", "user-1")] = asyncio.Lock()
    sm.remove_key_lock("acme", "user-1")
    assert ("acme", "user-1") not in sm._key_locks
    # No-op for non-existent key
    sm.remove_key_lock("missing", "x")  # must not raise
