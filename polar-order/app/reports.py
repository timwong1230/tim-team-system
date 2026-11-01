from __future__ import annotations

import sqlite3
from calendar import monthrange
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from .db import (
    get_cash_tilt,
    get_daily_report_snapshot,
    upsert_daily_report_snapshot,
)
from .ops_constants import WHATSAPP_PAYMENT_LINES
from .pricing import business_date, business_day_window
from .seats import BOSSES

HK = ZoneInfo("Asia/Hong_Kong")


def _parse_iso(s: str) -> datetime:
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=HK)
    return dt.astimezone(HK)


def _is_boss_session(s: sqlite3.Row) -> bool:
    """Boss personal tabs are excluded from guest sales reports."""
    zone = s["zone"] if "zone" in s.keys() else None
    return (zone or "") == "boss"


def _persist_daily_snapshot(
    conn: sqlite3.Connection, report: dict, *, force: bool = False
) -> None:
    """Save live day totals so Reports still work after sessions are wiped."""
    if not force:
        if int(report.get("session_count") or 0) <= 0 and float(report.get("gross_sales") or 0) <= 0:
            # Still persist if claims / cash tilt were recorded for the night.
            if float(report.get("claims_total") or 0) <= 0 and float(report.get("cash_tilt") or 0) <= 0:
                return
    upsert_daily_report_snapshot(
        conn,
        business_date=str(report["business_date"]),
        gross_sales=float(report.get("gross_sales") or 0),
        session_count=int(report.get("session_count") or 0),
        claims_total=float(report.get("claims_total") or 0),
        cash_tilt=float(report.get("cash_tilt") or 0),
        by_payment_method=list(report.get("by_payment_method") or []),
        sessions=list(report.get("sessions") or []),
        claims=list(report.get("claims") or []),
    )


def _report_from_snapshot(biz: date, snap: dict, *, start: datetime, end: datetime) -> dict:
    claims = list(snap.get("claims") or [])
    claims_total = round(float(snap.get("claims_total") or 0), 1)
    total = round(float(snap.get("gross_sales") or 0), 1)
    return {
        "business_date": biz.isoformat(),
        "window": f"{start.strftime('%Y-%m-%d %H:%M')} → {end.strftime('%Y-%m-%d %H:%M')} (HK)",
        "session_count": int(snap.get("session_count") or 0),
        "gross_sales": total,
        "sessions": list(snap.get("sessions") or []),
        "by_payment_method": list(snap.get("by_payment_method") or []),
        "claims": claims,
        "claims_total": claims_total,
        "net_after_claims": round(total - claims_total, 1),
        "cash_tilt": round(float(snap.get("cash_tilt") or 0), 1),
        "from_snapshot": True,
        "snapshot_updated_at": snap.get("updated_at"),
    }


