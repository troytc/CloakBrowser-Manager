"""SQLite database operations for browser profiles."""

from __future__ import annotations

import datetime
import json
import logging
import random
import shutil
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any

logger = logging.getLogger("cloakbrowser.manager.database")

DATA_DIR = Path("/data")
DB_PATH = DATA_DIR / "profiles.db"


@contextmanager
def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS profiles (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                fingerprint_seed INTEGER NOT NULL,
                proxy TEXT,
                timezone TEXT,
                locale TEXT,
                platform TEXT DEFAULT 'windows',
                user_agent TEXT,
                screen_width INTEGER DEFAULT 1920,
                screen_height INTEGER DEFAULT 1080,
                gpu_vendor TEXT,
                gpu_renderer TEXT,
                hardware_concurrency INTEGER,
                humanize BOOLEAN DEFAULT 0,
                human_preset TEXT DEFAULT 'default',
                headless BOOLEAN DEFAULT 0,
                geoip BOOLEAN DEFAULT 0,
                clipboard_sync BOOLEAN DEFAULT 0,
                color_scheme TEXT,
                notes TEXT,
                user_data_dir TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS profile_tags (
                profile_id TEXT REFERENCES profiles(id) ON DELETE CASCADE,
                tag TEXT NOT NULL,
                color TEXT,
                PRIMARY KEY (profile_id, tag)
            );

            CREATE TABLE IF NOT EXISTS vendor_templates (
                id TEXT PRIMARY KEY,
                vendor_type TEXT NOT NULL UNIQUE,
                label TEXT,
                notes TEXT,
                blueprint TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
        """)
        conn.commit()

        # Migrations for existing databases
        cols = {row[1] for row in conn.execute("PRAGMA table_info(profiles)").fetchall()}
        if "clipboard_sync" not in cols:
            conn.execute("ALTER TABLE profiles ADD COLUMN clipboard_sync BOOLEAN DEFAULT 1")
            conn.commit()
        if "launch_args" not in cols:
            conn.execute("ALTER TABLE profiles ADD COLUMN launch_args TEXT DEFAULT '[]'")
            conn.commit()

        # D-07: schema migration wipe — old dev/test schema lacks vendor_type column.
        # Unconditionally drop all profile rows (and their on-disk dirs) to make room for
        # the new (vendor_type, vendor_connection_id, template_id) shape. The wipe is
        # idempotent: once vendor_type exists, this block does nothing.
        cols = {row[1] for row in conn.execute("PRAGMA table_info(profiles)").fetchall()}
        if "vendor_type" not in cols:
            profile_ids = [r[0] for r in conn.execute("SELECT id FROM profiles").fetchall()]
            tag_rowcount = conn.execute("DELETE FROM profile_tags").rowcount
            profile_rowcount = conn.execute("DELETE FROM profiles").rowcount
            conn.commit()
            dir_count = 0
            for pid in profile_ids:
                pdir = DATA_DIR / "profiles" / pid
                if pdir.exists():
                    try:
                        shutil.rmtree(pdir, ignore_errors=True)
                        dir_count += 1
                    except Exception as exc:
                        logger.warning("Could not remove %s: %s", pdir, exc)
            logger.warning(
                "Schema migration: wiped %d profile rows (+ %d tag rows) and %d profile directories (dev/test data)",
                profile_rowcount, tag_rowcount, dir_count,
            )
            conn.execute("ALTER TABLE profiles ADD COLUMN vendor_type TEXT NOT NULL DEFAULT ''")
            conn.execute("ALTER TABLE profiles ADD COLUMN vendor_connection_id TEXT NOT NULL DEFAULT ''")
            conn.execute(
                "ALTER TABLE profiles ADD COLUMN template_id TEXT REFERENCES vendor_templates(id) ON DELETE RESTRICT"
            )
            conn.commit()
            # Refresh cols so later detection works
            cols = {row[1] for row in conn.execute("PRAGMA table_info(profiles)").fetchall()}

        # Idempotent UNIQUE index (D-05) on (vendor_type, vendor_connection_id)
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_profiles_vendor_pair "
            "ON profiles(vendor_type, vendor_connection_id)"
        )
        conn.commit()


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def create_profile(
    name: str,
    fingerprint_seed: int | None = None,
    **fields: Any,
) -> dict[str, Any]:
    profile_id = str(uuid.uuid4())
    seed = fingerprint_seed if fingerprint_seed is not None else random.randint(10000, 99999)
    user_data_dir = str(DATA_DIR / "profiles" / profile_id)
    now = _now()
    tags = fields.pop("tags", None) or []

    # Pitfall 2 fix — legacy-path coexistence with UNIQUE(vendor_type, vendor_connection_id).
    # Each legacy create_profile() call gets a distinct (__legacy__, uuid) pair so the
    # UNIQUE index does not reject back-to-back legacy creates.
    fields["vendor_type"] = fields.get("vendor_type") or "__legacy__"
    fields["vendor_connection_id"] = fields.get("vendor_connection_id") or str(uuid.uuid4())

    with get_db() as conn:
        conn.execute(
            """INSERT INTO profiles (
                id, name, fingerprint_seed, proxy, timezone, locale, platform,
                user_agent, screen_width, screen_height, gpu_vendor, gpu_renderer,
                hardware_concurrency, humanize, human_preset, headless, geoip,
                clipboard_sync, color_scheme, launch_args, notes,
                user_data_dir, created_at, updated_at,
                vendor_type, vendor_connection_id, template_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                profile_id, name, seed,
                fields.get("proxy"),
                fields.get("timezone"),
                fields.get("locale"),
                fields.get("platform", "windows"),
                fields.get("user_agent"),
                fields.get("screen_width", 1920),
                fields.get("screen_height", 1080),
                fields.get("gpu_vendor"),
                fields.get("gpu_renderer"),
                fields.get("hardware_concurrency"),
                fields.get("humanize", False),
                fields.get("human_preset", "default"),
                fields.get("headless", False),
                fields.get("geoip", False),
                fields.get("clipboard_sync", False),
                fields.get("color_scheme"),
                json.dumps(fields.get("launch_args") or []),
                fields.get("notes"),
                user_data_dir, now, now,
                fields["vendor_type"],
                fields["vendor_connection_id"],
                fields.get("template_id"),
            ),
        )
        for t in tags:
            conn.execute(
                "INSERT INTO profile_tags (profile_id, tag, color) VALUES (?, ?, ?)",
                (profile_id, t["tag"], t.get("color")),
            )
        conn.commit()

    return get_profile(profile_id)  # type: ignore[return-value]


def get_profile(profile_id: str) -> dict[str, Any] | None:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,)).fetchone()
        if not row:
            return None
        profile = dict(row)
        profile["launch_args"] = json.loads(profile.get("launch_args") or "[]")
        tags = conn.execute(
            "SELECT tag, color FROM profile_tags WHERE profile_id = ?",
            (profile_id,),
        ).fetchall()
        profile["tags"] = [dict(t) for t in tags]
        return profile


