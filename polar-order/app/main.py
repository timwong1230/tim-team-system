from __future__ import annotations

import asyncio
import io
import json
import os
import re
import sqlite3
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote
from zoneinfo import ZoneInfo

import qrcode
from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from .db import (
    add_claim,
    add_ff_party_guest,
    clear_open_session,
    connect,
    create_booking,
    delete_claim,
    delete_ff_party_guest,
    ensure_session,
    ff_party_summary,
    find_next_open_split,
    get_ff_party_guest,
    get_open_session,
    get_session,
    get_table_by_code,
    init_db,
    list_active_tables,
    list_bookings_for_date,
    list_bookings_for_month,
    list_claims,
    list_guest_tables,
    list_table_splits,
    load_menu_meta,
    mark_ff_party_guest_paid,
    publish_event,
    reset_operational_data,
    session_is_ff_party,
    set_booking_status,
    set_cash_tilt,
    start_session,
    transfer_open_session,
    sync_ff_party_size,
    update_booking,
    utc_now,
)
from .seats import parent_table_code, parse_table_split
from .ops_constants import (
    BILL_EDIT_PASSWORD,
    BOSS_CREDIT_METHOD,
    CLAIM_PRESETS,
    PAYMENT_METHODS,
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
    build_daily_sales_sheet_row,
    daily_sales_report,
    format_whatsapp_sales_report,
    item_purchase_report,
    monthly_boss_report,
    monthly_sales_report,
)
from .bank_evidence import (
    list_recent_evidence,
    resolve_evidence_path,
    save_and_register,
)
from .bank_import import parse_bank_csv
from .sheets_sync import (
    SheetsNotConfigured,
    append_bank_entries,
    sheets_configured,
    upsert_daily_sales_row,
)
from .ai_host import ask_ai
from .guest_nav import build_guest_nav
from .paths import BANK_EVIDENCE_DIR, DATA_DIR, ROOT
from .seats import BOSSES, boss_by_id, boss_seat_code
from .cocktails import (
    cocktail_birthday_serve,
    count_birthday_free_qty,
    note_is_birthday_free,
)
from .spirits import (
    SINGLE_MIX_ITEM_ID,
    list_spirit_glass_options,
    single_mix_serve,
    spirit_serve_for,
)

HK = ZoneInfo("Asia/Hong_Kong")

templates = Jinja2Templates(directory=str(ROOT / "templates"))

STAFF_PIN = os.getenv("POLAR_STAFF_PIN", "polar2026")
# Bump when shipping guest UI/CSS/JS so iPhone Safari cannot keep a stale bundle.
ASSET_VERSION = os.getenv("POLAR_ASSET_VERSION", "20261101c").strip() or "20261101c"
templates.env.globals["asset_v"] = ASSET_VERSION
_subscribers: list[asyncio.Queue] = []


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    # One-shot cloud wipe: set POLAR_RESET_ON_START=RESET-YYYY-MM-DD (HK date).
    # A bare "RESET" is ignored so a forgotten env var cannot wipe every restart.
    reset_token = os.getenv("POLAR_RESET_ON_START", "").strip().upper()
    today_hk = business_date(datetime.now(HK)).isoformat()
    expected = f"RESET-{today_hk}"
    if reset_token == expected:
        conn = connect()
        cleared = reset_operational_data(conn)
        conn.close()
        print(f"[polar] POLAR_RESET_ON_START wiped operational data: {cleared}", flush=True)
    elif reset_token in {"RESET", "1", "TRUE", "YES"}:
        print(
            f"[polar] POLAR_RESET_ON_START={reset_token!r} ignored — "
            f"use {expected} for a one-shot wipe",
            flush=True,
        )
    yield


app = FastAPI(title="Polar Lounge Order", version="0.1.0", lifespan=lifespan)


