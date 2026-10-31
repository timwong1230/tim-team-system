"""Boss tab credit must not inflate Purchase · by item / category."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_POLAR = _ROOT / "polar-order"
if str(_POLAR) not in sys.path:
    sys.path.insert(0, str(_POLAR))


def test_boss_credit_excluded_from_item_purchase():
    tmp = tempfile.mkdtemp(prefix="polar-boss-purchase-")
    os.environ["POLAR_DATA_DIR"] = tmp
    os.environ["POLAR_STAFF_PIN"] = "polar2026"

    import importlib

    import app.paths as paths
    import app.db as db
    import app.main as main
    import app.reports as reports

    importlib.reload(paths)
    importlib.reload(db)
    importlib.reload(reports)
    importlib.reload(main)

    from datetime import datetime
    from zoneinfo import ZoneInfo

    from fastapi.testclient import TestClient

    from app.pricing import business_date
    from app.seats import BOSSES, boss_seat_code

    pin = "polar2026"
    boss = BOSSES[0]
    seat = boss_seat_code(boss["id"])
    assert seat

    html = (_POLAR / "templates/staff_reports.html").read_text(encoding="utf-8")
    assert "boss credit excluded" in html.lower() or "boss tab credit" in html.lower()

    src = (_POLAR / "app/reports.py").read_text(encoding="utf-8")
    assert "NOT LIKE 'BOSS%'" in src
    assert "!= 'Credit'" in src or "!= \"Credit\"" in src

    with TestClient(main.app) as client:
        # Boss tab: 5× Coke as credit
        placed = client.post(
            f"/api/boss/{boss['id']}/orders",
            json={"items": [{"item_id": "coke", "qty": 5}]},
        )
        assert placed.status_code == 200, placed.text
        closed = client.post(
            f"/api/staff/bill/{seat}/close",
            data={"pin": pin, "discount_percent": 0},
        )
        assert closed.status_code == 200, closed.text

        # Guest table: 1× Coke as real sale
        client.post(
            "/api/t/TABLE2/welcome",
            json={"guest_name": "Guest", "party_size": 1},
        )
        guest_order = client.post(
            "/api/t/TABLE2/orders",
            json={"items": [{"item_id": "coke", "qty": 1}]},
        )
        assert guest_order.status_code == 200, guest_order.text
        guest_close = client.post(
            "/api/staff/bill/TABLE2/close",
            data={"pin": pin, "discount_percent": 0, "payment_method": "Cash"},
        )
        assert guest_close.status_code == 200, guest_close.text

        conn = db.connect()
        day = business_date(datetime.now(ZoneInfo("Asia/Hong_Kong")))
        purchase = reports.item_purchase_report(conn, year=day.year, month=day.month)
        daily = reports.daily_sales_report(conn, day)
        bosses = reports.monthly_boss_report(conn, day.year, day.month)
        conn.close()

        coke = next((i for i in purchase["by_item"] if i["item_id"] == "coke"), None)
        assert coke is not None, purchase["by_item"]
        assert coke["qty"] == 1, coke  # guest only — not boss 5
        assert abs(float(coke["revenue"]) - 59.0) < 0.01

        non_alc = next(
            (c for c in purchase["by_category"] if c["category_id"] == "non-alcohol"),
            None,
        )
        assert non_alc is not None
        assert non_alc["qty"] == 1

        # Sales also guest-only; boss ledger still tracks credit separately
        assert daily["session_count"] == 1
        assert abs(float(daily["gross_sales"]) - 75.9) < 0.1
        jon = next(b for b in bosses["bosses"] if b["boss_id"] == boss["id"])
        assert jon["item_qty"] == 5
        assert abs(float(jon["total"]) - 295.0) < 0.1

        page = client.get(
            f"/staff/reports?pin={pin}&month={day.year:04d}-{day.month:02d}"
        )
        assert page.status_code == 200
        assert b"boss credit excluded" in page.content.lower() or b"boss tab credit" in page.content.lower()
