"""Boss tabs close as Polar credit — no payment method, excluded from sales."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_POLAR = _ROOT / "polar-order"
if str(_POLAR) not in sys.path:
    sys.path.insert(0, str(_POLAR))


def test_boss_tab_closes_as_credit_not_sales():
    tmp = tempfile.mkdtemp(prefix="polar-boss-credit-")
    os.environ["POLAR_DATA_DIR"] = tmp
    os.environ["POLAR_STAFF_PIN"] = "polar2026"

    import importlib

    import app.paths as paths
    import app.db as db
    import app.main as main
    import app.reports as reports
    import app.ops_constants as ops

    importlib.reload(paths)
    importlib.reload(db)
    importlib.reload(ops)
    importlib.reload(reports)
    importlib.reload(main)

    from datetime import datetime
    from zoneinfo import ZoneInfo

    from fastapi.testclient import TestClient

    from app.ops_constants import BOSS_CREDIT_METHOD, PAYMENT_METHODS
    from app.pricing import business_date
    from app.seats import BOSSES, boss_seat_code

    pin = "polar2026"
    boss = BOSSES[0]
    seat = boss_seat_code(boss["id"])
    assert seat

    bill_html = (_POLAR / "templates/staff_bill.html").read_text(encoding="utf-8")
    assert "Credit used" in bill_html
    assert "Record credit & open PDF" in bill_html
    assert "Polar credit" in bill_html

    with TestClient(main.app) as client:
        # Place a boss order (opens session)
        placed = client.post(
            f"/api/boss/{boss['id']}/orders",
            json={"items": [{"item_id": "coke", "qty": 1}]},
        )
        assert placed.status_code == 200, placed.text

        page = client.get(f"/staff/bill/{seat}?pin={pin}")
        assert page.status_code == 200
        assert b"Credit used" in page.content
        assert b"Record credit & open PDF" in page.content
        assert b"Polar credit" in page.content
        # Guest payment picker must not appear on boss bills
        assert b"pay-method-card" not in page.content
        assert b"Required before closing the table" not in page.content
        for m in PAYMENT_METHODS:
            assert m.encode() not in page.content

        # Close without payment_method — should succeed as Credit
        closed = client.post(
            f"/api/staff/bill/{seat}/close",
            data={"pin": pin, "discount_percent": 0},
        )
        assert closed.status_code == 200, closed.text
        payload = closed.json()
        assert payload["ok"] is True
        sid = payload["session_id"]
        assert float(payload["total"]) > 0

        conn = db.connect()
        row = conn.execute(
            "SELECT payment_method, total, status FROM sessions WHERE id = ?",
            (sid,),
        ).fetchone()
        assert row["status"] == "closed"
        assert row["payment_method"] == BOSS_CREDIT_METHOD
        credit_total = float(row["total"] or 0)
        assert credit_total > 0

        day = business_date(datetime.now(ZoneInfo("Asia/Hong_Kong")))
        daily = reports.daily_sales_report(conn, day)
        conn.close()

        # Boss credit must not inflate guest sales / payment tender breakdown
        assert daily["gross_sales"] == 0
        assert daily["session_count"] == 0
        assert all(p["method"] != BOSS_CREDIT_METHOD for p in daily["by_payment_method"])

        # Sending a fake tender on boss close is ignored — still Credit
        placed2 = client.post(
            f"/api/boss/{boss['id']}/orders",
            json={"items": [{"item_id": "coke", "qty": 2}]},
        )
        assert placed2.status_code == 200, placed2.text
        closed2 = client.post(
            f"/api/staff/bill/{seat}/close",
            data={"pin": pin, "discount_percent": 0, "payment_method": "Cash"},
        )
        assert closed2.status_code == 200, closed2.text
        sid2 = closed2.json()["session_id"]
        conn = db.connect()
        row2 = conn.execute(
            "SELECT payment_method FROM sessions WHERE id = ?", (sid2,)
        ).fetchone()
        assert row2["payment_method"] == BOSS_CREDIT_METHOD
        daily2 = reports.daily_sales_report(conn, day)
        conn.close()
        assert daily2["gross_sales"] == 0
