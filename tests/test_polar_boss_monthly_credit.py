"""Monthly Boss Report must match closed BOSS* Credit sessions (daily ledger)."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_POLAR = _ROOT / "polar-order"
if str(_POLAR) not in sys.path:
    sys.path.insert(0, str(_POLAR))


def test_monthly_boss_includes_staff_placed_credit():
    tmp = tempfile.mkdtemp(prefix="polar-boss-monthly-")
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
    jon = next(b for b in BOSSES if b["id"] == "jon")
    seat = boss_seat_code(jon["id"])
    assert seat == "BOSSJON"

    html = (_POLAR / "templates/staff_reports.html").read_text(encoding="utf-8")
    assert "Daily credit" in html
    assert "Polar credit (BOSS tabs)" in html

    with TestClient(main.app) as client:
        # Staff places on Boss Jon tab (historically created_by=Staff).
        placed = client.post(
            f"/api/staff/bill/{seat}/orders",
            json={
                "pin": pin,
                "items": [
                    {"item_id": "shisha-regular", "qty": 1},
                    {"item_id": "coke", "qty": 2},
                ],
            },
        )
        assert placed.status_code == 200, placed.text
        assert placed.json()["created_by"] == "Jon"

        closed = client.post(
            f"/api/staff/bill/{seat}/close",
            data={"pin": pin, "discount_percent": 0},
        )
        assert closed.status_code == 200, closed.text
        credit_total = float(closed.json()["total"])

        # Second credit tab same month via boss QR (created_by=Jon).
        placed2 = client.post(
            f"/api/boss/{jon['id']}/orders",
            json={"items": [{"item_id": "coke", "qty": 1}]},
        )
        assert placed2.status_code == 200, placed2.text
        closed2 = client.post(
            f"/api/staff/bill/{seat}/close",
            data={"pin": pin, "discount_percent": 0},
        )
        assert closed2.status_code == 200, closed2.text
        credit_total += float(closed2.json()["total"])

        conn = db.connect()
        day = business_date(datetime.now(ZoneInfo("Asia/Hong_Kong")))
        daily = reports.daily_sales_report(conn, day)
        bosses = reports.monthly_boss_report(conn, day.year, day.month)
        conn.close()

        jon_daily = [s for s in daily["sessions"] if s.get("is_boss") and "Jon" in s["table"]]
        assert len(jon_daily) == 2
        daily_sum = round(sum(float(s["total"]) for s in jon_daily), 1)

        jon_month = next(b for b in bosses["bosses"] if b["boss_id"] == "jon")
        assert jon_month["session_count"] == 2
        assert abs(float(jon_month["total"]) - daily_sum) < 0.05
        assert abs(float(jon_month["total"]) - round(credit_total, 1)) < 0.05
        assert jon_month["by_day"]
        assert jon_month["by_day"][0]["business_date"] == day.isoformat()

        # Still excluded from guest sales
        assert daily["session_count"] == 0
        assert abs(float(daily["gross_sales"])) < 0.01

        page = client.get(
            f"/staff/reports?pin={pin}&month={day.year:04d}-{day.month:02d}"
        )
        assert page.status_code == 200
        assert b"Daily credit" in page.content
        assert str(day.isoformat()).encode() in page.content