def list_profiles() -> list[dict[str, Any]]:
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM profiles ORDER BY created_at DESC").fetchall()
        profiles = []
        for row in rows:
            profile = dict(row)
            profile["launch_args"] = json.loads(profile.get("launch_args") or "[]")
            tags = conn.execute(
                "SELECT tag, color FROM profile_tags WHERE profile_id = ?",
                (profile["id"],),
            ).fetchall()
            profile["tags"] = [dict(t) for t in tags]
            profiles.append(profile)
        return profiles


def update_profile(profile_id: str, **fields: Any) -> dict[str, Any] | None:
    existing = get_profile(profile_id)
    if not existing:
        return None

    tags = fields.pop("tags", None)

    # Only update fields that were explicitly provided
    update_cols = []
    update_vals = []
    # Pre-serialize launch_args to JSON before the generic update loop
    if "launch_args" in fields:
        fields["launch_args"] = json.dumps(fields["launch_args"] or [])

    for col in (
        "name", "fingerprint_seed", "proxy", "timezone", "locale", "platform",
        "user_agent", "screen_width", "screen_height", "gpu_vendor", "gpu_renderer",
        "hardware_concurrency", "humanize", "human_preset", "headless", "geoip",
        "clipboard_sync", "color_scheme", "launch_args", "notes",
    ):
        if col in fields:
            update_cols.append(f"{col} = ?")
            update_vals.append(fields[col])

    if update_cols:
        update_cols.append("updated_at = ?")
        update_vals.append(_now())
        update_vals.append(profile_id)
        with get_db() as conn:
            conn.execute(
                f"UPDATE profiles SET {', '.join(update_cols)} WHERE id = ?",
                update_vals,
            )
            conn.commit()

    if tags is not None:
        with get_db() as conn:
            conn.execute("DELETE FROM profile_tags WHERE profile_id = ?", (profile_id,))
            for t in tags:
                conn.execute(
                    "INSERT INTO profile_tags (profile_id, tag, color) VALUES (?, ?, ?)",
                    (profile_id, t["tag"], t.get("color")),
                )
            conn.commit()

    return get_profile(profile_id)


def delete_profile(profile_id: str) -> bool:
    with get_db() as conn:
        cursor = conn.execute("DELETE FROM profiles WHERE id = ?", (profile_id,))
        conn.commit()
        return cursor.rowcount > 0


# ---------------------------------------------------------------------------
# Vendor template helpers (D-01..D-09, TMPL-05)
# ---------------------------------------------------------------------------