@app.middleware("http")
async def _html_no_cache(request: Request, call_next):
    """Stop Safari / QR WebViews from serving a stale guest menu HTML shell."""
    response = await call_next(request)
    content_type = response.headers.get("content-type", "")
    path = request.url.path or ""
    if "text/html" in content_type or path.startswith("/t/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
    elif path.startswith("/static/"):
        # Versioned URLs (?v=) are the real bust; keep CDN revalidation honest.
        response.headers.setdefault("Cache-Control", "public, max-age=300, must-revalidate")
    return response


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
    # Used when the table has no open session yet (NOM as first item)
    guest_name: str | None = Field(default=None, max_length=40)
    party_size: int | None = Field(default=None, ge=1, le=30)


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


class StaffSnackIn(BaseModel):
    pin: str
    waived: bool = False


class StaffItemEditIn(BaseModel):
    pin: str
    qty: int = Field(..., ge=0, le=50)  # 0 = remove line


class StaffTransferIn(BaseModel):
    pin: str
    target_table: str = Field(min_length=1, max_length=40)


class StaffSplitIn(BaseModel):
    pin: str


class StaffClearTableIn(BaseModel):
    pin: str


class StaffFfPartyEnableIn(BaseModel):
    pin: str
    party_name: str | None = Field(default=None, max_length=40)
    expected_size: int = Field(default=4, ge=1, le=40)
    default_price: float = Field(default=450, ge=0, le=50000)
    waive_snacks: bool = True


class StaffFfPartyGuestIn(BaseModel):
    pin: str
    guest_label: str = Field(min_length=1, max_length=40)
    head_price: float = Field(ge=0, le=50000)
    package_label: str | None = Field(default=None, max_length=80)
    collect_now: bool = True


class StaffFfPartyGuestPayIn(BaseModel):
    pin: str


class StaffFfPartyGuestDeleteIn(BaseModel):
    pin: str


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


def _session_snack_waived(session: sqlite3.Row | dict | None) -> bool:
    if not session:
        return False
    try:
        if "snack_waived" in session.keys():
            return bool(session["snack_waived"])
    except Exception:
        pass
    if isinstance(session, dict):
        return bool(session.get("snack_waived"))
    return False


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


def _staff_only_category_ids() -> set[str]:
    """Category ids marked staff_only in menu.json (hidden from guest QR menu)."""
    try:
        meta = load_menu_meta()
    except Exception:
        return set()
    return {
        str(c["id"])
        for c in (meta.get("categories") or [])
        if c.get("staff_only") and c.get("id")
    }


def _menu_payload(
    conn: sqlite3.Connection,
    *,
    include_staff_only: bool = False,
    staff_cocktail_promo: bool = False,
) -> list[dict[str, Any]]:
    promo = current_promo()
    staff_only_ids = _staff_only_category_ids()
    cats = conn.execute(
        "SELECT * FROM menu_categories ORDER BY sort_order ASC"
    ).fetchall()
    out = []
    for cat in cats:
        if cat["id"] in staff_only_ids and not include_staff_only:
            continue
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
            serve = spirit_serve_for(cat["id"], item["unit"], item_id=item["id"])
            if not serve and staff_cocktail_promo:
                serve = cocktail_birthday_serve(cat["id"])
            if item["id"] == SINGLE_MIX_ITEM_ID:
                serve = single_mix_serve(list_spirit_glass_options(conn))
            image = item["image"] or ""
            if image and "v=" not in image:
                sep = "&" if "?" in image else "?"
                image = f"{image}{sep}v={ASSET_VERSION}"
            row = {
                "id": item["id"],
                "name": item["name"],
                "price": float(item["price"]),
                "display_price": final,
                "unit": item["unit"],
                "note": item["note"],
                "allow_note": bool(item["allow_note"]),
                "promo_tag": tag,
                "image": image or None,
                "promo_type": cat["promo"],
                "combo_price": None,
                "serve": serve,
                # legacy alias for templates during transition
                "mixer_options": (serve.get("options") if serve else None) or None,
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
                "staff_only": cat["id"] in staff_only_ids,
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
        # Free Flow party head — custom price, no 10% service (free-flow category).
        if (entry.item_id or "") == "ff-party-head":
            if not custom_name:
                raise HTTPException(400, "Free Flow head needs a guest name")
            if entry.custom_price is None:
                raise HTTPException(400, "Free Flow head needs a price")
            price = round(float(entry.custom_price), 1)
            if price < 0:
                raise HTTPException(400, "Invalid price")
            raw_entries.append(
                {
                    "item_id": "ff-party-head",
                    "name": custom_name,
                    "category_id": "free-flow",
                    "promo": "none",
                    "base_price": price,
                    "qty": entry.qty,
                    "note": entry.note,
                }
            )
            continue
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
    # Demo practice seat: include staff-only Free Flow so staff can rehearse it.
    is_demo = (table["zone"] or "") == "demo"
    menu = _menu_payload(conn, include_staff_only=is_demo) if ready else []
    guest_nav = build_guest_nav(menu) if ready else {"roots": [], "leaves": []}
    single_mix_spirits = list_spirit_glass_options(conn) if ready else []
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
            "guest_nav": guest_nav,
            "promo": promo,
            "ready": ready,
            "other_seats": other_seats,
            "single_mix_spirits": single_mix_spirits,
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
    # Boss station is staff-facing — include Free Flow etc.
    menu = _menu_payload(conn, include_staff_only=True)
    single_mix_spirits = list_spirit_glass_options(conn)
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
            "single_mix_spirits": single_mix_spirits,
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
    # Keep served on open sessions so staff can undo / cancel after mistakes.
    orders = conn.execute(
        """
        SELECT o.*, t.code AS table_code, t.label AS table_label,
               s.guest_name AS guest_name,
               dt.code AS deliver_to_code, dt.label AS deliver_to_label
        FROM orders o
        JOIN tables t ON t.id = o.table_id
        JOIN sessions s ON s.id = o.session_id
        LEFT JOIN tables dt ON dt.id = o.deliver_table_id
        WHERE o.status IN ('new', 'preparing', 'ready', 'served')
          AND s.status = 'open'
        ORDER BY
          CASE o.status
            WHEN 'new' THEN 0
            WHEN 'preparing' THEN 1
            WHEN 'ready' THEN 2
            ELSE 3
          END,
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
                    snack_waived=_session_snack_waived(session),
                )
        entry = {
            "table": t,
            "session": session,
            "bill": bill,
            "open_orders": open_orders,
            "is_boss": zone == "boss",
            "is_demo": zone == "demo",
            "is_split": zone == "table_split",
            "can_split": zone == "table",
            "is_ff_party": session_is_ff_party(session),
            "parent_label": None,
        }
        if entry["is_split"]:
            parent = parent_table_code(t["code"])
            entry["parent_label"] = parent.replace("TABLE", "Table ") if parent else None
            # Idle A–D cards clutter Open seats — staff open splits from Table 1–5
            # (Split party / bill siblings). Only list a split when it has a live party.
            if not session:
                continue
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


def _bill_dict_for_session(
    conn: sqlite3.Connection,
    session: sqlite3.Row,
    *,
    is_boss: bool,
    discount_percent: float = 0,
) -> dict:
    meta = load_menu_meta()
    lines = _session_lines(conn, session["id"])
    if is_boss:
        prod = round(sum(float(x["line_total"]) for x in lines), 1)
        return {
            "total": prod,
            "subtotal": prod,
            "serviceable_subtotal": prod,
            "snack_charge": 0,
            "service_charge": 0,
            "discount_amount": 0,
            "discount_percent": 0,
            "party_size": 1,
            "service_charge_rate": 0,
            "snack_waived": True,
        }
    return compute_bill(
        lines,
        session["party_size"],
        meta["service_charge_rate"],
        meta["snack_charge_per_head"],
        discount_percent=discount_percent,
        snack_waived=_session_snack_waived(session),
    )


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
    menu = _menu_payload(
        conn,
        include_staff_only=True,
        staff_cocktail_promo=True,
    )
    single_mix_spirits = list_spirit_glass_options(conn)
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
            "single_mix_spirits": single_mix_spirits,
            "ff_party": session_is_ff_party(session),
        },
    )


@app.get("/staff/bill/{table_code}", response_class=HTMLResponse)
def staff_bill(
    request: Request,
    table_code: str,
    pin: str = "",
    discount: float = 0,
    edited: str = "",
):
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
    transfer_targets: list[sqlite3.Row] = []
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
                snack_waived=_session_snack_waived(session),
            )
            for t in list_active_tables(conn):
                tz = (t["zone"] or "").strip().lower()
                if tz in ("boss", "demo"):
                    continue
                if t["id"] == table["id"]:
                    continue
                if get_open_session(conn, t["id"]):
                    continue
                transfer_targets.append(t)
    zone = (table["zone"] or "").strip().lower()
    can_split = zone in ("table", "table_split")
    split_parent = (
        table["code"]
        if zone == "table"
        else (parent_table_code(table["code"]) or table["code"])
    )
    split_siblings = list_table_splits(conn, split_parent) if can_split else []
    ff_party = session_is_ff_party(session) and not is_boss
    ff_summary = (
        ff_party_summary(conn, session["id"]) if ff_party and session else None
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
            "payment_methods": PAYMENT_METHODS,
            "pin": pin,
            "discount": discount or 0,
            "is_boss": is_boss,
            "snack_per_head": meta["snack_charge_per_head"],
            "snack_waived": _session_snack_waived(session),
            "transfer_targets": transfer_targets,
            "can_split": can_split,
            "split_parent": split_parent,
            "split_siblings": split_siblings,
            "ff_party": ff_party,
            "ff_summary": ff_summary,
            "ff_expected": int(session["ff_expected"] or 0) if session and ff_party else 0,
            "ff_default_price": (
                float(session["ff_default_price"])
                if session and ff_party and session["ff_default_price"] is not None
                else 450.0
            ),
            "bill_reopened": (edited or "").strip() in ("1", "true", "yes"),
        },
    )


def _ff_party_bill_payload(conn: sqlite3.Connection, session: sqlite3.Row) -> dict[str, Any]:
    session = get_session(conn, session["id"]) or session
    summary = ff_party_summary(conn, session["id"])
    meta = load_menu_meta()
    lines = _session_lines(conn, session["id"])
    bill = compute_bill(
        lines,
        session["party_size"],
        meta["service_charge_rate"],
        meta["snack_charge_per_head"],
        discount_percent=float(session["discount_percent"] or 0),
        snack_waived=_session_snack_waived(session),
    )
    return {
        "ff_party": True,
        "ff_expected": int(session["ff_expected"] or 0),
        "ff_default_price": float(session["ff_default_price"] or 0),
        "party_size": session["party_size"],
        "snack_waived": _session_snack_waived(session),
        "summary": summary,
        "bill": bill,
        "lines": lines,
    }


def _collect_ff_guest_payment(
    conn: sqlite3.Connection,
    *,
    table: sqlite3.Row,
    session: sqlite3.Row,
    guest: sqlite3.Row,
) -> tuple[sqlite3.Row, dict[str, Any]]:
    """Ring a Free Flow head line (no service) and mark guest paid."""
    if guest["status"] == "paid":
        raise HTTPException(400, "Guest already paid")
    label = guest["guest_label"]
    price = float(guest["head_price"])
    note = guest["package_label"]
    order_id, payload = _create_order(
        conn,
        table=table,
        session=session,
        items=[
            CartItemIn(
                item_id="ff-party-head",
                qty=1,
                note=note,
                custom_name=f"Free Flow · {label}",
                custom_price=price,
            )
        ],
        note="Free Flow party head",
        created_by="Staff",
    )
    paid = mark_ff_party_guest_paid(conn, guest_id=guest["id"], order_id=order_id)
    return paid, payload


@app.post("/api/staff/bill/{table_code}/ff-party/enable")
def staff_enable_ff_party(table_code: str, body: StaffFfPartyEnableIn):
    """Start Free Flow party mode — head fees collected as guests arrive."""
    if body.pin != STAFF_PIN:
        raise HTTPException(401, "Unauthorized")
    conn = connect()
    table = get_table_by_code(conn, table_code)
    if not table:
        conn.close()
        raise HTTPException(404, "Table not found")
    if (table["zone"] or "") in ("boss", "demo"):
        conn.close()
        raise HTTPException(400, "Free Flow party is for guest tables only")
    name = (body.party_name or "").strip() or "Free Flow party"
    try:
        session = ensure_session(
            conn,
            table["id"],
            party_size=body.expected_size,
            guest_name=name,
        )
    except ValueError as e:
        conn.close()
        raise HTTPException(400, str(e)) from e
    conn.execute(
        """
        UPDATE sessions SET
          ff_party = 1,
          ff_expected = ?,
          ff_default_price = ?,
          party_size = ?,
          snack_waived = ?
        WHERE id = ?
        """,
        (
            body.expected_size,
            round(float(body.default_price), 1),
            body.expected_size,
            1 if body.waive_snacks else 0,
            session["id"],
        ),
    )
    conn.commit()
    session = get_open_session(conn, table["id"])
    payload = _ff_party_bill_payload(conn, session)
    conn.close()
    return {"ok": True, **payload}


@app.post("/api/staff/bill/{table_code}/ff-party/guests")
async def staff_add_ff_party_guest(table_code: str, body: StaffFfPartyGuestIn):
    """Add a Free Flow guest (custom head price); optionally collect now."""
    if body.pin != STAFF_PIN:
        raise HTTPException(401, "Unauthorized")
    conn = connect()
    table = get_table_by_code(conn, table_code)
    if not table:
        conn.close()
        raise HTTPException(404, "Table not found")
    session = get_open_session(conn, table["id"])
    if not session or not session_is_ff_party(session):
        conn.close()
        raise HTTPException(400, "Enable Free Flow party on this bill first")
    try:
        guest = add_ff_party_guest(
            conn,
            session_id=session["id"],
            guest_label=body.guest_label,
            head_price=body.head_price,
            package_label=body.package_label,
        )
        session = sync_ff_party_size(conn, session)
    except ValueError as e:
        conn.close()
        raise HTTPException(400, str(e)) from e

    broadcast = None
    if body.collect_now:
        try:
            guest, broadcast = _collect_ff_guest_payment(
                conn, table=table, session=session, guest=guest
            )
        except HTTPException:
            conn.close()
            raise
    payload = _ff_party_bill_payload(conn, session)
    conn.close()
    if broadcast:
        await _broadcast({"type": "order.new", "data": broadcast})
    return {"ok": True, "guest": dict(guest), **payload}


@app.post("/api/staff/bill/{table_code}/ff-party/guests/{guest_id}/pay")
async def staff_pay_ff_party_guest(
    table_code: str, guest_id: int, body: StaffFfPartyGuestPayIn
):
    """Collect head fee for a pending Free Flow guest."""
    if body.pin != STAFF_PIN:
        raise HTTPException(401, "Unauthorized")
    conn = connect()
    table = get_table_by_code(conn, table_code)
    if not table:
        conn.close()
        raise HTTPException(404, "Table not found")
    session = get_open_session(conn, table["id"])
    if not session or not session_is_ff_party(session):
        conn.close()
        raise HTTPException(400, "Not a Free Flow party")
    guest = get_ff_party_guest(conn, guest_id)
    if not guest or guest["session_id"] != session["id"]:
        conn.close()
        raise HTTPException(404, "Guest not found")
    try:
        guest, broadcast = _collect_ff_guest_payment(
            conn, table=table, session=session, guest=guest
        )
    except HTTPException:
        conn.close()
        raise
    payload = _ff_party_bill_payload(conn, session)
    conn.close()
    await _broadcast({"type": "order.new", "data": broadcast})
    return {"ok": True, "guest": dict(guest), **payload}


@app.post("/api/staff/bill/{table_code}/ff-party/guests/{guest_id}/delete")
def staff_delete_ff_party_guest(
    table_code: str, guest_id: int, body: StaffFfPartyGuestDeleteIn
):
    """Remove an unpaid Free Flow guest from the list."""
    if body.pin != STAFF_PIN:
        raise HTTPException(401, "Unauthorized")
    conn = connect()
    table = get_table_by_code(conn, table_code)
    if not table:
        conn.close()
        raise HTTPException(404, "Table not found")
    session = get_open_session(conn, table["id"])
    if not session or not session_is_ff_party(session):
        conn.close()
        raise HTTPException(400, "Not a Free Flow party")
    guest = get_ff_party_guest(conn, guest_id)
    if not guest or guest["session_id"] != session["id"]:
        conn.close()
        raise HTTPException(404, "Guest not found")
    try:
        delete_ff_party_guest(conn, guest_id)
        session = sync_ff_party_size(conn, session)
    except ValueError as e:
        conn.close()
        raise HTTPException(400, str(e)) from e
    payload = _ff_party_bill_payload(conn, session)
    conn.close()
    return {"ok": True, **payload}


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
        snack_waived=_session_snack_waived(session),
    )
    conn.close()
    return {
        "ok": True,
        "party_size": session["party_size"],
        "guest_name": session["guest_name"],
        "snack_waived": _session_snack_waived(session),
        "bill": bill,
    }


@app.post("/api/staff/bill/{table_code}/snack")
def staff_update_snack(table_code: str, body: StaffSnackIn):
    """Waive or restore per-head bar snack charge when guest declines snacks."""
    if body.pin != STAFF_PIN:
        raise HTTPException(401, "Unauthorized")
    conn = connect()
    table = get_table_by_code(conn, table_code)
    if not table:
        conn.close()
        raise HTTPException(404, "Table not found")
    if (table["zone"] or "") == "boss":
        conn.close()
        return {"ok": True, "snack_waived": True, "bill": None}
    session = get_open_session(conn, table["id"])
    if not session:
        conn.close()
        raise HTTPException(400, "No open session")
    waived = 1 if body.waived else 0
    conn.execute(
        "UPDATE sessions SET snack_waived = ? WHERE id = ?",
        (waived, session["id"]),
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
        snack_waived=_session_snack_waived(session),
    )
    conn.close()
    return {
        "ok": True,
        "snack_waived": bool(waived),
        "party_size": session["party_size"],
        "bill": bill,
    }


@app.post("/api/staff/bill/{table_code}/clear")
async def staff_clear_table(table_code: str, body: StaffClearTableIn):
    """Void the open session — wrong table / accidental open. Not a sale."""
    if body.pin != STAFF_PIN:
        raise HTTPException(401, "Unauthorized")
    conn = connect()
    table = get_table_by_code(conn, table_code)
    if not table:
        conn.close()
        raise HTTPException(404, "Table not found")
    try:
        cleared = clear_open_session(conn, table["id"])
    except ValueError as e:
        conn.close()
        raise HTTPException(400, str(e)) from e
    payload = {
        "table_code": table["code"],
        "table_label": table["label"],
        "session_id": cleared["id"],
        "guest_name": cleared["guest_name"] if "guest_name" in cleared.keys() else None,
    }
    publish_event(conn, "session.clear", payload)
    conn.close()
    await _broadcast({"type": "session.clear", "data": payload})
    return {
        "ok": True,
        "cleared": True,
        "session_id": cleared["id"],
        "table_code": table["code"],
        "redirect": f"/staff/tables?pin={body.pin}",
    }


@app.post("/api/staff/bill/{table_code}/transfer")
async def staff_transfer_table(table_code: str, body: StaffTransferIn):
    """Move an open guest session (and its orders) to another empty guest table."""
    if body.pin != STAFF_PIN:
        raise HTTPException(401, "Unauthorized")
    conn = connect()
    source = get_table_by_code(conn, table_code)
    if not source:
        conn.close()
        raise HTTPException(404, "Table not found")
    zone = (source["zone"] or "").strip().lower()
    if zone in ("boss", "demo"):
        conn.close()
        raise HTTPException(400, "Cannot transfer boss or demo seats")
    target = get_table_by_code(conn, body.target_table.strip().upper())
    if not target:
        conn.close()
        raise HTTPException(404, "Target table not found")
    target_zone = (target["zone"] or "").strip().lower()
    if target_zone in ("boss", "demo"):
        conn.close()
        raise HTTPException(400, "Target must be a guest table")
    session = get_open_session(conn, source["id"])
    if not session:
        conn.close()
        raise HTTPException(400, "No open session on this table")
    try:
        moved = transfer_open_session(conn, source["id"], target["id"])
    except ValueError as e:
        conn.close()
        raise HTTPException(400, str(e)) from e
    payload = {
        "from_table": source["code"],
        "to_table": target["code"],
        "session_id": moved["id"],
        "guest_name": moved["guest_name"],
    }
    publish_event(conn, "session.transfer", payload)
    conn.close()
    await _broadcast({"type": "session.transfer", "data": payload})
    return {
        "ok": True,
        "from_table": source["code"],
        "to_table": target["code"],
        "to_label": target["label"],
        "session_id": moved["id"],
        "redirect": f"/staff/bill/{target['code']}?pin={body.pin}",
    }


@app.post("/api/staff/tables/{table_code}/split")
def staff_open_table_split(table_code: str, body: StaffSplitIn):
    """Open the next free Table NA/B/C/D seat for a second party at the same table."""
    if body.pin != STAFF_PIN:
        raise HTTPException(401, "Unauthorized")
    conn = connect()
    table = get_table_by_code(conn, table_code)
    if not table:
        conn.close()
        raise HTTPException(404, "Table not found")
    zone = (table["zone"] or "").strip().lower()
    parent_code = table["code"]
    if zone == "table_split":
        parent_code = parent_table_code(table["code"]) or table["code"]
    elif zone != "table":
        conn.close()
        raise HTTPException(400, "Only Table 1–5 can be split into A/B/C/D parties")
    split = find_next_open_split(conn, parent_code)
    if not split:
        conn.close()
        raise HTTPException(
            400,
            f"All splits for {parent_code.replace('TABLE', 'Table ')} are in use (A–D)",
        )
    siblings = [
        {
            "code": s["code"],
            "label": s["label"],
            "busy": bool(get_open_session(conn, s["id"])),
        }
        for s in list_table_splits(conn, parent_code)
    ]
    conn.close()
    return {
        "ok": True,
        "parent": parent_code,
        "code": split["code"],
        "label": split["label"],
        "siblings": siblings,
        "redirect": f"/staff/order/{split['code']}?pin={body.pin}",
        "bill_url": f"/staff/bill/{split['code']}?pin={body.pin}",
    }


@app.post("/api/staff/bill/{table_code}/custom")
async def staff_add_custom(table_code: str, body: StaffCustomIn):
    """Staff adds a Not on Menu line — may be the first item on the bill."""
    if body.pin != STAFF_PIN:
        raise HTTPException(401, "Unauthorized")
    conn = connect()
    table = get_table_by_code(conn, table_code)
    if not table:
        conn.close()
        raise HTTPException(404, "Table not found")
    session = get_open_session(conn, table["id"])
    if not session or not session["guest_name"]:
        name = (body.guest_name or "").strip() or "Walk-in"
        party = int(body.party_size or 2)
        try:
            session = start_session(conn, table["id"], name, party_size=party)
        except ValueError as e:
            conn.close()
            raise HTTPException(400, str(e)) from e
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


@app.post("/api/staff/bill/{table_code}/items/{item_row_id}")
async def staff_edit_bill_item(table_code: str, item_row_id: int, body: StaffItemEditIn):
    """Change qty of a bill line, or remove it (qty=0). Open sessions only."""
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
        raise HTTPException(400, "No open session")

    row = conn.execute(
        """
        SELECT oi.*, o.id AS order_id, o.session_id, o.status AS order_status
        FROM order_items oi
        JOIN orders o ON o.id = oi.order_id
        WHERE oi.id = ? AND o.session_id = ?
        """,
        (item_row_id, session["id"]),
    ).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, "Item not found on this bill")
    if row["order_status"] == "cancelled":
        conn.close()
        raise HTTPException(400, "Order already cancelled")

    now = utc_now()
    qty = int(body.qty)
    removed = False
    if qty <= 0:
        conn.execute("DELETE FROM order_items WHERE id = ?", (item_row_id,))
        left = conn.execute(
            "SELECT COUNT(*) AS c FROM order_items WHERE order_id = ?",
            (row["order_id"],),
        ).fetchone()["c"]
        if left == 0:
            conn.execute(
                "UPDATE orders SET status = 'cancelled', updated_at = ? WHERE id = ?",
                (now, row["order_id"]),
            )
        else:
            conn.execute(
                "UPDATE orders SET updated_at = ? WHERE id = ?",
                (now, row["order_id"]),
            )
        removed = True
        action = "removed"
    else:
        unit = float(row["unit_price"] or 0)
        line_total = round(unit * qty, 1)
        conn.execute(
            """
            UPDATE order_items
            SET qty = ?, line_total = ?
            WHERE id = ?
            """,
            (qty, line_total, item_row_id),
        )
        conn.execute(
            "UPDATE orders SET updated_at = ? WHERE id = ?",
            (now, row["order_id"]),
        )
        action = "updated"

    publish_event(
        conn,
        "order.status",
        {
            "order_id": row["order_id"],
            "status": "cancelled" if removed and action == "removed" else row["order_status"],
            "table_code": table["code"],
            "item_edit": action,
        },
    )
    conn.commit()

    is_boss = (table["zone"] or "") == "boss"
    lines = _session_lines(conn, session["id"])
    bill = _bill_dict_for_session(conn, session, is_boss=is_boss)
    conn.close()
    await _broadcast(
        {
            "type": "order.status",
            "data": {
                "order_id": row["order_id"],
                "table_code": table["code"],
                "item_edit": action,
            },
        }
    )
    return {
        "ok": True,
        "action": action,
        "item_id": item_row_id,
        "qty": 0 if removed else qty,
        "lines": lines,
        "bill": bill,
    }


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

    # Birthday Free: one complimentary Celestial cocktail per open session.
    birthday_qty = sum(
        int(entry.qty)
        for entry in body.items
        if note_is_birthday_free(entry.note)
    )
    if birthday_qty:
        if birthday_qty > 1:
            conn.close()
            raise HTTPException(400, "Only one Birthday Free cocktail per table")
        existing = _session_lines(conn, session["id"])
        if count_birthday_free_qty(existing) >= 1:
            conn.close()
            raise HTTPException(400, "Birthday Free cocktail already on this bill")

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
    payment_method: str = Form(""),
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
    # Boss tabs are Polar credit ledgers — not guest payment / not sales.
    if is_boss:
        method = BOSS_CREDIT_METHOD
    else:
        method = (payment_method or "").strip()
        if method not in PAYMENT_METHODS:
            conn.close()
            raise HTTPException(400, "Select a payment method")
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
            snack_waived=_session_snack_waived(session),
        )
    now = utc_now()
    # Keep original business_date when re-closing an edited (reopened) bill.
    existing_biz = None
    if "business_date" in session.keys() and session["business_date"]:
        existing_biz = str(session["business_date"]).strip()[:10] or None
    biz = existing_biz or business_date(datetime.now(HK)).isoformat()
    guest_name = session["guest_name"] if session["guest_name"] else None
    receipt_rel = generate_receipt_pdf(
        session_id=session["id"],
        table_label=table["label"],
        party_size=session["party_size"] if not is_boss else 1,
        lines=lines,
        bill=bill,
        closed_at_iso=now,
        guest_name=guest_name,
        payment_method=method,
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
          business_date = ?,
          payment_method = ?
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
            method,
            session["id"],
        ),
    )
    conn.execute(
        "UPDATE orders SET status = 'served', updated_at = ? WHERE session_id = ? AND status != 'cancelled'",
        (now, session["id"]),
    )
    conn.commit()
    # Snapshot tonight's running totals so yesterday's report survives resets.
    try:
        daily_sales_report(conn, date.fromisoformat(biz))
    except Exception:
        pass
    conn.close()
    return {
        "ok": True,
        "session_id": session["id"],
        "total": bill["total"],
        "receipt_url": f"/staff/receipt/{session['id']}?pin={pin}",
    }


class StaffPaymentUpdateIn(BaseModel):
    pin: str
    payment_method: str = Field(min_length=1, max_length=40)


class StaffReopenEditIn(BaseModel):
    pin: str
    edit_password: str = Field(min_length=1, max_length=80)


@app.post("/api/staff/sessions/{session_id}/reopen-edit")
def staff_reopen_session_for_edit(session_id: int, body: StaffReopenEditIn):
    """Unlock a Mark-paid bill for item edits (password-gated)."""
    if body.pin != STAFF_PIN:
        raise HTTPException(401, "Unauthorized")
    if (body.edit_password or "").strip() != BILL_EDIT_PASSWORD:
        raise HTTPException(403, "Wrong edit password")
    conn = connect()
    session = get_session(conn, session_id)
    if not session or session["status"] != "closed":
        conn.close()
        raise HTTPException(404, "Closed bill not found")
    table = conn.execute(
        "SELECT * FROM tables WHERE id = ?", (session["table_id"],)
    ).fetchone()
    if not table:
        conn.close()
        raise HTTPException(404, "Table not found")
    open_sess = get_open_session(conn, table["id"])
    if open_sess and int(open_sess["id"]) != int(session_id):
        conn.close()
        raise HTTPException(
            400,
            f"{table['label']} already has an open party — finish or clear it first",
        )
    # Keep business_date so re-close stays on the original night.
    conn.execute(
        """
        UPDATE sessions SET
          status = 'open',
          closed_at = NULL,
          receipt_path = NULL,
          payment_method = NULL,
          discount_percent = 0,
          subtotal = NULL,
          snack_charge = NULL,
          service_charge = NULL,
          discount_amount = NULL,
          total = NULL
        WHERE id = ?
        """,
        (session_id,),
    )
    # Orders stay non-cancelled so staff can edit qty / add items, then Mark paid again.
    conn.execute(
        """
        UPDATE orders SET status = 'placed', updated_at = ?
        WHERE session_id = ? AND status = 'served'
        """,
        (utc_now(), session_id),
    )
    conn.commit()
    # Refresh that night's snapshot without this bill until they re-close.
    biz = session["business_date"]
    if biz:
        try:
            daily_sales_report(
                conn,
                date.fromisoformat(str(biz)[:10]),
                use_snapshot_fallback=False,
                force_snapshot=True,
            )
        except Exception:
            pass
    conn.close()
    return {
        "ok": True,
        "session_id": session_id,
        "table_code": table["code"],
        "table_label": table["label"],
        "redirect": f"/staff/bill/{table['code']}?pin={body.pin}&edited=1",
    }


@app.post("/api/staff/sessions/{session_id}/payment")
def staff_update_session_payment(session_id: int, body: StaffPaymentUpdateIn):
    """Correct tender after Mark paid — updates closed session + regenerates PDF."""
    if body.pin != STAFF_PIN:
        raise HTTPException(401, "Unauthorized")
    method = (body.payment_method or "").strip()
    if method not in PAYMENT_METHODS:
        raise HTTPException(400, "Select a payment method")
    conn = connect()
    session = get_session(conn, session_id)
    if not session or session["status"] != "closed":
        conn.close()
        raise HTTPException(404, "Closed bill not found")
    table = conn.execute(
        "SELECT * FROM tables WHERE id = ?", (session["table_id"],)
    ).fetchone()
    if not table:
        conn.close()
        raise HTTPException(404, "Table not found")
    zone = (table["zone"] or "").strip().lower()
    if zone in ("boss", "demo"):
        conn.close()
        raise HTTPException(400, "Cannot change payment on boss or demo seats")
    if (session["payment_method"] or "") == BOSS_CREDIT_METHOD:
        conn.close()
        raise HTTPException(400, "Cannot change boss credit")

    meta = load_menu_meta()
    lines = _session_lines(conn, session["id"])
    bill = {
        "subtotal": float(session["subtotal"] or 0),
        "snack_charge": float(session["snack_charge"] or 0),
        "service_charge": float(session["service_charge"] or 0),
        "discount_amount": float(session["discount_amount"] or 0),
        "discount_percent": float(session["discount_percent"] or 0),
        "total": float(session["total"] or 0),
        "party_size": int(session["party_size"] or 1),
        "service_charge_rate": float(meta["service_charge_rate"]),
    }
    guest_name = session["guest_name"] if session["guest_name"] else None
    receipt_rel = generate_receipt_pdf(
        session_id=session["id"],
        table_label=table["label"],
        party_size=int(session["party_size"] or 1),
        lines=lines,
        bill=bill,
        closed_at_iso=session["closed_at"] or utc_now(),
        guest_name=guest_name,
        payment_method=method,
    )
    conn.execute(
        "UPDATE sessions SET payment_method = ?, receipt_path = ? WHERE id = ?",
        (method, receipt_rel, session["id"]),
    )
    conn.commit()
    biz_iso = session["business_date"]
    if biz_iso:
        try:
            daily_sales_report(conn, date.fromisoformat(str(biz_iso)[:10]))
        except Exception:
            pass
    conn.close()
    return {
        "ok": True,
        "session_id": session_id,
        "payment_method": method,
        "receipt_url": f"/staff/receipt/{session_id}?pin={body.pin}",
    }


@app.get("/staff/receipt/{session_id}")
def staff_receipt(session_id: int, pin: str = ""):
    if pin != STAFF_PIN:
        raise HTTPException(401, "Unauthorized")
    from .paths import RECEIPT_DIR

    conn = connect()
    session = get_session(conn, session_id)
    conn.close()
    candidates = []
    if session and session["receipt_path"]:
        rel = session["receipt_path"]
        candidates.append(DATA_DIR / rel)
        candidates.append(ROOT / rel)
    # After a live-data reset, session rows are gone but PDFs + snapshots remain.
    candidates.append(RECEIPT_DIR / f"receipt-S{session_id}.pdf")
    path = next((p for p in candidates if p.exists()), None)
    if not path:
        raise HTTPException(404, "Receipt not found")
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
    BANK_EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
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
            "claim_presets": CLAIM_PRESETS,
            "payment_methods": PAYMENT_METHODS,
            "day": biz.isoformat(),
            "month": f"{year}-{mon:02d}",
            "sheets_sync_ready": sheets_configured(),
            "bank_evidence_recent": list_recent_evidence(12),
        },
    )


class ClaimBody(BaseModel):
    pin: str
    business_date: str
    category: str = ""
    custom_name: str = ""
    amount: float = Field(..., gt=0, le=500000)


class CashTiltBody(BaseModel):
    pin: str
    business_date: str
    amount: float = Field(..., ge=0, le=500000)


class BookingIn(BaseModel):
    pin: str
    guest_name: str = Field(min_length=1, max_length=80)
    party_size: int = Field(default=2, ge=1, le=50)
    booking_date: str
    booking_time: str
    note: str | None = Field(default=None, max_length=500)


class BookingStatusIn(BaseModel):
    pin: str
    status: str


def _parse_booking_date(value: str) -> date:
    try:
        return date.fromisoformat((value or "").strip())
    except ValueError as exc:
        raise HTTPException(400, "Invalid date (use YYYY-MM-DD)") from exc


def _parse_booking_time(value: str) -> str:
    raw = (value or "").strip()
    # Accept HH:MM or HH:MM:SS from <input type="time">
    parts = raw.split(":")
    if len(parts) < 2:
        raise HTTPException(400, "Invalid time (use HH:MM)")
    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except ValueError as exc:
        raise HTTPException(400, "Invalid time (use HH:MM)") from exc
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        raise HTTPException(400, "Invalid time (use HH:MM)")
    return f"{hour:02d}:{minute:02d}"


def _booking_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "guest_name": row["guest_name"],
        "party_size": row["party_size"],
        "booking_date": row["booking_date"],
        "booking_time": row["booking_time"],
        "note": row["note"],
        "status": row["status"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _month_calendar_cells(year: int, month: int, counts: dict[str, int]) -> list[dict[str, Any]]:
    """Build a Mon–Sun calendar grid for the staff bookings view."""
    first = date(year, month, 1)
    # Monday=0 … Sunday=6
    start_pad = first.weekday()
    if month == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month + 1, 1)
    days_in_month = (next_month - first).days
    cells: list[dict[str, Any]] = []
    for _ in range(start_pad):
        cells.append({"empty": True})
    for day_n in range(1, days_in_month + 1):
        d = date(year, month, day_n)
        iso = d.isoformat()
        cells.append(
            {
                "empty": False,
                "day": day_n,
                "iso": iso,
                "count": counts.get(iso, 0),
            }
        )
    while len(cells) % 7:
        cells.append({"empty": True})
    return cells


@app.get("/staff/bookings", response_class=HTMLResponse)
def staff_bookings(request: Request, pin: str = "", month: str = "", day: str = ""):
    if pin != STAFF_PIN:
        return HTMLResponse("Unauthorized", status_code=401)
    today = datetime.now(HK).date()
    if month:
        try:
            y_str, m_str = month.split("-")
            year, mon = int(y_str), int(m_str)
            if mon < 1 or mon > 12:
                raise ValueError
        except ValueError:
            year, mon = today.year, today.month
    else:
        year, mon = today.year, today.month

    selected = today
    if day:
        try:
            selected = date.fromisoformat(day)
        except ValueError:
            selected = today
    elif month:
        selected = date(year, mon, 1)

    # Keep selected day inside the viewed month for the list panel
    if selected.year != year or selected.month != mon:
        if mon == 12:
            last = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            last = date(year, mon + 1, 1) - timedelta(days=1)
        selected = date(year, mon, min(selected.day, last.day))

    conn = connect()
    month_rows = list_bookings_for_month(conn, year, mon)
    day_rows = list_bookings_for_date(conn, selected.isoformat())
    conn.close()

    counts: dict[str, int] = {}
    for row in month_rows:
        key = row["booking_date"]
        counts[key] = counts.get(key, 0) + 1

    if mon == 1:
        prev_m = f"{year - 1}-12"
    else:
        prev_m = f"{year}-{mon - 1:02d}"
    if mon == 12:
        next_m = f"{year + 1}-01"
    else:
        next_m = f"{year}-{mon + 1:02d}"

    return templates.TemplateResponse(
        "staff_bookings.html",
        {
            "request": request,
            "title": "Booking Schedule",
            "pin": pin,
            "year": year,
            "month": mon,
            "month_label": f"{year}-{mon:02d}",
            "prev_month": prev_m,
            "next_month": next_m,
            "today": today.isoformat(),
            "selected": selected.isoformat(),
            "cells": _month_calendar_cells(year, mon, counts),
            "day_bookings": [_booking_dict(r) for r in day_rows],
            "month_count": len(month_rows),
        },
    )


@app.post("/api/staff/bookings")
def staff_create_booking(body: BookingIn):
    if body.pin != STAFF_PIN:
        raise HTTPException(401, "Unauthorized")
    booking_date = _parse_booking_date(body.booking_date).isoformat()
    booking_time = _parse_booking_time(body.booking_time)
    conn = connect()
    try:
        row = create_booking(
            conn,
            guest_name=body.guest_name,
            party_size=body.party_size,
            booking_date=booking_date,
            booking_time=booking_time,
            note=body.note,
        )
    except ValueError as e:
        conn.close()
        raise HTTPException(400, str(e)) from e
    conn.close()
    return {"ok": True, "booking": _booking_dict(row)}


@app.put("/api/staff/bookings/{booking_id}")
def staff_update_booking(booking_id: int, body: BookingIn):
    if body.pin != STAFF_PIN:
        raise HTTPException(401, "Unauthorized")
    booking_date = _parse_booking_date(body.booking_date).isoformat()
    booking_time = _parse_booking_time(body.booking_time)
    conn = connect()
    try:
        row = update_booking(
            conn,
            booking_id,
            guest_name=body.guest_name,
            party_size=body.party_size,
            booking_date=booking_date,
            booking_time=booking_time,
            note=body.note,
        )
    except ValueError as e:
        conn.close()
        raise HTTPException(400, str(e)) from e
    conn.close()
    return {"ok": True, "booking": _booking_dict(row)}


@app.post("/api/staff/bookings/{booking_id}/status")
def staff_booking_status(booking_id: int, body: BookingStatusIn):
    if body.pin != STAFF_PIN:
        raise HTTPException(401, "Unauthorized")
    conn = connect()
    try:
        row = set_booking_status(conn, booking_id, (body.status or "").strip())
    except ValueError as e:
        conn.close()
        raise HTTPException(400, str(e)) from e
    conn.close()
    return {"ok": True, "booking": _booking_dict(row)}


@app.post("/api/staff/claims")
def staff_add_claim(body: ClaimBody):
    if body.pin != STAFF_PIN:
        raise HTTPException(401, "Unauthorized")
    try:
        date.fromisoformat(body.business_date)
    except ValueError as exc:
        raise HTTPException(400, "Invalid business date") from exc
    preset = (body.category or "").strip()
    custom = (body.custom_name or "").strip()
    if custom:
        category = custom[:80]
    elif preset in CLAIM_PRESETS:
        category = preset
    else:
        raise HTTPException(400, "Pick a claim type or enter a custom name")
    conn = connect()
    row = add_claim(
        conn,
        business_date=body.business_date,
        category=category,
        amount=round(float(body.amount), 1),
    )
    claims = list_claims(conn, body.business_date)
    try:
        daily_sales_report(conn, date.fromisoformat(body.business_date))
    except Exception:
        pass
    conn.close()
    total = round(sum(float(c["amount"]) for c in claims), 1)
    return {
        "ok": True,
        "claim": {
            "id": row["id"],
            "category": row["category"],
            "amount": float(row["amount"]),
            "business_date": row["business_date"],
        },
        "claims_total": total,
        "claim_count": len(claims),
    }


@app.delete("/api/staff/claims/{claim_id}")
def staff_delete_claim(claim_id: int, pin: str = ""):
    if pin != STAFF_PIN:
        raise HTTPException(401, "Unauthorized")
    conn = connect()
    ok = delete_claim(conn, claim_id)
    conn.close()
    if not ok:
        raise HTTPException(404, "Claim not found")
    return {"ok": True}


def _sync_daily_sales_for_biz(biz: date) -> dict[str, Any]:
    """Build + upsert one Daily_Sales row (raises on Sheets errors)."""
    if not sheets_configured():
        raise SheetsNotConfigured(
            "Set POLAR_DAILY_SALES_SHEET_ID and POLAR_GSPREAD_KEY on the server."
        )
    conn = connect()
    daily = daily_sales_report(conn, biz)
    monthly = monthly_sales_report(conn, biz.year, biz.month)
    conn.close()
    row = build_daily_sales_sheet_row(
        business_date=biz,
        by_payment_method=daily["by_payment_method"],
        claims_total=float(daily["claims_total"]),
        daily_sales=float(daily["gross_sales"]),
        cash_tilt=float(daily["cash_tilt"]),
        monthly_total=float(monthly["gross_sales"]),
    )
    return upsert_daily_sales_row(row)


def _auto_sync_daily_sales_safe(biz_iso: str) -> None:
    """Best-effort background sync after cash tilt — never raises to the request."""
    try:
        biz = date.fromisoformat(biz_iso)
        _sync_daily_sales_for_biz(biz)
    except Exception:
        # Night close must not fail if Sheets is slow/down.
        return


@app.post("/api/staff/cash-tilt")
def staff_set_cash_tilt(body: CashTiltBody, background_tasks: BackgroundTasks):
    if body.pin != STAFF_PIN:
        raise HTTPException(401, "Unauthorized")
    try:
        date.fromisoformat(body.business_date)
    except ValueError as exc:
        raise HTTPException(400, "Invalid business date") from exc
    conn = connect()
    amount = set_cash_tilt(conn, body.business_date, round(float(body.amount), 1))
    try:
        daily_sales_report(conn, date.fromisoformat(body.business_date))
    except Exception:
        pass
    conn.close()
    auto = False
    if sheets_configured():
        background_tasks.add_task(_auto_sync_daily_sales_safe, body.business_date)
        auto = True
    return {
        "ok": True,
        "business_date": body.business_date,
        "cash_tilt": amount,
        "sheets_auto_sync_queued": auto,
    }


@app.get("/api/staff/whatsapp-sales-report")
def staff_whatsapp_sales_report(pin: str = "", day: str = ""):
    """One-click nightly close text for WhatsApp (wa.me)."""
    if pin != STAFF_PIN:
        raise HTTPException(401, "Unauthorized")
    today_biz = business_date(datetime.now(HK))
    if day:
        try:
            biz = date.fromisoformat(day)
        except ValueError as exc:
            raise HTTPException(400, "Invalid business date") from exc
    else:
        biz = today_biz

    conn = connect()
    daily = daily_sales_report(conn, biz)
    monthly = monthly_sales_report(conn, biz.year, biz.month)
    conn.close()

    message = format_whatsapp_sales_report(
        business_date=biz,
        by_payment_method=daily["by_payment_method"],
        claims_total=float(daily["claims_total"]),
        daily_sales=float(daily["gross_sales"]),
        cash_tilt=float(daily["cash_tilt"]),
        monthly_total=float(monthly["gross_sales"]),
    )
    return {
        "ok": True,
        "business_date": biz.isoformat(),
        "message": message,
        "wa_url": f"https://wa.me/?text={quote(message)}",
    }


@app.post("/api/staff/sync-daily-sales")
def staff_sync_daily_sales(pin: str = Form(...), day: str = Form("")):
    """Upsert tonight's Daily_Sales row into Google Sheets (manual backup)."""
    if pin != STAFF_PIN:
        raise HTTPException(401, "Unauthorized")
    today_biz = business_date(datetime.now(HK))
    if day:
        try:
            biz = date.fromisoformat(day)
        except ValueError as exc:
            raise HTTPException(400, "Invalid business date") from exc
    else:
        biz = today_biz

    try:
        return _sync_daily_sales_for_biz(biz)
    except SheetsNotConfigured as exc:
        raise HTTPException(503, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 — surface Sheets errors to staff
        raise HTTPException(502, f"Google Sheets sync failed: {exc}") from exc


@app.post("/api/staff/import-bank-csv")
async def staff_import_bank_csv(
    pin: str = Form(...),
    account: str = Form("hsbc_ca"),
    file: UploadFile = File(...),
):
    """Tim: upload HSBC CSV → auto Nature → append Bank_Entries (deduped)."""
    if pin != STAFF_PIN:
        raise HTTPException(401, "Unauthorized")
    if account not in {"hsbc_sa", "hsbc_ca"}:
        raise HTTPException(400, "account must be hsbc_sa or hsbc_ca")
    if not sheets_configured():
        raise HTTPException(
            503,
            "Google Sheet sync not configured. Set POLAR_DAILY_SALES_SHEET_ID "
            "and POLAR_GSPREAD_KEY on the server.",
        )
    raw = await file.read()
    if not raw:
        raise HTTPException(400, "Empty CSV file")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    try:
        entries = parse_bank_csv(text, account=account)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if not entries:
        raise HTTPException(400, "No bank rows found in CSV")
    try:
        result = append_bank_entries(entries)
    except SheetsNotConfigured as exc:
        raise HTTPException(503, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"Bank import failed: {exc}") from exc
    result["parsed"] = len(entries)
    return result


@app.post("/api/staff/import-bank-evidence")
async def staff_import_bank_evidence(
    pin: str = Form(...),
    note: str = Form(""),
    txn_date: str = Form(""),
    amount_hint: str = Form(""),
    files: list[UploadFile] = File(...),
):
    """Tim: upload bank / FPS / transit screenshots → disk + Bank_Evidence (+ Drive)."""
    if pin != STAFF_PIN:
        raise HTTPException(401, "Unauthorized")
    if not files:
        raise HTTPException(400, "Choose at least one image or PDF")

    payloads: list[dict] = []
    for f in files:
        raw = await f.read()
        if not raw:
            continue
        payloads.append(
            {
                "filename": f.filename or "evidence",
                "content": raw,
                "content_type": f.content_type or "",
            }
        )
    if not payloads:
        raise HTTPException(400, "Empty upload")

    try:
        return save_and_register(
            payloads,
            note=note,
            txn_date=txn_date,
            amount_hint=amount_hint,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"Evidence upload failed: {exc}") from exc


@app.get("/api/staff/bank-evidence/{evidence_id}")
def staff_get_bank_evidence(evidence_id: str, pin: str = ""):
    """Serve a stored bank evidence file (staff PIN required)."""
    if pin != STAFF_PIN:
        raise HTTPException(401, "Unauthorized")
    path = resolve_evidence_path(evidence_id)
    if path is None or not path.is_file():
        raise HTTPException(404, "Evidence not found")
    import mimetypes

    mime, _ = mimetypes.guess_type(path.name)
    return FileResponse(
        path,
        media_type=mime or "application/octet-stream",
        filename=path.name.partition("_")[2] or path.name,
    )


@app.post("/api/staff/reset-sales")
def staff_reset_sales(pin: str = Form(...), confirm: str = Form("")):
    """Wipe live orders/sessions/events/receipts. Keeps daily report snapshots."""
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
    from .db import count_daily_report_snapshots
    from .paths import DATA_DIR, DB_PATH

    closed = 0
    snaps = 0
    try:
        conn = connect()
        closed = int(
            conn.execute(
                "SELECT COUNT(*) AS c FROM sessions WHERE status = 'closed'"
            ).fetchone()["c"]
        )
        snaps = count_daily_report_snapshots(conn)
        conn.close()
    except Exception:
        pass
    return {
        "ok": True,
        "promo": current_promo(),
        "data_dir": str(DATA_DIR),
        "db_exists": DB_PATH.exists(),
        "closed_sessions": closed,
        "daily_report_snapshots": snaps,
    }
