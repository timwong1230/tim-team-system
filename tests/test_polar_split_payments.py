"""Same-table split payment: multiple methods that sum to amount due."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_POLAR = _ROOT / "polar-order"
if str(_POLAR) not in sys.path:
    sys.path.insert(0, str(_POLAR))


def test_split_payments_on_close_and_daily_sales():
    tmp = tempfile.mkdtemp(prefix="polar-split-pay-")
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

    from app.ops_constants import SPLIT_PAYMENT_METHOD
    from app.pricing import business_date

    pin = "polar2026"
    with TestClient(main.app) as client:
        client.post(
            "/api/t/TABLE3/welcome",
            json={"guest_name": "Splitters", "party_size": 2},
        )
        client.post(
            "/api/t/TABLE3/orders",
            json={"items": [{"item_id": "coke", "qty": 2}]},
        )
        # coke $59 × 2 = 118 + snack 20 + service ceil((118+20)*0.1)=14 → 152
        preview = client.get(f"/staff/bill/TABLE3?pin={pin}")
        assert preview.status_code == 200

        conn = db.connect()
        table = db.get_table_by_code(conn, "TABLE3")
        sess = db.get_open_session(conn, table["id"])
        assert sess is not None
        # Force known total path via close with payments that match computed bill.
        # Close once with a probe single payment to learn total, then reopen? Easier:
        # compute from API by closing with exact split after reading amount due from page.
        import re

        m = re.search(r'id="vTotal"[^>]*>\$([0-9.]+)', preview.text)
        assert m, preview.text[:500]
        total = float(m.group(1))
        half = round(total / 2, 1)
        # Adjust so two parts sum exactly
        a = round(total - half, 1)
        b = half
        assert abs(a + b - total) < 0.05

        closed = client.post(
            "/api/staff/bill/TABLE3/close",
            data={
                "pin": pin,
                "discount_percent": 0,
                "party_size": 2,
                "payments_json": (
                    f'[{{"method":"Cash","amount":{a}}},'
                    f'{{"method":"Visa","amount":{b}}}]'
                ),
            },
        )
        assert closed.status_code == 200, closed.text
        session_id = closed.json()["session_id"]

        row = db.get_session(conn, session_id)
        assert row["status"] == "closed"
        assert row["payment_method"] == SPLIT_PAYMENT_METHOD
        pays = db.list_session_payments(conn, session_id)
        assert len(pays) == 2
        assert {p["method"] for p in pays} == {"Cash", "Visa"}
        assert abs(sum(p["amount"] for p in pays) - float(row["total"])) < 0.05

        daily = reports.daily_sales_report(conn, business_date())
        methods = {p["method"]: p["total"] for p in daily["by_payment_method"]}
        assert methods.get("Cash", 0) == a
        assert methods.get("Visa", 0) == b
        assert SPLIT_PAYMENT_METHOD not in methods
        sess_row = next(s for s in daily["sessions"] if s["session_id"] == session_id)
        assert "Cash" in (sess_row["payment_method"] or "")
        assert "Visa" in (sess_row["payment_method"] or "")
        assert len(sess_row["payments"]) == 2

        # Bad sum rejected
        client.post(
            "/api/t/TABLE5/welcome",
            json={"guest_name": "BadSplit", "party_size": 1},
        )
        client.post(
            "/api/t/TABLE5/orders",
            json={"items": [{"item_id": "coke", "qty": 1}]},
        )
        bad = client.post(
            "/api/staff/bill/TABLE5/close",
            data={
                "pin": pin,
                "discount_percent": 0,
                "payments_json": '[{"method":"Cash","amount":1},{"method":"Visa","amount":1}]',
            },
        )
        assert bad.status_code == 400

        # Single-method path still works (legacy)
        client.post(
            "/api/t/TABLE2/welcome",
            json={"guest_name": "Single", "party_size": 1},
        )
        client.post(
            "/api/t/TABLE2/orders",
            json={"items": [{"item_id": "coke", "qty": 1}]},
        )
        single = client.post(
            "/api/staff/bill/TABLE2/close",
            data={"pin": pin, "discount_percent": 0, "payment_method": "AlipayHK"},
        )
        assert single.status_code == 200, single.text
        sid2 = single.json()["session_id"]
        row2 = db.get_session(conn, sid2)
        assert row2["payment_method"] == "AlipayHK"
        pays2 = db.list_session_payments(conn, sid2)
        assert len(pays2) == 1 and pays2[0]["method"] == "AlipayHK"
        conn.close()


def test_format_payment_label():
    from app.db import format_payment_label

    assert format_payment_label("Cash") == "Cash"
    assert (
        format_payment_label(
            "Split",
            [{"method": "Cash", "amount": 100}, {"method": "Visa", "amount": 50}],
        )
        == "Cash $100 · Visa $50"
    )
