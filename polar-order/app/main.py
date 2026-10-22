from __future__ import annotations

import asyncio
import io
import json
import os
import re
import sqlite3
from contextlib import asynccontextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import qrcode
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from .db import (
    connect,
    ensure_session,
    get_open_session,
    get_session,
    get_table_by_code,
    init_db,
    list_active_tables,
    list_guest_tables,
    load_menu_meta,
    publish_event,
    reset_operational_data,
    start_session,
    utc_now,
)
from .pricing import (
    SHISHA_COMBO_SNACK_PRICE,
    SHISHA_REGULAR_ID,
    business_date,
    compute_bill,
    current_promo,
    price_item,
    price_order_lines,
)
from .receipt import generate_receipt_pdf
from .reports import (
    daily_sales_report,
    item_purchase_report,
    monthly_boss_report,
    monthly_sales_report,
)
from .ai_host import ask_ai
from .paths import DATA_DIR, ROOT
from .seats import BOSSES, boss_by_id, boss_seat_code
from .spirits import spirit_serve_for

HK = ZoneInfo("Asia/Hong_Kong")

templates = Jinja2Templates(directory=str(ROOT / "templates"))

STAFF_PIN = os.getenv("POLAR_STAFF_PIN", "polar2026")
_subscribers: list[asyncio.Queue] = []


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    # One-shot cloud wipe: set POLAR_RESET_ON_START=RESET, deploy once, then remove the env var.
    if os.getenv("POLAR_RESET_ON_START", "").strip().upper() == "RESET":
        conn = connect()
        cleared = reset_operational_data(conn)
        conn.close()
        print(f"[polar] POLAR_RESET_ON_START wiped operational data: {cleared}", flush=True)
    yield