def daily_sales_report(
    conn: sqlite3.Connection,
    biz: date,
    *,
    use_snapshot_fallback: bool = True,
    force_snapshot: bool = False,
) -> dict:
    start, end = business_day_window(biz)
    sessions = conn.execute(
        """
        SELECT s.*, t.label AS table_label, t.code AS table_code, t.zone AS zone
        FROM sessions s
        JOIN tables t ON t.id = s.table_id
        WHERE s.status = 'closed' AND s.closed_at IS NOT NULL
          AND COALESCE(t.zone, '') NOT IN ('boss', 'demo')
        ORDER BY s.closed_at ASC
        """
    ).fetchall()
    rows = []
    total = 0.0
    by_method: dict[str, float] = {}
    for s in sessions:
        closed = _parse_iso(s["closed_at"])
        # Prefer stored business_date; else classify by closed_at
        bd = s["business_date"] or business_date(closed).isoformat()
        if bd != biz.isoformat():
            continue
        amt = float(s["total"] or 0)
        total += amt
        method = (s["payment_method"] if "payment_method" in s.keys() else None) or "—"
        by_method[method] = round(by_method.get(method, 0) + amt, 1)
        rows.append(
            {
                "session_id": s["id"],
                "table": s["table_label"],
                "table_code": s["table_code"],
                "party_size": s["party_size"],
                "discount_percent": s["discount_percent"] or 0,
                "payment_method": method if method != "—" else None,
                "total": amt,
                "closed_at": closed.strftime("%H:%M"),
                "receipt_path": s["receipt_path"],
            }
        )

    claims = conn.execute(
        """
        SELECT * FROM claims
        WHERE business_date = ?
        ORDER BY id ASC
        """,
        (biz.isoformat(),),
    ).fetchall()
    claim_rows = [
        {
            "id": c["id"],
            "category": c["category"],
            "amount": float(c["amount"] or 0),
            "created_at": c["created_at"],
        }
        for c in claims
    ]
    claims_total = round(sum(c["amount"] for c in claim_rows), 1)
    cash_tilt = round(get_cash_tilt(conn, biz.isoformat()), 1)

    live = {
        "business_date": biz.isoformat(),
        "window": f"{start.strftime('%Y-%m-%d %H:%M')} → {end.strftime('%Y-%m-%d %H:%M')} (HK)",
        "session_count": len(rows),
        "gross_sales": round(total, 1),
        "sessions": rows,
        "by_payment_method": [
            {"method": m, "total": t}
            for m, t in sorted(by_method.items(), key=lambda x: (-x[1], x[0]))
        ],
        "claims": claim_rows,
        "claims_total": claims_total,
        "net_after_claims": round(total - claims_total, 1),
        "cash_tilt": cash_tilt,
        "from_snapshot": False,
        "snapshot_updated_at": None,
    }

    # Live night still open / recorded — keep a durable snapshot.
    if (
        live["session_count"]
        or live["claims_total"]
        or live["cash_tilt"]
        or live["gross_sales"]
        or force_snapshot
    ):
        _persist_daily_snapshot(conn, live, force=force_snapshot)
        return live

    # Past day after a reset/redeploy wipe — fall back to saved close.
    if use_snapshot_fallback:
        snap = get_daily_report_snapshot(conn, biz.isoformat())
        if snap and (
            int(snap.get("session_count") or 0)
            or float(snap.get("gross_sales") or 0)
            or float(snap.get("claims_total") or 0)
            or float(snap.get("cash_tilt") or 0)
        ):
            return _report_from_snapshot(biz, snap, start=start, end=end)
    return live


def _money_line(amount: float) -> str:
    return f"${int(round(float(amount or 0)))}"


def _sum_methods(by_method: dict[str, float], aliases: tuple[str, ...]) -> float:
    total = 0.0
    for alias in aliases:
        total += float(by_method.get(alias, 0) or 0)
    return round(total, 1)


def payment_totals_for_sheet(by_payment_method: list[dict]) -> dict[str, float]:
    """Map WhatsApp payment labels → amounts for Daily_Sales columns."""
    methods = {str(p["method"]): float(p["total"]) for p in by_payment_method}
    return {
        label: _sum_methods(methods, aliases)
        for label, aliases in WHATSAPP_PAYMENT_LINES
    }


def build_daily_sales_sheet_row(
    *,
    business_date: date,
    by_payment_method: list[dict],
    claims_total: float,
    daily_sales: float,
    cash_tilt: float,
    monthly_total: float,
    synced_at: str | None = None,
) -> dict[str, str | float]:
    """One Daily_Sales ledger row (aligned with WhatsApp close fields)."""
    from datetime import timezone

    pay = payment_totals_for_sheet(by_payment_method)
    stamp = synced_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "business_date": business_date.isoformat(),
        "Cash": pay.get("Cash", 0),
        "Visa": pay.get("Visa", 0),
        "Master": pay.get("Master", 0),
        "AE": pay.get("AE", 0),
        "Alipay": pay.get("Alipay", 0),
        "UnionPay": pay.get("UnionPay", 0),
        "WeChat pay": pay.get("WeChat pay", 0),
        "Deposit": pay.get("Deposit", 0),
        "Claim": round(float(claims_total or 0), 1),
        "Daily Sales": round(float(daily_sales or 0), 1),
        "Cash Tilt": round(float(cash_tilt or 0), 1),
        "Monthly Total": round(float(monthly_total or 0), 1),
        "synced_at": stamp,
    }


def format_whatsapp_sales_report(
    *,
    business_date: date,
    by_payment_method: list[dict],
    claims_total: float,
    daily_sales: float,
    cash_tilt: float,
    monthly_total: float,
) -> str:
    """Build the nightly WhatsApp close message (DD-MM-YYYY)."""
    pay = payment_totals_for_sheet(by_payment_method)
    lines = [
        "Sales report",
        business_date.strftime("%d-%m-%Y"),
        "",
    ]
    for label, _aliases in WHATSAPP_PAYMENT_LINES:
        lines.append(f"{label}: {_money_line(pay.get(label, 0))}")
    lines.append(f"Claim: {_money_line(claims_total)}")
    lines.append(f"Daily Sales: {_money_line(daily_sales)}")
    lines.append("")
    lines.append(f"Cash Tilt: {_money_line(cash_tilt)}")
    lines.append(f"Monthly Total: {_money_line(monthly_total)}")
    return "\n".join(lines)


