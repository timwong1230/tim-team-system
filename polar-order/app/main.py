from __future__ import annotations

import asyncio
import io
import json
import os
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
    load_menu_meta,
    publish_event,
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
from .reports import daily_sales_report, item_purchase_report, monthly_sales_report
from .seats import BOSSES, boss_by_id

HK = ZoneInfo("Asia/Hong_Kong")

ROOT = Path(__file__).resolve().parents[1]
templates = Jinja2Templates(directory=str(ROOT / "templates"))

STAFF_PIN = os.getenv("POLAR_STAFF_PIN", "polar2026")
_subscribers: list[asyncio.Queue] = []


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="Polar Lounge Order", version="0.1.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(ROOT / "static")), name="static")


class CartItemIn(BaseModel):
    item_id: str
    qty: int = Field(ge=1, le=50)
    note: str | None = None


class WelcomeIn(BaseModel):
    guest_name: str = Field(min_length=1, max_length=40)
    party_size: int = Field(default=2, ge=1, le=30)


class OrderIn(BaseModel):
    note: str | None = None
    items: list[CartItemIn]
    party_size: int | None = Field(default=None, ge=1, le=30)


class BossOrderIn(BaseModel):
    table_code: str
    guest_name: str = Field(min_length=1, max_length=40)
    party_size: int = Field(default=2, ge=1, le=30)
    note: str | None = None
    items: list[CartItemIn]


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


def _menu_payload(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    promo = current_promo()
    cats = conn.execute(
        "SELECT * FROM menu_categories ORDER BY sort_order ASC"
    ).fetchall()
    out = []
    for cat in cats:
        items = conn.execute(
            "SELECT * FROM menu_items WHERE category_id = ? AND available = 1 ORDER BY name ASC",
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
            }
            if cat["promo"] == "snacks":
                row["combo_price"] = SHISHA_COMBO_SNACK_PRICE
            row_items.append(row)
        out.append(
            {
                "id": cat["id"],
                "name": cat["name"],
                "promo": cat["promo"],
                "items": row_items,
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
) -> tuple[int, dict[str, Any]]:
    if not items:
        raise HTTPException(400, "Cart is empty")
    promo = current_promo()
    now = utc_now()

    raw_entries = []
    for entry in items:
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

    cur = conn.execute(
        """
        INSERT INTO orders (session_id, table_id, status, note, created_at, updated_at, created_by)
        VALUES (?, ?, 'new', ?, ?, ?, ?)
        """,
        (session["id"], table["id"], note, now, now, created_by),
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
    session = get_open_session(conn, table["id"])
    ready = bool(session and session["guest_name"])
    menu = _menu_payload(conn) if ready else []
    promo = current_promo()
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


@app.post("/api/t/{table_code}/orders")
async def place_order(table_code: str, body: OrderIn):
    conn = connect()
    table = get_table_by_code(conn, table_code)
    if not table:
        conn.close()
        raise HTTPException(404, "Table not found")

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

    try:
        order_id, payload = _create_order(
            conn,
            table=table,
            session=session,
            items=body.items,
            note=body.note,
            created_by=None,
        )
    except HTTPException:
        conn.close()
        raise
    conn.close()
    await _broadcast({"type": "order.new", "data": payload})
    return {"ok": True, "order_id": order_id}


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
    conn = connect()
    tables = list_active_tables(conn)
    seat_rows = []
    for t in tables:
        session = get_open_session(conn, t["id"])
        seat_rows.append(
            {
                "code": t["code"],
                "label": t["label"],
                "zone": t["zone"],
                "has_session": bool(session),
                "guest_name": session["guest_name"] if session else None,
                "party_size": session["party_size"] if session else None,
            }
        )
    menu = _menu_payload(conn)
    promo = current_promo()
    conn.close()
    return templates.TemplateResponse(
        "boss_order.html",
        {
            "request": request,
            "title": f"{boss['name']} · Order",
            "boss": boss,
            "tables": seat_rows,
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
    conn = connect()
    table = get_table_by_code(conn, body.table_code)
    if not table:
        conn.close()
        raise HTTPException(404, "Seat not found")
    try:
        session = start_session(
            conn, table["id"], body.guest_name.strip(), body.party_size
        )
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
               s.guest_name AS guest_name
        FROM orders o
        JOIN tables t ON t.id = o.table_id
        JOIN sessions s ON s.id = o.session_id
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
    meta = load_menu_meta()
    for t in tables:
        session = get_open_session(conn, t["id"])
        bill = None
        open_orders = 0
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
            bill = compute_bill(
                [dict(x) for x in lines],
                session["party_size"],
                meta["service_charge_rate"],
                meta["snack_charge_per_head"],
            )
        rows.append(
            {
                "table": t,
                "session": session,
                "bill": bill,
                "open_orders": open_orders,
            }
        )
    conn.close()
    return templates.TemplateResponse(
        "staff_tables.html",
        {"request": request, "title": "Staff · Seats", "rows": rows, "pin": pin},
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
    if session:
        lines = _session_lines(conn, session["id"])
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
        },
    )


@app.post("/api/staff/bill/{table_code}/close")
def close_bill(
    table_code: str,
    pin: str = Form(...),
    discount_percent: float = Form(0),
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

    meta = load_menu_meta()
    lines = _session_lines(conn, session["id"])
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
        party_size=session["party_size"],
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
    path = ROOT / session["receipt_path"]
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
    tables = list_active_tables(conn)
    conn.close()
    base = str(request.base_url).rstrip("/")
    return templates.TemplateResponse(
        "staff_qrs.html",
        {
            "request": request,
            "title": "Seat QR Codes",
            "tables": tables,
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
            "day": biz.isoformat(),
            "month": f"{year}-{mon:02d}",
        },
    )


@app.get("/health")
def health():
    return {"ok": True, "promo": current_promo()}
