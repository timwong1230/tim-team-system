from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .seats import SEATS

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "polar_order.db"
MENU_PATH = ROOT / "data" / "menu.json"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r["name"] == column for r in rows)


def _ensure_columns(conn: sqlite3.Connection) -> None:
    migrations = [
        ("tables", "zone", "TEXT"),
        ("tables", "sort_order", "INTEGER NOT NULL DEFAULT 0"),
        ("menu_items", "image", "TEXT"),
        ("sessions", "guest_name", "TEXT"),
        ("sessions", "discount_percent", "REAL NOT NULL DEFAULT 0"),
        ("sessions", "subtotal", "REAL"),
        ("sessions", "snack_charge", "REAL"),
        ("sessions", "service_charge", "REAL"),
        ("sessions", "discount_amount", "REAL"),
        ("sessions", "total", "REAL"),
        ("sessions", "receipt_path", "TEXT"),
        ("sessions", "business_date", "TEXT"),
        ("orders", "created_by", "TEXT"),
        ("orders", "deliver_table_id", "INTEGER"),
        ("orders", "gift_message", "TEXT"),
    ]
    for table, col, decl in migrations:
        if not _column_exists(conn, table, col):
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")
    conn.commit()


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
            image TEXT,
            FOREIGN KEY(category_id) REFERENCES menu_categories(id)
        );

        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            table_id INTEGER NOT NULL,
            party_size INTEGER NOT NULL DEFAULT 1,
            status TEXT NOT NULL DEFAULT 'open',
            opened_at TEXT NOT NULL,
            closed_at TEXT,
            discount_percent REAL NOT NULL DEFAULT 0,
            subtotal REAL,
            snack_charge REAL,
            service_charge REAL,
            discount_amount REAL,
            total REAL,
            receipt_path TEXT,
            business_date TEXT,
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
    _ensure_columns(conn)
    _seed_tables(conn)
    sync_menu(conn)
    conn.close()


def _seat_id(seat: dict) -> int:
    zone = seat["zone"]
    if zone == "boss":
        # BOSSJON / BOSSBARRY / BOSSTIM / BOSSZIV → 31-34
        from .seats import BOSSES

        code = seat["code"].upper()
        for i, b in enumerate(BOSSES):
            if code == f"BOSS{b['id'].upper()}":
                return 31 + i
        return 39
    num = int("".join(ch for ch in seat["code"] if ch.isdigit()) or "0")
    if zone == "table":
        return num  # 1-5
    if zone == "bar":
        return 10 + num  # 11-15
    return 20 + num  # 21-28 terrace


def _seed_tables(conn: sqlite3.Connection) -> None:
    """Sync Polar seat map; deactivate seats no longer used."""
    conn.execute("UPDATE tables SET active = 0")
    wanted_codes = {s["code"] for s in SEATS}
    # Free codes that will be claimed by new seat ids (avoid UNIQUE conflicts)
    for seat in SEATS:
        sid = _seat_id(seat)
        conn.execute(
            "UPDATE tables SET code = 'OLD_' || id || '_' || code WHERE code = ? AND id != ?",
            (seat["code"], sid),
        )
    for seat in SEATS:
        sid = _seat_id(seat)
        conn.execute(
            """
            INSERT INTO tables (id, code, label, zone, sort_order, active)
            VALUES (?, ?, ?, ?, ?, 1)
            ON CONFLICT(id) DO UPDATE SET
              code=excluded.code,
              label=excluded.label,
              zone=excluded.zone,
              sort_order=excluded.sort_order,
              active=1
            """,
            (sid, seat["code"], seat["label"], seat["zone"], seat["sort"]),
        )
    # Keep any leftover historical rows inactive
    conn.execute(
        f"UPDATE tables SET active = 0 WHERE code NOT IN ({','.join('?' for _ in wanted_codes)})",
        tuple(wanted_codes),
    )
    conn.commit()