def monthly_sales_report(conn: sqlite3.Connection, year: int, month: int) -> dict:
    last = monthrange(year, month)[1]
    days = []
    month_total = 0.0
    month_sessions = 0
    for d in range(1, last + 1):
        day = daily_sales_report(conn, date(year, month, d))
        if (
            day["session_count"]
            or day["gross_sales"]
            or day["claims_total"]
            or day["cash_tilt"]
        ):
            days.append(
                {
                    "business_date": day["business_date"],
                    "session_count": day["session_count"],
                    "gross_sales": day["gross_sales"],
                    "from_snapshot": bool(day.get("from_snapshot")),
                }
            )
            month_total += day["gross_sales"]
            month_sessions += day["session_count"]
    return {
        "year": year,
        "month": month,
        "label": f"{year}-{month:02d}",
        "session_count": month_sessions,
        "gross_sales": round(month_total, 1),
        "days": days,
    }


def item_purchase_report(
    conn: sqlite3.Connection,
    *,
    year: int,
    month: int,
) -> dict:
    """Sold qty/revenue for closed guest sessions in a calendar month's business dates.

    Boss tabs are Polar credit — never guest purchase / stock-sold counts.
    Excludes ``zone=boss|demo``, ``BOSS*`` seat codes, and ``payment_method=Credit``.
    """
    last = monthrange(year, month)[1]
    start_biz = date(year, month, 1)
    end_biz = date(year, month, last)
    start_dt, _ = business_day_window(start_biz)
    # include last day's window end
    _, end_dt = business_day_window(end_biz)

    # Pull closed guest sessions in month (exclude boss credit + demo)
    sessions = conn.execute(
        """
        SELECT s.id, s.business_date, s.closed_at, s.status
        FROM sessions s
        JOIN tables t ON t.id = s.table_id
        WHERE s.status = 'closed'
          AND COALESCE(t.zone, '') NOT IN ('boss', 'demo')
          AND UPPER(COALESCE(t.code, '')) NOT LIKE 'BOSS%'
          AND COALESCE(s.payment_method, '') != 'Credit'
        """
    ).fetchall()
    session_ids = []
    for s in sessions:
        if s["business_date"]:
            try:
                bd = date.fromisoformat(s["business_date"])
            except ValueError:
                continue
            if start_biz <= bd <= end_biz:
                session_ids.append(s["id"])
        elif s["closed_at"]:
            closed = _parse_iso(s["closed_at"])
            if start_dt <= closed < end_dt:
                session_ids.append(s["id"])

    by_item: dict[str, dict] = {}
    by_category: dict[str, dict] = {}
    if session_ids:
        placeholders = ",".join("?" * len(session_ids))
        lines = conn.execute(
            f"""
            SELECT oi.item_id, oi.item_name, oi.category_id, oi.qty, oi.line_total,
                   COALESCE(mc.name, oi.category_id) AS category_name
            FROM order_items oi
            JOIN orders o ON o.id = oi.order_id
            LEFT JOIN menu_categories mc ON mc.id = oi.category_id
            WHERE o.session_id IN ({placeholders}) AND o.status != 'cancelled'
            """,
            session_ids,
        ).fetchall()
        for row in lines:
            iid = row["item_id"]
            cid = row["category_id"]
            by_item.setdefault(
                iid,
                {
                    "item_id": iid,
                    "item_name": row["item_name"],
                    "category_id": cid,
                    "category_name": row["category_name"],
                    "qty": 0,
                    "revenue": 0.0,
                },
            )
            by_item[iid]["qty"] += int(row["qty"])
            by_item[iid]["revenue"] += float(row["line_total"])

            by_category.setdefault(
                cid,
                {
                    "category_id": cid,
                    "category_name": row["category_name"],
                    "qty": 0,
                    "revenue": 0.0,
                },
            )
            by_category[cid]["qty"] += int(row["qty"])
            by_category[cid]["revenue"] += float(row["line_total"])

    items = sorted(by_item.values(), key=lambda x: (-x["revenue"], x["item_name"]))
    cats = sorted(by_category.values(), key=lambda x: (-x["revenue"], x["category_name"]))
    for x in items:
        x["revenue"] = round(x["revenue"], 1)
    for x in cats:
        x["revenue"] = round(x["revenue"], 1)

    return {
        "year": year,
        "month": month,
        "label": f"{year}-{month:02d}",
        "by_category": cats,
        "by_item": items,
    }