def list_templates() -> list[dict[str, Any]]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, vendor_type, label, notes, blueprint, created_at, updated_at "
            "FROM vendor_templates ORDER BY created_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def get_template(template_id: str) -> dict[str, Any] | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT id, vendor_type, label, notes, blueprint, created_at, updated_at "
            "FROM vendor_templates WHERE id = ?",
            (template_id,),
        ).fetchone()
    return dict(row) if row else None


def get_template_by_vendor_type(vendor_type: str) -> dict[str, Any] | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT id, vendor_type, label, notes, blueprint, created_at, updated_at "
            "FROM vendor_templates WHERE vendor_type = ?",
            (vendor_type,),
        ).fetchone()
    return dict(row) if row else None


def create_template(
    *, vendor_type: str, label: str | None, notes: str | None, blueprint_json: str
) -> dict[str, Any]:
    template_id = str(uuid.uuid4())
    now = _now()
    with get_db() as conn:
        conn.execute(
            "INSERT INTO vendor_templates (id, vendor_type, label, notes, blueprint, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (template_id, vendor_type, label, notes, blueprint_json, now, now),
        )
        conn.commit()
    result = get_template(template_id)
    assert result is not None
    return result


def update_template(template_id: str, **fields: Any) -> dict[str, Any] | None:
    if not fields:
        return get_template(template_id)
    sets: list[str] = []
    values: list[Any] = []
    for key in ("label", "notes", "blueprint_json"):
        if key in fields:
            col = "blueprint" if key == "blueprint_json" else key
            sets.append(f"{col} = ?")
            values.append(fields[key])
    sets.append("updated_at = ?")
    values.append(_now())
    values.append(template_id)
    with get_db() as conn:
        cur = conn.execute(
            f"UPDATE vendor_templates SET {', '.join(sets)} WHERE id = ?",
            tuple(values),
        )
        conn.commit()
        if cur.rowcount == 0:
            return None
    return get_template(template_id)


def delete_template(template_id: str) -> bool:
    with get_db() as conn:
        cur = conn.execute("DELETE FROM vendor_templates WHERE id = ?", (template_id,))
        conn.commit()
        return cur.rowcount > 0


def count_profiles_by_template(template_id: str) -> int:
    with get_db() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM profiles WHERE template_id = ?",
            (template_id,),
        ).fetchone()
    return int(row["n"])


def list_profiles_by_template(template_id: str) -> list[str]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id FROM profiles WHERE template_id = ? ORDER BY created_at ASC",
            (template_id,),
        ).fetchall()
    return [r["id"] for r in rows]


def create_profile_from_template(
    template: dict[str, Any],
    vendor_connection_id: str,
    name: str | None = None,
) -> dict[str, Any]:
    """Snapshot-copy blueprint fields into a new profile row (D-03, D-04, TMPL-05).

    Called by Phase 2's POST /sessions handler; NOT called in Phase 1 routes.
    The blueprint is read once at creation time and copied verbatim into profile
    columns — subsequent template edits never mutate this profile (TMPL-05).
    """
    bp = template["blueprint"]
    if isinstance(bp, str):
        bp = json.loads(bp)

    profile_id = str(uuid.uuid4())
    seed = random.randint(10000, 99999)  # D-04: always random per profile, never from template
    display_name = name or f"{template['vendor_type']}/{vendor_connection_id}"
    user_data_dir = str(DATA_DIR / "profiles" / profile_id)
    now = _now()

    with get_db() as conn:
        conn.execute(
            "INSERT INTO profiles ("
            "id, name, fingerprint_seed, "
            "vendor_type, vendor_connection_id, template_id, "
            "proxy, timezone, locale, platform, user_agent, "
            "screen_width, screen_height, gpu_vendor, gpu_renderer, "
            "hardware_concurrency, humanize, human_preset, headless, geoip, "
            "clipboard_sync, color_scheme, launch_args, notes, "
            "user_data_dir, created_at, updated_at"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                profile_id, display_name, seed,
                template["vendor_type"], vendor_connection_id, template["id"],
                bp.get("proxy"),
                bp.get("timezone"),
                bp.get("locale"),
                bp.get("platform", "windows"),
                bp.get("user_agent"),
                bp.get("screen_width", 1920),
                bp.get("screen_height", 1080),
                bp.get("gpu_vendor"),
                bp.get("gpu_renderer"),
                bp.get("hardware_concurrency"),
                bool(bp.get("humanize", False)),
                bp.get("human_preset", "default"),
                False,
                False,
                bool(bp.get("clipboard_sync", False)),  # D-18
                bp.get("color_scheme"),
                json.dumps(bp.get("launch_args") or []),
                None,
                user_data_dir, now, now,
            ),
        )
        conn.commit()
    result = get_profile(profile_id)
    assert result is not None
    return result
