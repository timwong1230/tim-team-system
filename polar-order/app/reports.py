from __future__ import annotations

import sqlite3
from calendar import monthrange
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from .db import (
    format_payment_label,
    get_cash_tilt,
    get_daily_report_snapshot,
    list_session_payments,
    upsert_daily_report_snapshot,
)
from .ops_constants import SPLIT_PAYMENT_METHOD, WHATSAPP_PAYMENT_LINES
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
        has_guest = (
            int(report.get("session_count") or 0) > 0
            or float(report.get("gross_sales") or 0) > 0
        )
        has_boss = int(report.get("boss_session_count") or 0) > 0 or any(
            s.get("is_boss") for s in (report.get("sessions") or [])
        )
        has_ops = (
            float(report.get("claims_total") or 0) > 0
            or float(report.get("cash_tilt") or 0) > 0
        )
        # Persist when guest sales, boss credit bills, claims, or cash tilt exist.
        if not (has_guest or has_boss or has_ops):
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
    sessions = list(snap.get("sessions") or [])
    boss_session_count = sum(1 for s in sessions if s.get("is_boss"))
    return {
        "business_date": biz.isoformat(),
        "window": f"{start.strftime('%Y-%m-%d %H:%M')} → {end.strftime('%Y-%m-%d %H:%M')} (HK)",
        "session_count": int(snap.get("session_count") or 0),
        "boss_session_count": boss_session_count,
        "gross_sales": total,
        "sessions": sessions,
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
    # Include boss Credit bills in the list; still exclude demo practice seats.
    # Guest sales totals ignore boss rows below.
    sessions = conn.execute(
        """
        SELECT s.*, t.label AS table_label, t.code AS table_code, t.zone AS zone
        FROM sessions s
        JOIN tables t ON t.id = s.table_id
        WHERE s.status = 'closed' AND s.closed_at IS NOT NULL
          AND COALESCE(t.zone, '') != 'demo'
        ORDER BY s.closed_at ASC
        """
    ).fetchall()
    rows = []
    total = 0.0
    guest_count = 0
    boss_count = 0
    by_method: dict[str, float] = {}
    for s in sessions:
        closed = _parse_iso(s["closed_at"])
        # Prefer stored business_date; else classify by closed_at
        bd = s["business_date"] or business_date(closed).isoformat()
        if bd != biz.isoformat():
            continue
        amt = float(s["total"] or 0)
        is_boss = _is_boss_session(s)
        method = (s["payment_method"] if "payment_method" in s.keys() else None) or "—"
        pays = list_session_payments(conn, int(s["id"]))
        if pays:
            method_label = format_payment_label(method, pays)
        else:
            method_label = method if method != "—" else None
        if is_boss:
            boss_count += 1
            # Boss Polar credit — list for ops visibility, never count as sales.
            pays = []
            method_label = method_label or method
        else:
            guest_count += 1
            total += amt
            if pays:
                for p in pays:
                    m = p["method"] or "—"
                    by_method[m] = round(by_method.get(m, 0) + float(p["amount"]), 1)
            else:
                # Legacy single-tender rows (no session_payments yet).
                if method != SPLIT_PAYMENT_METHOD:
                    by_method[method] = round(by_method.get(method, 0) + amt, 1)
        rows.append(
            {
                "session_id": s["id"],
                "table": s["table_label"],
                "table_code": s["table_code"],
                "party_size": s["party_size"],
                "discount_percent": s["discount_percent"] or 0,
                "payment_method": method_label,
                "payment_method_raw": method if method != "—" else None,
                "payments": pays,
                "total": amt,
                "closed_at": closed.strftime("%H:%M"),
                "receipt_path": s["receipt_path"],
                "is_boss": is_boss,
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
        "session_count": guest_count,
        "boss_session_count": boss_count,
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
        or live["boss_session_count"]
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
            or any(s.get("is_boss") for s in (snap.get("sessions") or []))
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


def _boss_from_seat_code(table_code: str | None) -> dict | None:
    """Map BOSSJON / bossjon → boss dict."""
    code = (table_code or "").strip().upper()
    if not code.startswith("BOSS"):
        return None
    suffix = code[4:].lower()
    for b in BOSSES:
        if b["id"] == suffix:
            return b
    return None


def monthly_boss_report(conn: sqlite3.Connection, year: int, month: int) -> dict:
    """Per-boss Polar credit for a calendar month (not guest sales).

    Uses closed boss-tab Credit sessions — same ledger as daily Reports —
    so staff-placed BOSS* orders count even when ``created_by='Staff'``.
    Classified by the session ``business_date`` (Polar night).
    """
    last = monthrange(year, month)[1]
    start_biz = date(year, month, 1)
    end_biz = date(year, month, last)

    by_boss: dict[str, dict] = {
        b["name"]: {
            "boss_id": b["id"],
            "boss_name": b["name"],
            "session_count": 0,
            "order_count": 0,
            "item_qty": 0,
            "total": 0.0,
            "items": {},  # item_id -> row
            "sessions": [],
            "by_day": {},  # business_date -> {total, session_count, item_qty}
        }
        for b in BOSSES
    }

    sessions = conn.execute(
        """
        SELECT s.id, s.total, s.closed_at, s.business_date, s.payment_method,
               s.receipt_path, t.label AS table_label, t.code AS table_code,
               t.zone AS zone
        FROM sessions s
        JOIN tables t ON t.id = s.table_id
        WHERE s.status = 'closed'
          AND COALESCE(t.zone, '') = 'boss'
        ORDER BY s.closed_at ASC
        """
    ).fetchall()

    month_sessions: list[sqlite3.Row] = []
    for s in sessions:
        boss = _boss_from_seat_code(s["table_code"])
        if not boss:
            continue
        closed = _parse_iso(s["closed_at"]) if s["closed_at"] else None
        bd_str = s["business_date"] or (
            business_date(closed).isoformat() if closed else None
        )
        if not bd_str:
            continue
        try:
            bd = date.fromisoformat(bd_str)
        except ValueError:
            continue
        if not (start_biz <= bd <= end_biz):
            continue
        month_sessions.append(s)

    session_ids = [int(s["id"]) for s in month_sessions]
    lines_by_session: dict[int, list] = {}
    orders_by_session: dict[int, int] = {}
    if session_ids:
        placeholders = ",".join("?" * len(session_ids))
        order_rows = conn.execute(
            f"""
            SELECT id, session_id
            FROM orders
            WHERE session_id IN ({placeholders})
              AND status != 'cancelled'
            """,
            session_ids,
        ).fetchall()
        order_to_session = {int(o["id"]): int(o["session_id"]) for o in order_rows}
        for o in order_rows:
            sid = int(o["session_id"])
            orders_by_session[sid] = orders_by_session.get(sid, 0) + 1
        if order_to_session:
            oids = list(order_to_session.keys())
            oph = ",".join("?" * len(oids))
            for row in conn.execute(
                f"""
                SELECT oi.order_id, oi.item_id, oi.item_name, oi.qty, oi.line_total
                FROM order_items oi
                WHERE oi.order_id IN ({oph})
                """,
                oids,
            ).fetchall():
                sid = order_to_session[int(row["order_id"])]
                lines_by_session.setdefault(sid, []).append(row)

    for s in month_sessions:
        boss = _boss_from_seat_code(s["table_code"])
        assert boss is not None
        bucket = by_boss[boss["name"]]
        closed = _parse_iso(s["closed_at"]) if s["closed_at"] else None
        bd_str = s["business_date"] or (
            business_date(closed).isoformat() if closed else ""
        )
        lines = lines_by_session.get(int(s["id"]), [])
        # Prefer billed session total (matches daily Reports / PDF credit used).
        sess_total = float(s["total"] or 0)
        if sess_total <= 0 and lines:
            sess_total = sum(float(x["line_total"]) for x in lines)
        sess_qty = sum(int(x["qty"]) for x in lines)
        order_count = orders_by_session.get(int(s["id"]), 0)

        bucket["session_count"] += 1
        bucket["order_count"] += order_count
        bucket["item_qty"] += sess_qty
        bucket["total"] += sess_total
        bucket["sessions"].append(
            {
                "session_id": int(s["id"]),
                "business_date": bd_str,
                "closed_at": closed.strftime("%Y-%m-%d %H:%M") if closed else None,
                "table": s["table_label"],
                "total": round(sess_total, 1),
                "qty": sess_qty,
                "order_count": order_count,
            }
        )
        day_bucket = bucket["by_day"].setdefault(
            bd_str, {"business_date": bd_str, "total": 0.0, "session_count": 0, "item_qty": 0}
        )
        day_bucket["total"] += sess_total
        day_bucket["session_count"] += 1
        day_bucket["item_qty"] += sess_qty

        for row in lines:
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
        day_list = sorted(
            (
                {
                    "business_date": d["business_date"],
                    "total": round(d["total"], 1),
                    "session_count": d["session_count"],
                    "item_qty": d["item_qty"],
                }
                for d in bucket["by_day"].values()
            ),
            key=lambda x: x["business_date"],
        )
        total = round(bucket["total"], 1)
        grand += total
        bosses_out.append(
            {
                "boss_id": bucket["boss_id"],
                "boss_name": bucket["boss_name"],
                "session_count": bucket["session_count"],
                "order_count": bucket["order_count"],
                "item_qty": bucket["item_qty"],
                "total": total,
                "item_rows": item_list,
                "by_day": day_list,
                "sessions": list(reversed(bucket["sessions"]))[:60],
            }
        )

    return {
        "year": year,
        "month": month,
        "label": f"{year}-{month:02d}",
        "gross_total": round(grand, 1),
        "bosses": bosses_out,
    }