def monthly_boss_report(conn: sqlite3.Connection, year: int, month: int) -> dict:
    """Per-boss order totals for a calendar month (not guest sales).

    Counts non-cancelled order lines tagged created_by = boss name,
    classified by business_date of the order timestamp.
    """
    last = monthrange(year, month)[1]
    start_biz = date(year, month, 1)
    end_biz = date(year, month, last)
    start_dt, _ = business_day_window(start_biz)
    _, end_dt = business_day_window(end_biz)

    boss_names = {b["name"]: b for b in BOSSES}
    by_boss: dict[str, dict] = {
        b["name"]: {
            "boss_id": b["id"],
            "boss_name": b["name"],
            "order_count": 0,
            "item_qty": 0,
            "total": 0.0,
            "items": {},  # item_id -> row
            "orders": [],
        }
        for b in BOSSES
    }

    orders = conn.execute(
        """
        SELECT o.id, o.created_by, o.created_at, o.status, o.note,
               t.label AS table_label
        FROM orders o
        JOIN tables t ON t.id = o.table_id
        WHERE o.status != 'cancelled'
          AND o.created_by IS NOT NULL
        ORDER BY o.id ASC
        """
    ).fetchall()

    order_ids_in_month: list[int] = []
    order_meta: dict[int, sqlite3.Row] = {}
    for o in orders:
        if o["created_by"] not in boss_names:
            continue
        created = _parse_iso(o["created_at"])
        bd = business_date(created)
        if not (start_biz <= bd <= end_biz):
            # also allow if within window spanning month edges
            if not (start_dt <= created < end_dt):
                continue
        order_ids_in_month.append(o["id"])
        order_meta[o["id"]] = o

    if order_ids_in_month:
        placeholders = ",".join("?" * len(order_ids_in_month))
        lines = conn.execute(
            f"""
            SELECT oi.order_id, oi.item_id, oi.item_name, oi.qty, oi.line_total
            FROM order_items oi
            WHERE oi.order_id IN ({placeholders})
            """,
            order_ids_in_month,
        ).fetchall()
        lines_by_order: dict[int, list] = {}
        for row in lines:
            lines_by_order.setdefault(row["order_id"], []).append(row)

        for oid in order_ids_in_month:
            o = order_meta[oid]
            bucket = by_boss[o["created_by"]]
            o_lines = lines_by_order.get(oid, [])
            o_total = sum(float(x["line_total"]) for x in o_lines)
            o_qty = sum(int(x["qty"]) for x in o_lines)
            bucket["order_count"] += 1
            bucket["item_qty"] += o_qty
            bucket["total"] += o_total
            created = _parse_iso(o["created_at"])
            bucket["orders"].append(
                {
                    "order_id": oid,
                    "created_at": created.strftime("%Y-%m-%d %H:%M"),
                    "table": o["table_label"],
                    "total": round(o_total, 1),
                    "qty": o_qty,
                    "note": o["note"],
                }
            )
            for row in o_lines:
                iid = row["item_id"]
                items = bucket["items"]
                items.setdefault(
                    iid,
                    {
                        "item_id": iid,
                        "item_name": row["item_name"],
                        "qty": 0,
                        "revenue": 0.0,
                    },
                )
                items[iid]["qty"] += int(row["qty"])
                items[iid]["revenue"] += float(row["line_total"])

    bosses_out = []
    grand = 0.0
    for b in BOSSES:
        bucket = by_boss[b["name"]]
        item_list = sorted(
            bucket["items"].values(),
            key=lambda x: (-x["revenue"], x["item_name"]),
        )
        for x in item_list:
            x["revenue"] = round(x["revenue"], 1)
        total = round(bucket["total"], 1)
        grand += total
        bosses_out.append(
            {
                "boss_id": bucket["boss_id"],
                "boss_name": bucket["boss_name"],
                "order_count": bucket["order_count"],
                "item_qty": bucket["item_qty"],
                "total": total,
                "item_rows": item_list,
                "orders": list(reversed(bucket["orders"]))[:40],
            }
        )

    return {
        "year": year,
        "month": month,
        "label": f"{year}-{month:02d}",
        "gross_total": round(grand, 1),
        "bosses": bosses_out,
    }