app = FastAPI(title="Polar Lounge Order", version="0.1.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(ROOT / "static")), name="static")


class CartItemIn(BaseModel):
    item_id: str
    qty: int = Field(ge=1, le=50)
    note: str | None = None
    # Not on Menu — staff/guest typed name + price
    custom_name: str | None = Field(default=None, max_length=80)
    custom_price: float | None = Field(default=None, ge=0, le=50000)


class StaffCustomIn(BaseModel):
    pin: str
    custom_name: str = Field(min_length=1, max_length=80)
    custom_price: float = Field(ge=0, le=50000)
    qty: int = Field(default=1, ge=1, le=50)
    note: str | None = None


class StaffOrderIn(BaseModel):
    """Staff places a full menu order on behalf of a guest table."""

    pin: str
    note: str | None = None
    items: list[CartItemIn]
    # Used when the table has no open session yet
    guest_name: str | None = Field(default=None, max_length=40)
    party_size: int | None = Field(default=None, ge=1, le=30)


class WelcomeIn(BaseModel):
    guest_name: str = Field(min_length=1, max_length=40)
    party_size: int = Field(default=2, ge=1, le=30)


class StaffPartyIn(BaseModel):
    pin: str
    party_size: int = Field(ge=1, le=30)


class OrderIn(BaseModel):
    note: str | None = None
    items: list[CartItemIn]
    party_size: int | None = Field(default=None, ge=1, le=30)
    # Order for HIM/HER — bill stays on this table; deliver to another seat
    deliver_to: str | None = None
    gift_message: str | None = Field(default=None, max_length=200)


class BossOrderIn(BaseModel):
    note: str | None = None
    items: list[CartItemIn]


class AskAIIn(BaseModel):
    message: str = Field(min_length=1, max_length=500)
    history: list[dict[str, str]] = Field(default_factory=list)


def _session_shisha_combo_slots(conn: sqlite3.Connection, session_id: int) -> int:
    """Unused shisha→$40 snack slots already earned in this open session."""
    shisha = conn.execute(
        """
        SELECT COALESCE(SUM(oi.qty), 0) AS c
        FROM order_items oi
        JOIN orders o ON o.id = oi.order_id
        WHERE o.session_id = ? AND o.status != 'cancelled'
          AND oi.item_id = ?
        """,
        (session_id, SHISHA_REGULAR_ID),
    ).fetchone()["c"]
    combo_snacks = conn.execute(
        """
        SELECT COALESCE(SUM(oi.qty), 0) AS c
        FROM order_items oi
        JOIN orders o ON o.id = oi.order_id
        WHERE o.session_id = ? AND o.status != 'cancelled'
          AND oi.category_id = 'snacks'
          AND oi.unit_price <= ?
        """,
        (session_id, SHISHA_COMBO_SNACK_PRICE),
    ).fetchone()["c"]
    return max(0, int(shisha) - int(combo_snacks))


def _serve_rank(unit: str | None) -> int:
    if unit == "Glass":
        return 0
    if unit == "Bottle":
        return 1
    return 2


def _menu_payload(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    promo = current_promo()
    cats = conn.execute(
        "SELECT * FROM menu_categories ORDER BY sort_order ASC"
    ).fetchall()
    out = []
    for cat in cats:
        items = conn.execute(
            "SELECT * FROM menu_items WHERE category_id = ? AND available = 1",
            (cat["id"],),
        ).fetchall()
        row_items = []
        for item in items:
            final, tag = price_item(
                float(item["price"]),
                cat["promo"],
                promo,
                item_id=item["id"],
            )
            serve = spirit_serve_for(cat["id"], item["unit"])
            row = {
                "id": item["id"],
                "name": item["name"],
                "price": float(item["price"]),
                "display_price": final,
                "unit": item["unit"],
                "note": item["note"],
                "allow_note": bool(item["allow_note"]),
                "promo_tag": tag,
                "image": item["image"],
                "promo_type": cat["promo"],
                "combo_price": None,
                "serve": serve,
                # legacy alias for templates during transition
                "mixer_options": serve["options"] if serve else None,
            }
            if cat["promo"] == "snacks":
                row["combo_price"] = SHISHA_COMBO_SNACK_PRICE
            row_items.append(row)
        row_items.sort(
            key=lambda r: (_serve_rank(r.get("unit")), (r["name"] or "").lower(), r["id"])
        )
        units = {r.get("unit") for r in row_items if r.get("unit")}
        out.append(
            {
                "id": cat["id"],
                "name": cat["name"],
                "promo": cat["promo"],
                "items": row_items,
                # Guest UI shows Glass / Bottle section headers when both exist.
                "split_serve": "Glass" in units and "Bottle" in units,
            }
        )
    return out


async def _broadcast(event: dict[str, Any]) -> None:
    dead = []
    for q in _subscribers:
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            dead.append(q)
    for q in dead:
        if q in _subscribers:
            _subscribers.remove(q)


def _create_order(
    conn: sqlite3.Connection,
    *,
    table: sqlite3.Row,
    session: sqlite3.Row,
    items: list[CartItemIn],
    note: str | None,
    created_by: str | None = None,
    deliver_table: sqlite3.Row | None = None,
    gift_message: str | None = None,
) -> tuple[int, dict[str, Any]]:
    if not items:
        raise HTTPException(400, "Cart is empty")
    promo = current_promo()
    now = utc_now()

    raw_entries = []
    for entry in items:
        custom_name = (entry.custom_name or "").strip()
        is_custom = (
            entry.item_id in ("not-on-menu", "custom", "nom")
            or bool(custom_name)
            or (entry.item_id or "").startswith("nom-")
        )
        if is_custom:
            if not custom_name:
                raise HTTPException(400, "Not on Menu needs a product name")
            if entry.custom_price is None:
                raise HTTPException(400, "Not on Menu needs a price")
            price = round(float(entry.custom_price), 1)
            if price < 0:
                raise HTTPException(400, "Invalid price")
            slug = re.sub(r"[^a-z0-9]+", "-", custom_name.lower()).strip("-")[:40] or "item"
            raw_entries.append(
                {
                    "item_id": f"nom-{slug}",
                    "name": custom_name,
                    "category_id": "not-on-menu",
                    "promo": "none",
                    "base_price": price,
                    "qty": entry.qty,
                    "note": entry.note,
                }
            )
            continue

        item = conn.execute(
            """
            SELECT mi.*, mc.promo AS promo
            FROM menu_items mi
            JOIN menu_categories mc ON mc.id = mi.category_id
            WHERE mi.id = ? AND mi.available = 1
            """,
            (entry.item_id,),
        ).fetchone()
        if not item:
            raise HTTPException(400, f"Unknown item: {entry.item_id}")
        raw_entries.append(
            {
                "item_id": item["id"],
                "name": item["name"],
                "category_id": item["category_id"],
                "promo": item["promo"],
                "base_price": float(item["price"]),
                "qty": entry.qty,
                "note": entry.note,
            }
        )

    extra_slots = _session_shisha_combo_slots(conn, session["id"])
    priced_lines = price_order_lines(
        raw_entries, promo=promo, extra_shisha_slots=extra_slots
    )

    deliver_id = deliver_table["id"] if deliver_table else None
    gift = (gift_message or "").strip() or None
    if gift and len(gift) > 200:
        gift = gift[:200]

    cur = conn.execute(
        """
        INSERT INTO orders
        (session_id, table_id, status, note, created_at, updated_at, created_by,
         deliver_table_id, gift_message)
        VALUES (?, ?, 'new', ?, ?, ?, ?, ?, ?)
        """,
        (
            session["id"],
            table["id"],
            note,
            now,
            now,
            created_by,
            deliver_id,
            gift,
        ),
    )
    order_id = cur.lastrowid
    lines = []
    for row in priced_lines:
        conn.execute(
            """
            INSERT INTO order_items
            (order_id, item_id, item_name, category_id, promo, qty, unit_price, line_total, note)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                order_id,
                row["item_id"],
                row["item_name"],
                row["category_id"],
                row["promo"],
                row["qty"],
                row["unit_price"],
                row["line_total"],
                row.get("note"),
            ),
        )
        lines.append(
            {
                "name": row["item_name"],
                "qty": row["qty"],
                "line_total": row["line_total"],
            }
        )

    guest_name = session["guest_name"] if "guest_name" in session.keys() else None
    payload = {
        "order_id": order_id,
        "table_code": table["code"],
        "table_label": table["label"],
        "guest_name": guest_name,
        "created_by": created_by,
        "deliver_to_code": deliver_table["code"] if deliver_table else None,
        "deliver_to_label": deliver_table["label"] if deliver_table else None,
        "gift_message": gift,
        "items": lines,
        "created_at": now,
    }
    publish_event(conn, "order.new", payload)
    conn.commit()
    return order_id, payload


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(
        "home.html",
        {"request": request, "title": "Polar Lounge Order", "bosses": BOSSES},
    )


@app.get("/t/{table_code}", response_class=HTMLResponse)
def guest_table(request: Request, table_code: str):
    conn = connect()
    table = get_table_by_code(conn, table_code)
    if not table:
        conn.close()
        raise HTTPException(404, "Table not found")
    if (table["zone"] or "") == "boss":
        conn.close()
        # Boss tabs are not guest QR seats
        boss_id = table_code.replace("BOSS", "").lower()
        return RedirectResponse(url=f"/boss/{boss_id}", status_code=302)
    session = get_open_session(conn, table["id"])
    ready = bool(session and session["guest_name"])
    menu = _menu_payload(conn) if ready else []
    promo = current_promo()
    other_seats = []
    if ready:
        for t in list_guest_tables(conn):
            if t["id"] == table["id"]:
                continue
            other_seats.append({"code": t["code"], "label": t["label"]})
    conn.close()
    return templates.TemplateResponse(
        "guest.html",
        {
            "request": request,
            "table": table,
            "session": session,
            "menu": menu,
            "promo": promo,
            "ready": ready,
            "other_seats": other_seats,
            "title": f"Polar · {table['label']}",
        },
    )


@app.post("/api/t/{table_code}/welcome")
def guest_welcome(table_code: str, body: WelcomeIn):
    conn = connect()
    table = get_table_by_code(conn, table_code)
    if not table:
        conn.close()
        raise HTTPException(404, "Table not found")
    try:
        session = start_session(
            conn, table["id"], body.guest_name.strip(), body.party_size
        )
    except ValueError as e:
        conn.close()
        raise HTTPException(400, str(e)) from e
    conn.close()
    return {
        "ok": True,
        "session_id": session["id"],
        "guest_name": session["guest_name"],
        "party_size": session["party_size"],
    }


@app.get("/api/t/{table_code}/my-orders")
def guest_my_orders(table_code: str):
    """What this table has already sent — product + qty only (no prices)."""
    conn = connect()
    table = get_table_by_code(conn, table_code)
    if not table:
        conn.close()
        raise HTTPException(404, "Table not found")
    if (table["zone"] or "") == "boss":
        conn.close()
        raise HTTPException(400, "Boss station — use boss tab")
    session = get_open_session(conn, table["id"])
    if not session or not session["guest_name"]:
        conn.close()
        return {"ok": True, "items": [], "orders": []}

    rows = conn.execute(
        """
        SELECT oi.item_name, oi.qty, oi.note, o.id AS order_id, o.status, o.created_at
        FROM order_items oi
        JOIN orders o ON o.id = oi.order_id
        WHERE o.session_id = ? AND o.status != 'cancelled'
        ORDER BY o.id ASC, oi.id ASC
        """,
        (session["id"],),
    ).fetchall()
    conn.close()

    orders_map: dict[int, dict[str, Any]] = {}
    summary: dict[str, int] = {}
    for r in rows:
        oid = int(r["order_id"])
        if oid not in orders_map:
            orders_map[oid] = {
                "id": oid,
                "status": r["status"],
                "created_at": r["created_at"],
                "items": [],
            }
        name = r["item_name"]
        qty = int(r["qty"])
        note = (r["note"] or "").strip() or None
        # Strip baked-in promo tags like [30% OFF] from guest-facing note
        if note and note.startswith("[") and "]" in note:
            after = note.split("]", 1)[1].strip()
            note = after or None
        orders_map[oid]["items"].append({"name": name, "qty": qty, "note": note})
        summary[name] = summary.get(name, 0) + qty

    items = [{"name": n, "qty": q} for n, q in summary.items()]
    return {
        "ok": True,
        "items": items,
        "orders": list(orders_map.values()),
    }


@app.post("/api/t/{table_code}/orders")
async def place_order(table_code: str, body: OrderIn):
    conn = connect()
    table = get_table_by_code(conn, table_code)
    if not table:
        conn.close()
        raise HTTPException(404, "Table not found")
    if (table["zone"] or "") == "boss":
        conn.close()
        raise HTTPException(400, "Use boss station to order")

    session = get_open_session(conn, table["id"])
    if not session or not session["guest_name"]:
        conn.close()
        raise HTTPException(400, "Please enter your name and party size first")

    if body.party_size and body.party_size != session["party_size"]:
        session = ensure_session(
            conn,
            table["id"],
            party_size=body.party_size,
            guest_name=session["guest_name"],
        )

    deliver_table = None
    gift = (body.gift_message or "").strip() or None
    if body.deliver_to:
        deliver_table = get_table_by_code(conn, body.deliver_to)
        if not deliver_table or (deliver_table["zone"] or "") in ("boss", "demo"):
            conn.close()
            raise HTTPException(400, "Invalid delivery seat")
        if deliver_table["id"] == table["id"]:
            conn.close()
            raise HTTPException(400, "Pick a different seat to treat")
        if not gift:
            conn.close()
            raise HTTPException(400, "Add a short message for them")

    try:
        order_id, payload = _create_order(
            conn,
            table=table,
            session=session,
            items=body.items,
            note=body.note,
            created_by=None,
            deliver_table=deliver_table,
            gift_message=gift,
        )
    except HTTPException:
        conn.close()
        raise
    conn.close()
    await _broadcast({"type": "order.new", "data": payload})
    return {"ok": True, "order_id": order_id}


@app.post("/api/t/{table_code}/ask-ai")
def guest_ask_ai(table_code: str, body: AskAIIn):
    conn = connect()
    table = get_table_by_code(conn, table_code)
    if not table or (table["zone"] or "") == "boss":
        conn.close()
        raise HTTPException(404, "Table not found")
    session = get_open_session(conn, table["id"])
    guest_name = session["guest_name"] if session else None
    result = ask_ai(
        conn,
        message=body.message.strip(),
        history=body.history,
        guest_name=guest_name,
    )
    conn.close()
    return {"ok": True, **result}


@app.get("/boss", response_class=HTMLResponse)
def boss_home(request: Request):
    return templates.TemplateResponse(
        "boss_home.html",
        {"request": request, "title": "Boss order", "bosses": BOSSES},
    )


@app.get("/boss/{boss_id}", response_class=HTMLResponse)
def boss_station(request: Request, boss_id: str):
    boss = boss_by_id(boss_id)
    if not boss:
        raise HTTPException(404, "Boss not found")
    seat_code = boss_seat_code(boss_id)
    conn = connect()
    table = get_table_by_code(conn, seat_code) if seat_code else None
    if not table:
        conn.close()
        raise HTTPException(500, "Boss seat not seeded")
    # Keep an open personal tab so staff can see running total
    start_session(conn, table["id"], boss["name"], party_size=1)
    menu = _menu_payload(conn)
    promo = current_promo()
    conn.close()
    return templates.TemplateResponse(
        "boss_order.html",
        {
            "request": request,
            "title": f"{boss['name']} · Order",
            "boss": boss,
            "seat_code": table["code"],
            "menu": menu,
            "promo": promo,
        },
    )


@app.post("/api/boss/{boss_id}/orders")
async def boss_place_order(boss_id: str, body: BossOrderIn):
    boss = boss_by_id(boss_id)
    if not boss:
        raise HTTPException(404, "Boss not found")
    if not body.items:
        raise HTTPException(400, "Cart is empty")
    seat_code = boss_seat_code(boss_id)
    conn = connect()
    table = get_table_by_code(conn, seat_code) if seat_code else None
    if not table:
        conn.close()
        raise HTTPException(500, "Boss seat not seeded")
    try:
        session = start_session(conn, table["id"], boss["name"], party_size=1)
        order_id, payload = _create_order(
            conn,
            table=table,
            session=session,
            items=body.items,
            note=body.note,
            created_by=boss["name"],
        )
    except ValueError as e:
        conn.close()
        raise HTTPException(400, str(e)) from e
    except HTTPException:
        conn.close()
        raise
    conn.close()
    await _broadcast({"type": "order.new", "data": payload})
    return {"ok": True, "order_id": order_id, "created_by": boss["name"]}


@app.get("/staff", response_class=HTMLResponse)
def staff_login_page(request: Request):
    return templates.TemplateResponse(
        "staff_login.html",
        {"request": request, "title": "Staff Login"},
    )


@app.post("/staff")
def staff_login(request: Request, pin: str = Form(...)):
    if pin.strip() != STAFF_PIN:
        return templates.TemplateResponse(
            "staff_login.html",
            {"request": request, "title": "Staff Login", "error": "Wrong PIN"},
            status_code=401,
        )
    return RedirectResponse(url=f"/staff/board?pin={STAFF_PIN}", status_code=303)


@app.get("/staff/board", response_class=HTMLResponse)
def staff_board(request: Request, pin: str = ""):
    if pin != STAFF_PIN:
        return HTMLResponse("Unauthorized", status_code=401)
    return templates.TemplateResponse(
        "staff.html",
        {"request": request, "title": "Staff · Orders", "pin": pin},
    )


@app.get("/api/staff/orders")
def staff_orders(pin: str = ""):
    if pin != STAFF_PIN:
        raise HTTPException(401, "Unauthorized")
    conn = connect()
    orders = conn.execute(
        """
        SELECT o.*, t.code AS table_code, t.label AS table_label,
               s.guest_name AS guest_name,
               dt.code AS deliver_to_code, dt.label AS deliver_to_label
        FROM orders o
        JOIN tables t ON t.id = o.table_id
        JOIN sessions s ON s.id = o.session_id
        LEFT JOIN tables dt ON dt.id = o.deliver_table_id
        WHERE o.status IN ('new', 'preparing', 'ready')
        ORDER BY
          CASE o.status WHEN 'new' THEN 0 WHEN 'preparing' THEN 1 ELSE 2 END,
          o.id ASC
        """
    ).fetchall()
    result = []
    for o in orders:
        items = conn.execute(
            "SELECT * FROM order_items WHERE order_id = ? ORDER BY id ASC",
            (o["id"],),
        ).fetchall()
        result.append(
            {
                "id": o["id"],
                "status": o["status"],
                "table_code": o["table_code"],
                "table_label": o["table_label"],
                "guest_name": o["guest_name"],
                "created_by": o["created_by"],
                "note": o["note"],
                "created_at": o["created_at"],
                "deliver_to_code": o["deliver_to_code"],
                "deliver_to_label": o["deliver_to_label"],
                "gift_message": o["gift_message"],
                "items": [dict(i) for i in items],
            }
        )
    conn.close()
    return result


@app.post("/api/staff/orders/{order_id}/status")
async def update_order_status(order_id: int, status: str = Form(...), pin: str = Form(...)):
    if pin != STAFF_PIN:
        raise HTTPException(401, "Unauthorized")
    if status not in {"new", "preparing", "ready", "served", "cancelled"}:
        raise HTTPException(400, "Invalid status")
    conn = connect()
    order = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    if not order:
        conn.close()
        raise HTTPException(404, "Order not found")
    now = utc_now()
    conn.execute(
        "UPDATE orders SET status = ?, updated_at = ? WHERE id = ?",
        (status, now, order_id),
    )
    table = conn.execute("SELECT * FROM tables WHERE id = ?", (order["table_id"],)).fetchone()
    payload = {
        "order_id": order_id,
        "status": status,
        "table_code": table["code"] if table else None,
    }
    publish_event(conn, "order.status", payload)
    conn.commit()
    conn.close()
    await _broadcast({"type": "order.status", "data": payload})
    return {"ok": True}


@app.get("/staff/tables", response_class=HTMLResponse)
def staff_tables(request: Request, pin: str = ""):
    if pin != STAFF_PIN:
        return HTMLResponse("Unauthorized — open from Staff board", status_code=401)
    conn = connect()
    tables = list_active_tables(conn)
    rows = []
    demo_rows = []
    boss_rows = []
    meta = load_menu_meta()
    for t in tables:
        session = get_open_session(conn, t["id"])
        bill = None
        open_orders = 0
        zone = t["zone"] or ""
        if session:
            lines = conn.execute(
                """
                SELECT oi.*
                FROM order_items oi
                JOIN orders o ON o.id = oi.order_id
                WHERE o.session_id = ? AND o.status != 'cancelled'
                """,
                (session["id"],),
            ).fetchall()
            open_orders = conn.execute(
                """
                SELECT COUNT(*) AS c FROM orders
                WHERE session_id = ? AND status IN ('new','preparing','ready')
                """,
                (session["id"],),
            ).fetchone()["c"]
            # Boss tabs: show product total only (no guest snack/service)
            if zone == "boss":
                prod = round(sum(float(x["line_total"]) for x in lines), 1)
                bill = {
                    "total": prod,
                    "subtotal": prod,
                    "snack_charge": 0,
                    "service_charge": 0,
                    "discount_amount": 0,
                    "discount_percent": 0,
                    "party_size": 1,
                    "service_charge_rate": 0,
                }
            else:
                bill = compute_bill(
                    [dict(x) for x in lines],
                    session["party_size"],
                    meta["service_charge_rate"],
                    meta["snack_charge_per_head"],
                )
        entry = {
            "table": t,
            "session": session,
            "bill": bill,
            "open_orders": open_orders,
            "is_boss": zone == "boss",
            "is_demo": zone == "demo",
        }
        if entry["is_boss"]:
            boss_rows.append(entry)
        elif entry["is_demo"]:
            demo_rows.append(entry)
        else:
            rows.append(entry)
    conn.close()
    return templates.TemplateResponse(
        "staff_tables.html",
        {
            "request": request,
            "title": "Staff · Seats",
            "rows": rows,
            "demo_rows": demo_rows,
            "boss_rows": boss_rows,
            "pin": pin,
        },
    )


def _session_lines(conn: sqlite3.Connection, session_id: int) -> list[dict]:
    return [
        dict(x)
        for x in conn.execute(
            """
            SELECT oi.*, o.id AS order_id, o.created_at
            FROM order_items oi
            JOIN orders o ON o.id = oi.order_id
            WHERE o.session_id = ? AND o.status != 'cancelled'
            ORDER BY o.id ASC, oi.id ASC
            """,
            (session_id,),
        ).fetchall()
    ]


@app.get("/staff/order/{table_code}", response_class=HTMLResponse)
def staff_order_page(request: Request, table_code: str, pin: str = ""):
    """Staff menu — order for a guest table (not the guest QR phone)."""
    if pin != STAFF_PIN:
        return HTMLResponse("Unauthorized", status_code=401)
    conn = connect()
    table = get_table_by_code(conn, table_code)
    if not table:
        conn.close()
        raise HTTPException(404, "Table not found")
    if (table["zone"] or "") == "boss":
        conn.close()
        # Boss personal tabs use /boss/{id}
        boss_id = table_code.replace("BOSS", "").lower()
        return RedirectResponse(url=f"/boss/{boss_id}", status_code=302)
    session = get_open_session(conn, table["id"])
    menu = _menu_payload(conn)
    promo = current_promo()
    conn.close()
    return templates.TemplateResponse(
        "staff_order.html",
        {
            "request": request,
            "title": f"Order · {table['label']}",
            "table": table,
            "session": session,
            "menu": menu,
            "promo": promo,
            "pin": pin,
            "needs_checkin": not bool(session and session["guest_name"]),
        },
    )


@app.get("/staff/bill/{table_code}", response_class=HTMLResponse)
def staff_bill(request: Request, table_code: str, pin: str = "", discount: float = 0):
    if pin != STAFF_PIN:
        return HTMLResponse("Unauthorized", status_code=401)
    conn = connect()
    table = get_table_by_code(conn, table_code)
    if not table:
        conn.close()
        raise HTTPException(404, "Table not found")
    session = get_open_session(conn, table["id"])
    meta = load_menu_meta()
    lines: list[dict] = []
    bill = None
    is_boss = (table["zone"] or "") == "boss"
    if session:
        lines = _session_lines(conn, session["id"])
        if is_boss:
            prod = round(sum(float(x["line_total"]) for x in lines), 1)
            bill = {
                "total": prod,
                "subtotal": prod,
                "snack_charge": 0,
                "service_charge": 0,
                "discount_amount": 0,
                "discount_percent": 0,
                "party_size": 1,
                "service_charge_rate": 0,
            }
        else:
            bill = compute_bill(
                lines,
                session["party_size"],
                meta["service_charge_rate"],
                meta["snack_charge_per_head"],
                discount_percent=discount,
            )
    conn.close()
    return templates.TemplateResponse(
        "staff_bill.html",
        {
            "request": request,
            "title": f"Bill · {table['label']}",
            "table": table,
            "session": session,
            "lines": lines,
            "bill": bill,
            "pin": pin,
            "discount": discount or 0,
            "is_boss": is_boss,
            "snack_per_head": meta["snack_charge_per_head"],
        },
    )


@app.post("/api/staff/bill/{table_code}/party")
def staff_update_party(table_code: str, body: StaffPartyIn):
    """Staff confirms / corrects party size before close (affects snack charge)."""
    if body.pin != STAFF_PIN:
        raise HTTPException(401, "Unauthorized")
    conn = connect()
    table = get_table_by_code(conn, table_code)
    if not table:
        conn.close()
        raise HTTPException(404, "Table not found")
    if (table["zone"] or "") == "boss":
        conn.close()
        return {"ok": True, "party_size": 1, "bill": None}
    session = get_open_session(conn, table["id"])
    if not session:
        conn.close()
        raise HTTPException(400, "No open session")
    size = max(1, min(30, int(body.party_size)))
    conn.execute(
        "UPDATE sessions SET party_size = ? WHERE id = ?",
        (size, session["id"]),
    )
    conn.commit()
    session = get_open_session(conn, table["id"])
    meta = load_menu_meta()
    lines = _session_lines(conn, session["id"])
    bill = compute_bill(
        lines,
        session["party_size"],
        meta["service_charge_rate"],
        meta["snack_charge_per_head"],
        discount_percent=0,
    )
    conn.close()
    return {
        "ok": True,
        "party_size": session["party_size"],
        "guest_name": session["guest_name"],
        "bill": bill,
    }


@app.post("/api/staff/bill/{table_code}/custom")
async def staff_add_custom(table_code: str, body: StaffCustomIn):
    """Staff adds a Not on Menu line to the open session."""
    if body.pin != STAFF_PIN:
        raise HTTPException(401, "Unauthorized")
    conn = connect()
    table = get_table_by_code(conn, table_code)
    if not table:
        conn.close()
        raise HTTPException(404, "Table not found")
    session = get_open_session(conn, table["id"])
    if not session:
        conn.close()
        raise HTTPException(400, "No open session — guest must check in first")
    try:
        order_id, payload = _create_order(
            conn,
            table=table,
            session=session,
            items=[
                CartItemIn(
                    item_id="not-on-menu",
                    qty=body.qty,
                    note=body.note,
                    custom_name=body.custom_name.strip(),
                    custom_price=body.custom_price,
                )
            ],
            note="Not on Menu (staff)",
            created_by="Staff",
        )
    except HTTPException:
        conn.close()
        raise
    conn.close()
    await _broadcast({"type": "order.new", "data": payload})
    return {"ok": True, "order_id": order_id}


@app.post("/api/staff/bill/{table_code}/orders")
async def staff_place_order(table_code: str, body: StaffOrderIn):
    """Staff places a full menu order for a customer table."""
    if body.pin != STAFF_PIN:
        raise HTTPException(401, "Unauthorized")
    if not body.items:
        raise HTTPException(400, "Cart is empty")
    conn = connect()
    table = get_table_by_code(conn, table_code)
    if not table:
        conn.close()
        raise HTTPException(404, "Table not found")
    if (table["zone"] or "") == "boss":
        conn.close()
        raise HTTPException(400, "Use boss station to order for boss tabs")

    session = get_open_session(conn, table["id"])
    if not session or not session["guest_name"]:
        name = (body.guest_name or "").strip() or "Walk-in"
        party = int(body.party_size or 2)
        try:
            session = start_session(conn, table["id"], name, party_size=party)
        except ValueError as e:
            conn.close()
            raise HTTPException(400, str(e)) from e
    elif body.party_size and body.party_size != session["party_size"]:
        session = ensure_session(
            conn,
            table["id"],
            party_size=body.party_size,
            guest_name=session["guest_name"],
        )

    try:
        order_id, payload = _create_order(
            conn,
            table=table,
            session=session,
            items=body.items,
            note=body.note,
            created_by="Staff",
        )
    except HTTPException:
        conn.close()
        raise
    conn.close()
    await _broadcast({"type": "order.new", "data": payload})
    return {
        "ok": True,
        "order_id": order_id,
        "created_by": "Staff",
        "guest_name": session["guest_name"],
        "party_size": session["party_size"],
    }


@app.post("/api/staff/bill/{table_code}/close")
def close_bill(
    table_code: str,
    pin: str = Form(...),
    discount_percent: float = Form(0),
    party_size: int | None = Form(None),
):
    if pin != STAFF_PIN:
        raise HTTPException(401, "Unauthorized")
    conn = connect()
    table = get_table_by_code(conn, table_code)
    if not table:
        conn.close()
        raise HTTPException(404, "Table not found")
    session = get_open_session(conn, table["id"])
    if not session:
        conn.close()
        return {"ok": True, "message": "No open session"}

    is_boss = (table["zone"] or "") == "boss"
    if not is_boss and party_size is not None:
        size = max(1, min(30, int(party_size)))
        conn.execute(
            "UPDATE sessions SET party_size = ? WHERE id = ?",
            (size, session["id"]),
        )
        conn.commit()
        session = get_open_session(conn, table["id"])

    meta = load_menu_meta()
    lines = _session_lines(conn, session["id"])
    if is_boss:
        prod = round(sum(float(x["line_total"]) for x in lines), 1)
        bill = {
            "total": prod,
            "subtotal": prod,
            "snack_charge": 0,
            "service_charge": 0,
            "discount_amount": 0,
            "discount_percent": 0,
            "party_size": 1,
            "service_charge_rate": 0,
        }
    else:
        bill = compute_bill(
            lines,
            session["party_size"],
            meta["service_charge_rate"],
            meta["snack_charge_per_head"],
            discount_percent=discount_percent,
        )
    now = utc_now()
    biz = business_date(datetime.now(HK)).isoformat()
    guest_name = session["guest_name"] if session["guest_name"] else None
    receipt_rel = generate_receipt_pdf(
        session_id=session["id"],
        table_label=table["label"],
        party_size=session["party_size"] if not is_boss else 1,
        lines=lines,
        bill=bill,
        closed_at_iso=now,
        guest_name=guest_name,
    )
    conn.execute(
        """
        UPDATE sessions SET
          status = 'closed',
          closed_at = ?,
          discount_percent = ?,
          subtotal = ?,
          snack_charge = ?,
          service_charge = ?,
          discount_amount = ?,
          total = ?,
          receipt_path = ?,
          business_date = ?
        WHERE id = ?
        """,
        (
            now,
            bill["discount_percent"],
            bill["subtotal"],
            bill["snack_charge"],
            bill["service_charge"],
            bill["discount_amount"],
            bill["total"],
            receipt_rel,
            biz,
            session["id"],
        ),
    )
    conn.execute(
        "UPDATE orders SET status = 'served', updated_at = ? WHERE session_id = ? AND status != 'cancelled'",
        (now, session["id"]),
    )
    conn.commit()
    conn.close()
    return {
        "ok": True,
        "session_id": session["id"],
        "total": bill["total"],
        "receipt_url": f"/staff/receipt/{session['id']}?pin={pin}",
    }


@app.get("/staff/receipt/{session_id}")
def staff_receipt(session_id: int, pin: str = ""):
    if pin != STAFF_PIN:
        raise HTTPException(401, "Unauthorized")
    conn = connect()
    session = get_session(conn, session_id)
    conn.close()
    if not session or not session["receipt_path"]:
        raise HTTPException(404, "Receipt not found")
    # New receipts live under DATA_DIR; keep ROOT fallback for older rows.
    rel = session["receipt_path"]
    path = DATA_DIR / rel
    if not path.exists():
        path = ROOT / rel
    if not path.exists():
        raise HTTPException(404, "Receipt file missing")
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=f"Polar-Receipt-S{session_id}.pdf",
    )


@app.get("/staff/qrs", response_class=HTMLResponse)
def staff_qrs(request: Request, pin: str = ""):
    if pin != STAFF_PIN:
        return HTMLResponse("Unauthorized", status_code=401)
    conn = connect()
    tables = list_guest_tables(conn)
    conn.close()
    base = str(request.base_url).rstrip("/")
    boss_links = [
        {
            "id": b["id"],
            "name": b["name"],
            "url": f"{base}/boss/{b['id']}",
            "qr": f"/qr/boss/{b['id']}.png",
        }
        for b in BOSSES
    ]
    return templates.TemplateResponse(
        "staff_qrs.html",
        {
            "request": request,
            "title": "Seat QR Codes",
            "tables": tables,
            "boss_links": boss_links,
            "base": base,
            "pin": pin,
        },
    )


@app.get("/qr/{table_code}.png")
def qr_png(request: Request, table_code: str):
    conn = connect()
    table = get_table_by_code(conn, table_code)
    conn.close()
    if not table:
        raise HTTPException(404, "Table not found")
    url = str(request.base_url).rstrip("/") + f"/t/{table['code']}"
    img = qrcode.make(url)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/png")


@app.get("/qr/boss/{boss_id}.png")
def boss_qr_png(request: Request, boss_id: str):
    boss = boss_by_id(boss_id)
    if not boss:
        raise HTTPException(404, "Boss not found")
    url = str(request.base_url).rstrip("/") + f"/boss/{boss['id']}"
    img = qrcode.make(url)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/png")


@app.get("/api/events")
async def sse_events(pin: str = ""):
    if pin != STAFF_PIN:
        raise HTTPException(401, "Unauthorized")
    queue: asyncio.Queue = asyncio.Queue(maxsize=50)
    _subscribers.append(queue)

    async def gen():
        try:
            yield f"data: {json.dumps({'type': 'hello'})}\n\n"
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=20)
                    yield f"data: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    yield f"data: {json.dumps({'type': 'ping'})}\n\n"
        finally:
            if queue in _subscribers:
                _subscribers.remove(queue)

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.get("/staff/reports", response_class=HTMLResponse)
def staff_reports(request: Request, pin: str = "", day: str = "", month: str = ""):
    if pin != STAFF_PIN:
        return HTMLResponse("Unauthorized", status_code=401)
    today_biz = business_date(datetime.now(HK))
    if day:
        try:
            biz = date.fromisoformat(day)
        except ValueError:
            biz = today_biz
    else:
        biz = today_biz

    if month:
        try:
            y_str, m_str = month.split("-")
            year, mon = int(y_str), int(m_str)
        except Exception:
            year, mon = today_biz.year, today_biz.month
    else:
        year, mon = today_biz.year, today_biz.month

    conn = connect()
    daily = daily_sales_report(conn, biz)
    monthly = monthly_sales_report(conn, year, mon)
    items = item_purchase_report(conn, year=year, month=mon)
    bosses = monthly_boss_report(conn, year, mon)
    conn.close()
    return templates.TemplateResponse(
        "staff_reports.html",
        {
            "request": request,
            "title": "Reports",
            "pin": pin,
            "daily": daily,
            "monthly": monthly,
            "items": items,
            "bosses": bosses,
            "day": biz.isoformat(),
            "month": f"{year}-{mon:02d}",
        },
    )


@app.post("/api/staff/reset-sales")
def staff_reset_sales(pin: str = Form(...), confirm: str = Form("")):
    """Wipe all guest/boss orders, sessions, events, and receipts (menu/seats kept)."""
    if pin != STAFF_PIN:
        raise HTTPException(401, "Unauthorized")
    if (confirm or "").strip().upper() != "RESET":
        raise HTTPException(400, "Type RESET to confirm")
    conn = connect()
    counts = reset_operational_data(conn)
    conn.close()
    return {"ok": True, "cleared": counts}


@app.get("/health")
def health():
    return {"ok": True, "promo": current_promo()}
