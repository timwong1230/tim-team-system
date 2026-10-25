"""Cash tilt persistence + WhatsApp nightly sales report."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_POLAR = _ROOT / "polar-order"
if str(_POLAR) not in sys.path:
    sys.path.insert(0, str(_POLAR))


def test_cash_tilt_and_whatsapp_sales_report():
    tmp = tempfile.mkdtemp(prefix="polar-wa-tilt-")
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

    from datetime import date, datetime
    from zoneinfo import ZoneInfo

    from fastapi.testclient import TestClient

    from app.ops_constants import PAYMENT_METHODS
    from app.pricing import business_date
    from app.reports import format_whatsapp_sales_report

    assert "Deposit" in PAYMENT_METHODS

    text = format_whatsapp_sales_report(
        business_date=date(2026, 10, 25),
        by_payment_method=[
            {"method": "Cash", "total": 1000},
            {"method": "Visa", "total": 500},
            {"method": "Mastercard", "total": 200},
            {"method": "American Express", "total": 100},
            {"method": "AlipayHK", "total": 80},
            {"method": "UnionPay", "total": 50},
            {"method": "WeChat pay", "total": 40},
            {"method": "Deposit", "total": 30},
        ],
        claims_total=120,
        daily_sales=2000,
        cash_tilt=15,
        monthly_total=45000,
    )
    assert text.startswith("Sales report\n25-10-2026\n")
    assert "Cash: $1000" in text
    assert "Visa: $500" in text
    assert "Master: $200" in text
    assert "AE: $100" in text
    assert "Alipay: $80" in text
    assert "UnionPay: $50" in text
    assert "WeChat pay: $40" in text
    assert "Deposit: $30" in text
    assert "Claim: $120" in text
    assert "Daily Sales: $2000" in text
    assert "Cash Tilt: $15" in text
    assert "Monthly Total: $45000" in text

    pin = "polar2026"
    with TestClient(main.app) as client:
        client.post(
            "/api/t/TABLE5/welcome",
            json={"guest_name": "Pat", "party_size": 2},
        )
        client.post(
            "/api/t/TABLE5/orders",
            json={"items": [{"item_id": "coke", "qty": 2}]},
        )
        closed = client.post(
            "/api/staff/bill/TABLE5/close",
            data={
                "pin": pin,
                "discount_percent": 0,
                "payment_method": "Cash",
            },
        )
        assert closed.status_code == 200, closed.text
        sale = float(closed.json()["total"])

        day = business_date(datetime.now(ZoneInfo("Asia/Hong_Kong"))).isoformat()

        claim = client.post(
            "/api/staff/claims",
            json={
                "pin": pin,
                "business_date": day,
                "category": "Ice",
                "amount": 50,
            },
        )
        assert claim.status_code == 200, claim.text

        tilt = client.post(
            "/api/staff/cash-tilt",
            json={"pin": pin, "business_date": day, "amount": 88},
        )
        assert tilt.status_code == 200, tilt.text
        assert tilt.json()["cash_tilt"] == 88.0

        page = client.get(f"/staff/reports?pin={pin}&day={day}")
        assert page.status_code == 200
        assert b"Cash Tilt" in page.content
        assert b"WhatsApp Sales report" in page.content
        assert b'id="cashTiltAmount"' in page.content
        assert b"Open WhatsApp Sales report" in page.content

        wa = client.get(
            f"/api/staff/whatsapp-sales-report?pin={pin}&day={day}"
        )
        assert wa.status_code == 200, wa.text
        payload = wa.json()
        assert payload["ok"] is True
        assert payload["wa_url"].startswith("https://wa.me/?text=")
        msg = payload["message"]
        assert "Sales report" in msg
        assert f"Cash: ${int(round(sale))}" in msg
        assert "Claim: $50" in msg
        assert f"Daily Sales: ${int(round(sale))}" in msg
        assert "Cash Tilt: $88" in msg
        assert "Monthly Total:" in msg

        conn = db.connect()
        assert db.get_cash_tilt(conn, day) == 88.0
        conn.close()

        # Save again updates
        tilt2 = client.post(
            "/api/staff/cash-tilt",
            json={"pin": pin, "business_date": day, "amount": 0},
        )
        assert tilt2.status_code == 200
        assert tilt2.json()["cash_tilt"] == 0.0
