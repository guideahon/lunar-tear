#!/usr/bin/env python3
"""Apply pending migrations to game.db using sqlite3 directly."""
import sqlite3
from pathlib import Path

DB = Path(__file__).parent / "db" / "game.db"

def col_exists(cur, table, col):
    cur.execute(f"PRAGMA table_info({table})")
    return any(r[1] == col for r in cur.fetchall())

def table_exists(cur, name):
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,))
    return bool(cur.fetchone())

con = sqlite3.connect(str(DB))
cur = con.cursor()

# Migration: add_facebook_id
if not col_exists(cur, "users", "facebook_id"):
    print("[migrate] Adding facebook_id column to users...")
    cur.execute("ALTER TABLE users ADD COLUMN facebook_id INTEGER")
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_facebook_id ON users(facebook_id) WHERE facebook_id IS NOT NULL")
    print("[migrate] facebook_id: OK")
else:
    print("[migrate] facebook_id: already present")

# Migration: add_parts_status_subs
if not table_exists(cur, "user_parts_status_subs"):
    print("[migrate] Creating user_parts_status_subs table...")
    cur.execute("""
        CREATE TABLE user_parts_status_subs (
            user_id                      INTEGER NOT NULL REFERENCES users(user_id),
            user_parts_uuid              TEXT    NOT NULL,
            status_index                 INTEGER NOT NULL,
            parts_status_sub_lottery_id  INTEGER NOT NULL DEFAULT 0,
            level                        INTEGER NOT NULL DEFAULT 0,
            status_kind_type             INTEGER NOT NULL DEFAULT 0,
            status_calculation_type      INTEGER NOT NULL DEFAULT 0,
            status_change_value          INTEGER NOT NULL DEFAULT 0,
            latest_version               INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (user_id, user_parts_uuid, status_index)
        )
    """)
    cur.execute("UPDATE user_parts SET level = 1")
    print("[migrate] user_parts_status_subs: OK")
else:
    print("[migrate] user_parts_status_subs: already present")

con.commit()
con.close()
print("[migrate] Done.")
