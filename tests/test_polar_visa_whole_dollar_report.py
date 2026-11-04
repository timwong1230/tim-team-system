"""Closed Visa bills store whole-HKD totals so daily Visa matches the terminal."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_POLAR = _ROOT / "polar-order"
sys.path = [str(_POLAR)] + [p for p in sys.path if Path(p).resolve() != _ROOT]
for _name in list(sys.modules):
    if _name == "app" or _name.startswith("app."):
        del sys.modules[_name]


def test_visa_close_stores_whole_dollar_matching_report():
    tmp = tempfile.mkdtemp(prefix="polar-visa-whole-")
    os.environ["POLAR_DATA_DIR"] = tmp
    os.environ["POLAR_STAFF_PIN"] = "polar2026"

    import importlib

    import app.paths as paths
    import app.db as db
    import app.main as main
    import app.pricing as pricing
    import app.reports as reports

    importlib.reload(paths)
    importlib.reload(db)
    importlib.reload(pricing)
    importlib.reload(reports)
    importlib.reload(main)

    from datetime import date

    from fastapi.testclient import TestClient

    pin = "polar2026"
    with TestClient(main.app) as client:
        # Happy Hour–style tenth: unit priced as 54.4 in DB via not-on-menu
        placed = client.post(
            "/api/staff/bill/TABLE2/orders",
            json={
                "pin": pin,
                "guest_name": "Visa Guest",
                "party_size": 1,
                "items": [
                    {
                        "item_id": "not-on-menu",
                        "qty": 1,
                        "custom_name": "Promo drink",
                        "custom_price": 54.4,
                    }
                ],
            },
        )
        assert placed.status_code == 200, placed.text

        closed = client.post(
            f"/api/staff/bill/TABLE2/close",
            data={
                "pin": pin,
                "discount_percent": 0,
                "party_size": 1,
                "payment_method": "Visa",
            },
        )
        assert closed.status_code == 200, closed.text
        payload = closed.json()
        assert payload.get("ok") is True
        total = float(payload["total"])
        assert total == int(total)
        # 54.4 + snack 10 + ceil(6.44)=7 → raw 71.4 → whole $71
        assert total == 71.0

        conn = db.connect()
        row = conn.execute(
            "SELECT total, payment_method FROM sessions WHERE status='closed' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        biz = conn.execute(
            "SELECT business_date FROM sessions WHERE status='closed' ORDER BY id DESC LIMIT 1"
        ).fetchone()["business_date"]
        daily = reports.daily_sales_report(conn, date.fromisoformat(biz))
        conn.close()

        assert float(row["total"]) == 71.0
        assert row["payment_method"] == "Visa"
        by_pay = {p["method"]: p["total"] for p in daily["by_payment_method"]}
        assert by_pay.get("Visa") == 71.0
