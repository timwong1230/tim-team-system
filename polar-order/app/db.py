from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from .paths import DB_PATH, MENU_PATH
from .seats import SEATS


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
        ("sessions", "payment_method", "TEXT"),
        ("sessions", "snack_waived", "INTEGER NOT NULL DEFAULT 0"),
        ("orders", "created_by", "TEXT"),
        ("orders", "deliver_table_id", "INTEGER"),
        ("orders", "gift_message", "TEXT"),
    ]
    for table, col, decl in migrations:
        if not _column_exists(conn, table, col):
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS claims (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_date TEXT NOT NULL,
            category TEXT NOT NULL,
            amount REAL NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
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
            payment_method TEXT,
            FOREIGN KEY(table_id) REFERENCES tables(id)
        );

        CREATE TABLE IF NOT EXISTS claims (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_date TEXT NOT NULL,
            category TEXT NOT NULL,
            amount REAL NOT NULL,
            created_at TEXT NOT NULL
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

        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guest_name TEXT NOT NULL,
            party_size INTEGER NOT NULL DEFAULT 2,
            booking_date TEXT NOT NULL,
            booking_time TEXT NOT NULL,
            note TEXT,
            status TEXT NOT NULL DEFAULT 'confirmed',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS daily_cash_tilt (
            business_date TEXT PRIMARY KEY,
            amount REAL NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL
        );
        """
    )
    conn.commit()
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_bookings_date
        ON bookings (booking_date, booking_time)
        """
    )
    conn.commit()
    _ensure_columns(conn)
    _rewrite_chinese_promo_notes(conn)
    _seed_tables(conn)
    sync_menu(conn)
    conn.close()


def _rewrite_chinese_promo_notes(conn: sqlite3.Connection) -> None:
    """Replace legacy Chinese discount tags baked into order line notes."""
    replacements = (
        ("[7折]", "[30% OFF]"),
        ("[8折]", "[20% OFF]"),
    )
    for old, new in replacements:
        conn.execute(
            "UPDATE order_items SET note = REPLACE(note, ?, ?) WHERE note LIKE ?",
            (old, new, f"%{old}%"),
        )
    conn.commit()


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
        return 10 + num  # 11-16
    if zone == "demo":
        return 30  # DEMO practice seat
    return 20 + num  # 21-29 terrace


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
    """Real guest seats only (exclude boss tabs and staff Demo practice seat)."""
    return conn.execute(
        """
        SELECT * FROM tables
        WHERE active = 1
          AND COALESCE(zone, '') NOT IN ('boss', 'demo')
        ORDER BY sort_order ASC, id ASC
        """
    ).fetchall()


def get_open_session(conn: sqlite3.Connection, table_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM sessions WHERE table_id = ? AND status = 'open' ORDER BY id DESC LIMIT 1",
        (table_id,),
    ).fetchone()


def transfer_open_session(
    conn: sqlite3.Connection,
    from_table_id: int,
    to_table_id: int,
) -> sqlite3.Row:
    """Move an open session and all its orders to another guest table."""
    if from_table_id == to_table_id:
        raise ValueError("Source and target table are the same")
    source = get_open_session(conn, from_table_id)
    if not source:
        raise ValueError("No open session on source table")
    if get_open_session(conn, to_table_id):
        raise ValueError("Target table already has an open session")
    conn.execute(
        "UPDATE sessions SET table_id = ? WHERE id = ?",
        (to_table_id, source["id"]),
    )
    conn.execute(
        "UPDATE orders SET table_id = ? WHERE session_id = ?",
        (to_table_id, source["id"]),
    )
    conn.commit()
    moved = get_open_session(conn, to_table_id)
    if not moved:
        raise RuntimeError("Transfer failed")
    return moved


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


