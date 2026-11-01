"""Monthly Total must accumulate every business day in the month (MTD)."""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import date
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_POLAR = _ROOT / "polar-order"
if str(_POLAR) not in sys.path:
    sys.path.insert(0, str(_POLAR))


def test_monthly_total_sums_prior_nights_in_month():
    tmp = tempfile.mkdtemp(prefix="polar-mtd-")
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

    from fastapi.testclient import TestClient

    pin = "polar2026"
    with TestClient(main.app) as client:
        # Open two guest tables so we have sessions to stamp.
        assert client.post(
            "/api/t/TABLE1/welcome", json={"guest_name": "A", "party_size": 2}
        ).status_code == 200
        assert client.post(
            "/api/t/TABLE2/welcome", json={"guest_name": "B", "party_size": 2}
        ).status_code == 200

        conn = db.connect()
        t1 = conn.execute("SELECT id FROM tables WHERE code='TABLE1'").fetchone()["id"]
        t2 = conn.execute("SELECT id FROM tables WHERE code='TABLE2'").fetchone()["id"]
        s1 = conn.execute(
            "SELECT id FROM sessions WHERE table_id=? AND status='open'", (t1,)
        ).fetchone()["id"]
        s2 = conn.execute(
            "SELECT id FROM sessions WHERE table_id=? AND status='open'", (t2,)
        ).fetchone()["id"]
        conn.execute(
            """
            UPDATE sessions SET status='closed', total=1000, payment_method='Cash',
              business_date='2026-11-01', closed_at='2026-11-01T18:00:00+08:00'
            WHERE id=?
            """,
            (s1,),
        )
        conn.execute(
            """
            UPDATE sessions SET status='closed', total=2500, payment_method='Visa',
              business_date='2026-11-05', closed_at='2026-11-05T20:00:00+08:00'
            WHERE id=?
            """,
            (s2,),
        )
        conn.commit()

        mtd_early = reports.month_to_date_sales(conn, date(2026, 11, 1))
        assert mtd_early["gross_sales"] == 1000.0
        assert len(mtd_early["days"]) == 1

        mtd = reports.month_to_date_sales(conn, date(2026, 11, 5))
        assert mtd["gross_sales"] == 3500.0
        assert len(mtd["days"]) == 2
        assert [d["business_date"] for d in mtd["days"]] == [
            "2026-11-01",
            "2026-11-05",
        ]

        # Full November still only has these two nights.
        monthly = reports.monthly_sales_report(conn, 2026, 11)
        assert monthly["gross_sales"] == 3500.0
        conn.close()

        wa = client.get(f"/api/staff/whatsapp-sales-report?pin={pin}&day=2026-11-05")
        assert wa.status_code == 200, wa.text
        body = wa.json()
        assert body["monthly_total"] == 3500.0
        assert body["monthly_days"] == 2
        assert "Daily Sales: $2500" in body["message"]
        assert "Monthly Total: $3500" in body["message"]

        page = client.get(f"/staff/reports?pin={pin}&day=2026-11-05&month=2026-11")
        assert page.status_code == 200
        assert b"Monthly Total" in page.content
        assert b"$3500" in page.content or b"3500" in page.content