def sync_menu(conn: sqlite3.Connection) -> None:
    """Upsert categories/items from menu.json (prices, notes, images)."""
    menu = json.loads(MENU_PATH.read_text(encoding="utf-8"))
    keep_cats: list[str] = []
    keep_items: list[str] = []
    for cat in menu["categories"]:
        keep_cats.append(cat["id"])
        conn.execute(
            "INSERT OR REPLACE INTO menu_categories (id, name, sort_order, promo) VALUES (?, ?, ?, ?)",
            (cat["id"], cat["name"], cat["sort"], cat.get("promo", "none")),
        )
        for item in cat["items"]:
            keep_items.append(item["id"])
            conn.execute(
                """
                INSERT INTO menu_items
                (id, category_id, name, price, unit, note, allow_note, available, image)
                VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)
                ON CONFLICT(id) DO UPDATE SET
                  category_id=excluded.category_id,
                  name=excluded.name,
                  price=excluded.price,
                  unit=excluded.unit,
                  note=excluded.note,
                  allow_note=excluded.allow_note,
                  image=excluded.image,
                  available=1
                """,
                (
                    item["id"],
                    cat["id"],
                    item["name"],
                    float(item["price"]),
                    item.get("unit"),
                    item.get("note"),
                    1 if item.get("allow_note") else 0,
                    item.get("image"),
                ),
            )
    # Drop retired categories (e.g. old "wine") so guest tabs stay clean.
    if keep_cats:
        placeholders = ",".join("?" * len(keep_cats))
        conn.execute(
            f"DELETE FROM menu_categories WHERE id NOT IN ({placeholders})",
            keep_cats,
        )
    if keep_items:
        placeholders = ",".join("?" * len(keep_items))
        conn.execute(
            f"UPDATE menu_items SET available = 0 WHERE id NOT IN ({placeholders})",
            keep_items,
        )
    conn.commit()


def load_menu_meta() -> dict[str, Any]:
    return json.loads(MENU_PATH.read_text(encoding="utf-8"))


def get_table_by_code(conn: sqlite3.Connection, code: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM tables WHERE UPPER(code) = ? AND active = 1",
        (code.upper(),),
    ).fetchone()


def list_active_tables(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM tables WHERE active = 1 ORDER BY sort_order ASC, id ASC"
    ).fetchall()


def list_guest_tables(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Guest-facing seats only (exclude boss personal tabs)."""
    return conn.execute(
        """
        SELECT * FROM tables
        WHERE active = 1 AND COALESCE(zone, '') != 'boss'
        ORDER BY sort_order ASC, id ASC
        """
    ).fetchall()


def get_open_session(conn: sqlite3.Connection, table_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM sessions WHERE table_id = ? AND status = 'open' ORDER BY id DESC LIMIT 1",
        (table_id,),
    ).fetchone()


def start_session(
    conn: sqlite3.Connection,
    table_id: int,
    guest_name: str,
    party_size: int = 1,
) -> sqlite3.Row:
    """Create or refresh open session with guest name + party size."""
    name = (guest_name or "").strip()
    if not name:
        raise ValueError("Guest name required")
    size = max(1, int(party_size or 1))
    session = get_open_session(conn, table_id)
    if session:
        conn.execute(
            "UPDATE sessions SET guest_name = ?, party_size = ? WHERE id = ?",
            (name, size, session["id"]),
        )
        conn.commit()
        return get_open_session(conn, table_id)
    now = utc_now()
    cur = conn.execute(
        """
        INSERT INTO sessions (table_id, party_size, guest_name, status, opened_at)
        VALUES (?, ?, ?, 'open', ?)
        """,
        (table_id, size, name, now),
    )
    conn.commit()
    return conn.execute("SELECT * FROM sessions WHERE id = ?", (cur.lastrowid,)).fetchone()


def ensure_session(
    conn: sqlite3.Connection,
    table_id: int,
    party_size: int = 1,
    guest_name: str | None = None,
) -> sqlite3.Row:
    session = get_open_session(conn, table_id)
    if session:
        updates = []
        params: list[Any] = []
        if party_size and party_size != session["party_size"]:
            updates.append("party_size = ?")
            params.append(party_size)
        if guest_name and guest_name.strip() and guest_name.strip() != (session["guest_name"] or ""):
            updates.append("guest_name = ?")
            params.append(guest_name.strip())
        if updates:
            params.append(session["id"])
            conn.execute(
                f"UPDATE sessions SET {', '.join(updates)} WHERE id = ?",
                params,
            )
            conn.commit()
            session = get_open_session(conn, table_id)
        return session
    if not guest_name or not guest_name.strip():
        raise ValueError("Guest name required to open session")
    return start_session(conn, table_id, guest_name, party_size)


def publish_event(conn: sqlite3.Connection, kind: str, payload: dict[str, Any]) -> None:
    conn.execute(
        "INSERT INTO events (kind, payload, created_at) VALUES (?, ?, ?)",
        (kind, json.dumps(payload), utc_now()),
    )
    conn.commit()


def get_session(conn: sqlite3.Connection, session_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
