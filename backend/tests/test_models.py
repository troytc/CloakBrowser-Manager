"""Tests for Pydantic models — validation, defaults, constraints."""

import pytest
from pydantic import ValidationError

from backend.models import (
    ClipboardRequest,
    LaunchResponse,
    ProfileCreate,
    ProfileResponse,
    ProfileStatusResponse,
    ProfileUpdate,
    StatusResponse,
    TagCreate,
    TagResponse,
)


# ── ProfileCreate ────────────────────────────────────────────────────────────


def test_profile_create_minimal():
    p = ProfileCreate(name="Test")
    assert p.name == "Test"
    assert p.fingerprint_seed is None
    assert p.platform == "windows"
    assert p.screen_width == 1920
    assert p.screen_height == 1080
    assert p.humanize is False
    assert p.headless is False
    assert p.geoip is False
    assert p.human_preset == "default"


def test_profile_create_all_fields():
    p = ProfileCreate(
        name="Full",
        fingerprint_seed=42,
        proxy="http://host:8080",
        timezone="America/New_York",
        locale="en-US",
        platform="macos",
        user_agent="Mozilla/5.0",
        screen_width=2560,
        screen_height=1440,
        gpu_vendor="NVIDIA",
        gpu_renderer="RTX 3070",
        hardware_concurrency=16,
        humanize=True,
        human_preset="careful",
        headless=True,
        geoip=True,
        color_scheme="dark",
        notes="test note",
        tags=[TagCreate(tag="work", color="#ff0000")],
    )
    assert p.platform == "macos"
    assert p.human_preset == "careful"
    assert p.color_scheme == "dark"
    assert len(p.tags) == 1


def test_profile_create_launch_args_default():
    p = ProfileCreate(name="Test")
    assert p.launch_args == []


def test_profile_create_with_launch_args():
    p = ProfileCreate(name="Test", launch_args=["--load-extension=/tmp/ext"])
    assert p.launch_args == ["--load-extension=/tmp/ext"]


def test_profile_update_launch_args():
    p = ProfileUpdate(launch_args=["--flag"])
    dumped = p.model_dump(exclude_unset=True)
    assert dumped == {"launch_args": ["--flag"]}


def test_profile_create_invalid_platform():
    with pytest.raises(ValidationError):
        ProfileCreate(name="Bad", platform="android")


def test_profile_create_invalid_human_preset():
    with pytest.raises(ValidationError):
        ProfileCreate(name="Bad", human_preset="fast")


def test_profile_create_invalid_color_scheme():
    with pytest.raises(ValidationError):
        ProfileCreate(name="Bad", color_scheme="auto")


# ── ProfileUpdate ────────────────────────────────────────────────────────────


def test_profile_update_all_optional():
    p = ProfileUpdate()
    assert p.name is None
    assert p.platform is None


def test_profile_update_exclude_unset():
    p = ProfileUpdate(name="New Name")
    dumped = p.model_dump(exclude_unset=True)
    assert dumped == {"name": "New Name"}


def test_profile_update_invalid_platform():
    with pytest.raises(ValidationError):
        ProfileUpdate(platform="android")


# ── TagCreate ────────────────────────────────────────────────────────────────


def test_tag_create_minimal():
    t = TagCreate(tag="work")
    assert t.tag == "work"
    assert t.color is None


def test_tag_create_with_color():
    t = TagCreate(tag="personal", color="#00ff00")
    assert t.color == "#00ff00"


# ── ClipboardRequest ─────────────────────────────────────────────────────────


def test_clipboard_request_valid():
    c = ClipboardRequest(text="hello world")
    assert c.text == "hello world"


def test_clipboard_request_max_length():
    with pytest.raises(ValidationError):
        ClipboardRequest(text="x" * 1_048_577)


def test_clipboard_request_at_limit():
    c = ClipboardRequest(text="x" * 1_048_576)
    assert len(c.text) == 1_048_576


# ── LaunchResponse ──────────────────────────────────────────────────────────


def test_launch_response_with_cdp_url():
    r = LaunchResponse(
        profile_id="abc", vnc_ws_port=6100, display=":100",
        cdp_url="/api/profiles/abc/cdp",
    )
    assert r.cdp_url == "/api/profiles/abc/cdp"


def test_launch_response_cdp_url_default_none():
    r = LaunchResponse(profile_id="abc", vnc_ws_port=6100, display=":100")
    assert r.cdp_url is None


# ── ProfileStatusResponse ──────────────────────────────────────────────────


def test_profile_status_response_cdp_url():
    r = ProfileStatusResponse(
        status="running", vnc_ws_port=6100, display=":100",
        cdp_url="/api/profiles/abc/cdp",
    )
    assert r.cdp_url == "/api/profiles/abc/cdp"


