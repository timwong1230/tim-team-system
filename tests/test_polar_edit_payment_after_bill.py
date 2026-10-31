"""Staff can correct payment method after Mark paid (closed session)."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_POLAR = _ROOT / "polar-order"
if str(_POLAR) not in sys.path:
    sys.path.insert(0, str(_POLAR))


def test_change_payment_method_after_close():
    tmp = tempfile.mkdtemp(prefix="polar-edit-pay-")
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

    from app.pricing import business_date

    pin = "polar2026"
    with TestClient(main.app) as client:
        client.post(
            "/api/t/TABLE4/welcome",
            json={"guest_name": "PayFix", "party_size": 2},
        )
        client.post(
            "/api/t/TABLE4/orders",
            json={"items": [{"item_id": "coke", "qty": 1}]},
        )
        closed = client.post(
            "/api/staff/bill/TABLE4/close",
            data={
                "pin": pin,
                "discount_percent": 0,
                "payment_method": "Cash",
            },
        )
        assert closed.status_code == 200, closed.text
        session_id = closed.json()["session_id"]

        conn = db.connect()
        row = db.get_session(conn, session_id)
        assert row["status"] == "closed"
        assert row["payment_method"] == "Cash"
        old_receipt = row["receipt_path"]
        conn.close()

        # Reports page exposes payment editor
        day = business_date().isoformat()
        reports_page = client.get(f"/staff/reports?pin={pin}&day={day}")
        assert reports_page.status_code == 200
        assert b"pay-method-edit" in reports_page.content
        assert b"Wrong tender after Mark paid" in reports_page.content

        # Change Cash → Visa
        updated = client.post(
            f"/api/staff/sessions/{session_id}/payment",
            json={"pin": pin, "payment_method": "Visa"},
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["payment_method"] == "Visa"

        conn = db.connect()
        row = db.get_session(conn, session_id)
        assert row["payment_method"] == "Visa"
        assert row["receipt_path"]
        assert old_receipt  # original close wrote a receipt
        daily = reports.daily_sales_report(conn, business_date())
        methods = {p["method"]: p["total"] for p in daily["by_payment_method"]}
        assert methods.get("Visa", 0) > 0
        assert methods.get("Cash", 0) == 0

        client.post(
            "/api/t/TABLE2/welcome",
            json={"guest_name": "Open", "party_size": 1},
        )
        table2 = db.get_table_by_code(conn, "TABLE2")
        assert table2 is not None
        open_sess = db.get_open_session(conn, table2["id"])
        conn.close()
        assert open_sess

        # Bad method rejected
        bad = client.post(
            f"/api/staff/sessions/{session_id}/payment",
            json={"pin": pin, "payment_method": "Bitcoin"},
        )
        assert bad.status_code == 400

        # Open session cannot be edited this way
        open_edit = client.post(
            f"/api/staff/sessions/{open_sess['id']}/payment",
            json={"pin": pin, "payment_method": "Cash"},
        )
        assert open_edit.status_code == 404
