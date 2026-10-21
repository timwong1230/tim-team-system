from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "polar_order.db"
MENU_PATH = ROOT / "data" / "menu.json"
TABLE_COUNT = 20


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    conn = connect()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS tables (
            id INTEGER PRIMARY KEY,
            code TEXT NOT NULL UNIQUE,
            label TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS menu_categories (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            sort_order INTEGER NOT NULL,
            promo TEXT NOT NULL DEFAULT 'none'
        );

        CREATE TABLE IF NOT EXISTS menu_items (
            id TEXT PRIMARY KEY,
            category_id TEXT NOT NULL,
            name TEXT NOT NULL,
            price REAL NOT NULL,
            unit TEXT,
            note TEXT,
            allow_note INTEGER NOT NULL DEFAULT 0,
            available INTEGER NOT NULL DEFAULT 1,
            FOREIGN KEY(category_id) REFERENCES menu_categories(id)
        );

        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            table_id INTEGER NOT NULL,
            party_size INTEGER NOT NULL DEFAULT 1,
            status TEXT NOT NULL DEFAULT 'open',
            opened_at TEXT NOT NULL,
            closed_at TEXT,
            FOREIGN KEY(table_id) REFERENCES tables(id)
        );

        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            table_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'new',
            note TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(session_id) REFERENCES sessions(id),
            FOREIGN KEY(table_id) REFERENCES tables(id)
        );

        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            item_id TEXT NOT NULL,
            item_name TEXT NOT NULL,
            category_id TEXT NOT NULL,
            promo TEXT NOT NULL DEFAULT 'none',
            qty INTEGER NOT NULL,
            unit_price REAL NOT NULL,
            line_total REAL NOT NULL,
            note TEXT,
            FOREIGN KEY(order_id) REFERENCES orders(id)
        );

        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL,
            payload TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """
    )
    conn.commit()
    _seed_tables(conn)
    _seed_menu(conn)
    conn.close()


def _seed_tables(conn: sqlite3.Connection) -> None:
    for i in range(1, TABLE_COUNT + 1):
        code = f"T{i:02d}"
        conn.execute(
            "INSERT OR IGNORE INTO tables (id, code, label) VALUES (?, ?, ?)",
            (i, code, f"Table {i}"),
        )
    conn.commit()


def _seed_menu(conn: sqlite3.Connection) -> None:
    count = conn.execute("SELECT COUNT(*) AS c FROM menu_items").fetchone()["c"]
    if count:
        return
    menu = json.loads(MENU_PATH.read_text(encoding="utf-8"))
    for cat in menu["categories"]:
        conn.execute(
            "INSERT OR REPLACE INTO menu_categories (id, name, sort_order, promo) VALUES (?, ?, ?, ?)",
            (cat["id"], cat["name"], cat["sort"], cat.get("promo", "none")),
        )
        for item in cat["items"]:
            conn.execute(
                """
                INSERT OR REPLACE INTO menu_items
                (id, category_id, name, price, unit, note, allow_note, available)
                VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                """,
                (
                    item["id"],
                    cat["id"],
                    item["name"],
                    float(item["price"]),
                    item.get("unit"),
                    item.get("note"),
                    1 if item.get("allow_note") else 0,
                ),
            )
    conn.commit()


def load_menu_meta() -> dict[str, Any]:
    return json.loads(MENU_PATH.read_text(encoding="utf-8"))


def get_table_by_code(conn: sqlite3.Connection, code: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM tables WHERE code = ?", (code.upper(),)).fetchone()


def get_open_session(conn: sqlite3.Connection, table_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM sessions WHERE table_id = ? AND status = 'open' ORDER BY id DESC LIMIT 1",
        (table_id,),
    ).fetchone()


def ensure_session(conn: sqlite3.Connection, table_id: int, party_size: int = 1) -> sqlite3.Row:
    session = get_open_session(conn, table_id)
    if session:
        if party_size and party_size != session["party_size"]:
            conn.execute(
                "UPDATE sessions SET party_size = ? WHERE id = ?",
                (party_size, session["id"]),
            )
            conn.commit()
            session = get_open_session(conn, table_id)
        return session
    now = utc_now()
    cur = conn.execute(
        "INSERT INTO sessions (table_id, party_size, status, opened_at) VALUES (?, ?, 'open', ?)",
        (table_id, max(1, party_size), now),
    )
    conn.commit()
    return conn.execute("SELECT * FROM sessions WHERE id = ?", (cur.lastrowid,)).fetchone()


def publish_event(conn: sqlite3.Connection, kind: str, payload: dict[str, Any]) -> None:
    conn.execute(
        "INSERT INTO events (kind, payload, created_at) VALUES (?, ?, ?)",
        (kind, json.dumps(payload), utc_now()),
    )
    conn.commit()