def test_profile_status_response_cdp_url_stopped():
    r = ProfileStatusResponse(status="stopped")
    assert r.cdp_url is None


# ── ProfileResponse ────────────────────────────────────────────────────────


def test_profile_response_cdp_url():
    r = ProfileResponse(
        id="abc", name="Test", fingerprint_seed=12345,
        user_data_dir="/data/profiles/abc",
        created_at="2026-01-01T00:00:00", updated_at="2026-01-01T00:00:00",
        status="running", cdp_url="/api/profiles/abc/cdp",
    )
    assert r.cdp_url == "/api/profiles/abc/cdp"


def test_profile_response_cdp_url_default_none():
    r = ProfileResponse(
        id="abc", name="Test", fingerprint_seed=12345,
        user_data_dir="/data/profiles/abc",
        created_at="2026-01-01T00:00:00", updated_at="2026-01-01T00:00:00",
    )
    assert r.cdp_url is None


"""Phase 2 machine-API model validation tests (SESS-02, SESS-13, PROF-03)."""

import pytest
from pydantic import ValidationError

from backend.models import (
    MachineProfileResponse,
    ProfilePatch,
    SessionListItem,
    SessionRequest,
    SessionResponse,
    SessionStatusResponse,
)


def test_session_request_accepts_valid_input():
    sr = SessionRequest(vendor_type="acme", vendor_connection_id="user-1")
    assert sr.vendor_type == "acme"
    assert sr.vendor_connection_id == "user-1"


def test_session_request_strips_whitespace():
    sr = SessionRequest(vendor_type="  acme  ", vendor_connection_id="\tuser-1\n")
    assert sr.vendor_type == "acme"
    assert sr.vendor_connection_id == "user-1"


def test_session_request_rejects_empty_vendor_type():
    with pytest.raises(ValidationError):
        SessionRequest(vendor_type="", vendor_connection_id="user-1")


def test_session_request_rejects_whitespace_only():
    with pytest.raises(ValidationError):
        SessionRequest(vendor_type="   ", vendor_connection_id="user-1")


def test_session_request_rejects_unknown_field():
    with pytest.raises(ValidationError):
        SessionRequest(
            vendor_type="acme",
            vendor_connection_id="user-1",
            extra_field="x",
        )


def test_session_response_default_vnc_viewer_url_is_empty():
    resp = SessionResponse(
        profile_id="p1",
        cdp_url="/api/profiles/p1/cdp",
        state="running",
    )
    assert resp.vnc_viewer_url == ""


def test_session_response_rejects_invalid_state():
    with pytest.raises(ValidationError):
        SessionResponse(
            profile_id="p1",
            cdp_url="/api/profiles/p1/cdp",
            state="unknown",
        )


def test_session_status_response_defaults():
    s = SessionStatusResponse(state="stopped")
    assert s.cdp_attach_count == 0
    assert s.viewer_attach_count == 0
    assert s.idle_expires_at is None
    assert s.last_launched_at is None


def test_session_list_item_round_trip():
    item = SessionListItem(
        profile_id="p1",
        vendor_type="acme",
        vendor_connection_id="u1",
        state="running",
        cdp_attach_count=2,
        viewer_attach_count=0,
    )
    assert item.cdp_attach_count == 2
    assert item.state == "running"


def test_profile_patch_accepts_notes_only():
    p = ProfilePatch(notes="hello")
    assert p.notes == "hello"
    p_empty = ProfilePatch()
    assert p_empty.notes is None


def test_profile_patch_rejects_clipboard_sync():
    with pytest.raises(ValidationError):
        ProfilePatch(notes="x", clipboard_sync=True)


def test_profile_patch_rejects_identity_keys():
    with pytest.raises(ValidationError):
        ProfilePatch(notes="x", vendor_type="acme")
    with pytest.raises(ValidationError):
        ProfilePatch(notes="x", vendor_connection_id="u")
    with pytest.raises(ValidationError):
        ProfilePatch(notes="x", template_id="t")


def test_machine_profile_response_round_trip():
    payload = {
        "id": "p1",
        "name": "acme/u1",
        "vendor_type": "acme",
        "vendor_connection_id": "u1",
        "template_id": "t1",
        "notes": None,
        "user_data_dir": "/data/profiles/p1",
        "created_at": "2026-05-09T00:00:00+00:00",
        "updated_at": "2026-05-09T00:00:00+00:00",
        "timezone": "UTC",
        "locale": "en-US",
        "platform": "windows",
        "screen_width": 1920,
        "screen_height": 1080,
        "clipboard_sync": 0,
    }
    m = MachineProfileResponse(**payload)
    assert m.vendor_type == "acme"
    assert m.vendor_connection_id == "u1"
    assert m.clipboard_sync is False