def add_claim(
    conn: sqlite3.Connection,
    *,
    business_date: str,
    category: str,
    amount: float,
) -> sqlite3.Row:
    cur = conn.execute(
        """
        INSERT INTO claims (business_date, category, amount, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (business_date, category, float(amount), utc_now()),
    )
    conn.commit()
    return conn.execute("SELECT * FROM claims WHERE id = ?", (cur.lastrowid,)).fetchone()


def list_claims(conn: sqlite3.Connection, business_date: str) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            """
            SELECT * FROM claims
            WHERE business_date = ?
            ORDER BY id ASC
            """,
            (business_date,),
        ).fetchall()
    )


def delete_claim(conn: sqlite3.Connection, claim_id: int) -> bool:
    cur = conn.execute("DELETE FROM claims WHERE id = ?", (claim_id,))
    conn.commit()
    return cur.rowcount > 0


def list_bookings_for_month(
    conn: sqlite3.Connection,
    year: int,
    month: int,
    *,
    include_cancelled: bool = False,
) -> list[sqlite3.Row]:
    prefix = f"{year:04d}-{month:02d}"
    if include_cancelled:
        return list(
            conn.execute(
                """
                SELECT * FROM bookings
                WHERE booking_date LIKE ?
                ORDER BY booking_date ASC, booking_time ASC, id ASC
                """,
                (f"{prefix}%",),
            ).fetchall()
        )
    return list(
        conn.execute(
            """
            SELECT * FROM bookings
            WHERE booking_date LIKE ?
              AND status != 'cancelled'
            ORDER BY booking_date ASC, booking_time ASC, id ASC
            """,
            (f"{prefix}%",),
        ).fetchall()
    )


def list_bookings_for_date(
    conn: sqlite3.Connection,
    booking_date: str,
    *,
    include_cancelled: bool = False,
) -> list[sqlite3.Row]:
    if include_cancelled:
        return list(
            conn.execute(
                """
                SELECT * FROM bookings
                WHERE booking_date = ?
                ORDER BY booking_time ASC, id ASC
                """,
                (booking_date,),
            ).fetchall()
        )
    return list(
        conn.execute(
            """
            SELECT * FROM bookings
            WHERE booking_date = ?
              AND status != 'cancelled'
            ORDER BY booking_time ASC, id ASC
            """,
            (booking_date,),
        ).fetchall()
    )


def get_booking(conn: sqlite3.Connection, booking_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,)).fetchone()


def create_booking(
    conn: sqlite3.Connection,
    *,
    guest_name: str,
    party_size: int,
    booking_date: str,
    booking_time: str,
    note: str | None = None,
) -> sqlite3.Row:
    name = (guest_name or "").strip()
    if not name:
        raise ValueError("Guest name required")
    size = max(1, min(50, int(party_size or 1)))
    now = utc_now()
    cur = conn.execute(
        """
        INSERT INTO bookings (
            guest_name, party_size, booking_date, booking_time, note,
            status, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, 'confirmed', ?, ?)
        """,
        (name, size, booking_date, booking_time, (note or "").strip() or None, now, now),
    )
    conn.commit()
    row = get_booking(conn, int(cur.lastrowid))
    if not row:
        raise RuntimeError("Failed to create booking")
    return row


def update_booking(
    conn: sqlite3.Connection,
    booking_id: int,
    *,
    guest_name: str,
    party_size: int,
    booking_date: str,
    booking_time: str,
    note: str | None = None,
) -> sqlite3.Row:
    existing = get_booking(conn, booking_id)
    if not existing:
        raise ValueError("Booking not found")
    name = (guest_name or "").strip()
    if not name:
        raise ValueError("Guest name required")
    size = max(1, min(50, int(party_size or 1)))
    conn.execute(
        """
        UPDATE bookings SET
            guest_name = ?,
            party_size = ?,
            booking_date = ?,
            booking_time = ?,
            note = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (
            name,
            size,
            booking_date,
            booking_time,
            (note or "").strip() or None,
            utc_now(),
            booking_id,
        ),
    )
    conn.commit()
    row = get_booking(conn, booking_id)
    if not row:
        raise RuntimeError("Failed to update booking")
    return row


def get_cash_tilt(conn: sqlite3.Connection, business_date: str) -> float:
    row = conn.execute(
        "SELECT amount FROM daily_cash_tilt WHERE business_date = ?",
        (business_date,),
    ).fetchone()
    if not row:
        return 0.0
    return float(row["amount"] or 0)


def set_cash_tilt(conn: sqlite3.Connection, business_date: str, amount: float) -> float:
    value = max(0.0, float(amount or 0))
    conn.execute(
        """
        INSERT INTO daily_cash_tilt (business_date, amount, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(business_date) DO UPDATE SET
          amount = excluded.amount,
          updated_at = excluded.updated_at
        """,
        (business_date, value, utc_now()),
    )
    conn.commit()
    return value


def set_booking_status(
    conn: sqlite3.Connection,
    booking_id: int,
    status: str,
) -> sqlite3.Row:
    allowed = {"confirmed", "cancelled", "seated", "no_show"}
    if status not in allowed:
        raise ValueError("Invalid status")
    existing = get_booking(conn, booking_id)
    if not existing:
        raise ValueError("Booking not found")
    conn.execute(
        "UPDATE bookings SET status = ?, updated_at = ? WHERE id = ?",
        (status, utc_now(), booking_id),
    )
    conn.commit()
    row = get_booking(conn, booking_id)
    if not row:
        raise RuntimeError("Failed to update booking status")
    return row


def reset_operational_data(conn: sqlite3.Connection) -> dict[str, int]:
    """Wipe orders/sessions/events/claims/cash tilt/receipts. Keeps seats + menu + bookings."""
    from .paths import RECEIPT_DIR

    counts = {
        "order_items": conn.execute("SELECT COUNT(*) AS c FROM order_items").fetchone()["c"],
        "orders": conn.execute("SELECT COUNT(*) AS c FROM orders").fetchone()["c"],
        "sessions": conn.execute("SELECT COUNT(*) AS c FROM sessions").fetchone()["c"],
        "events": conn.execute("SELECT COUNT(*) AS c FROM events").fetchone()["c"],
        "claims": conn.execute("SELECT COUNT(*) AS c FROM claims").fetchone()["c"],
        "daily_cash_tilt": conn.execute(
            "SELECT COUNT(*) AS c FROM daily_cash_tilt"
        ).fetchone()["c"],
    }
    conn.execute("DELETE FROM order_items")
    conn.execute("DELETE FROM orders")
    conn.execute("DELETE FROM sessions")
    conn.execute("DELETE FROM events")
    conn.execute("DELETE FROM claims")
    conn.execute("DELETE FROM daily_cash_tilt")
    conn.execute(
        "DELETE FROM sqlite_sequence WHERE name IN "
        "('order_items','orders','sessions','events','claims')"
    )
    conn.commit()

    receipts_removed = 0
    RECEIPT_DIR.mkdir(parents=True, exist_ok=True)
    for path in RECEIPT_DIR.iterdir():
        if path.is_file():
            path.unlink()
            receipts_removed += 1
    counts["receipts"] = receipts_removed
    return counts
