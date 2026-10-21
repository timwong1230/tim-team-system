from __future__ import annotations

import sqlite3
from calendar import monthrange
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from .pricing import business_date, business_day_window

HK = ZoneInfo("Asia/Hong_Kong")


def _parse_iso(s: str) -> datetime:
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=HK)
    return dt.astimezone(HK)


def daily_sales_report(conn: sqlite3.Connection, biz: date) -> dict:
    start, end = business_day_window(biz)
    sessions = conn.execute(
        """
        SELECT s.*, t.label AS table_label, t.code AS table_code
        FROM sessions s
        JOIN tables t ON t.id = s.table_id
        WHERE s.status = 'closed' AND s.closed_at IS NOT NULL
        ORDER BY s.closed_at ASC
        """
    ).fetchall()
    rows = []
    total = 0.0
    for s in sessions:
        closed = _parse_iso(s["closed_at"])
        # Prefer stored business_date; else classify by closed_at
        bd = s["business_date"] or business_date(closed).isoformat()
        if bd != biz.isoformat():
            continue
        amt = float(s["total"] or 0)
        total += amt
        rows.append(
            {
                "session_id": s["id"],
                "table": s["table_label"],
                "party_size": s["party_size"],
                "discount_percent": s["discount_percent"] or 0,
                "total": amt,
                "closed_at": closed.strftime("%H:%M"),
                "receipt_path": s["receipt_path"],
            }
        )
    return {
        "business_date": biz.isoformat(),
        "window": f"{start.strftime('%Y-%m-%d %H:%M')} → {end.strftime('%Y-%m-%d %H:%M')} (HK)",
        "session_count": len(rows),
        "gross_sales": round(total, 1),
        "sessions": rows,
    }


def monthly_sales_report(conn: sqlite3.Connection, year: int, month: int) -> dict:
    last = monthrange(year, month)[1]
    days = []
    month_total = 0.0
    month_sessions = 0
    for d in range(1, last + 1):
        day = daily_sales_report(conn, date(year, month, d))
        if day["session_count"]:
            days.append(
                {
                    "business_date": day["business_date"],
                    "session_count": day["session_count"],
                    "gross_sales": day["gross_sales"],
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
    """Sold qty/revenue for closed sessions in a calendar month's business dates."""
    last = monthrange(year, month)[1]
    start_biz = date(year, month, 1)
    end_biz = date(year, month, last)
    start_dt, _ = business_day_window(start_biz)
    # include last day's window end
    _, end_dt = business_day_window(end_biz)

    # Pull closed sessions in month by business_date when set, else by closed_at window
    sessions = conn.execute(
        """
        SELECT id, business_date, closed_at, status
        FROM sessions
        WHERE status = 'closed'
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
