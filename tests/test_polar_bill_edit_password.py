"""Reopen a Mark-paid bill for edits — gated by POLAR_BILL_EDIT_PASSWORD."""

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


def test_reopen_paid_bill_requires_edit_password():
    tmp = tempfile.mkdtemp(prefix="polar-bill-reopen-")
    os.environ["POLAR_DATA_DIR"] = tmp
    os.environ["POLAR_STAFF_PIN"] = "polar2026"
    os.environ["POLAR_BILL_EDIT_PASSWORD"] = "polar2019"

    import importlib

    import app.paths as paths
    import app.db as db
    import app.main as main
    import app.ops_constants as ops
    import app.pricing as pricing
    import app.reports as reports

    importlib.reload(paths)
    importlib.reload(db)
    importlib.reload(ops)
    importlib.reload(pricing)
    importlib.reload(reports)
    importlib.reload(main)

    from fastapi.testclient import TestClient

    pin = "polar2026"
    with TestClient(main.app) as client:
        assert (
            client.post(
                "/api/t/TABLE3/welcome", json={"guest_name": "Typo", "party_size": 2}
            ).status_code
            == 200
        )
        placed = client.post(
            "/api/t/TABLE3/orders",
            json={"items": [{"item_id": "coke", "qty": 2}]},
        )
        assert placed.status_code == 200, placed.text

        closed = client.post(
            "/api/staff/bill/TABLE3/close",
            data={
                "pin": pin,
                "discount_percent": 0,
                "payment_method": "Cash",
            },
        )
        assert closed.status_code == 200, closed.text
        session_id = closed.json()["session_id"]
        first_total = float(closed.json()["total"])

        reports_page = client.get(f"/staff/reports?pin={pin}")
        assert reports_page.status_code == 200
        assert b"bill-edit-reopen-btn" in reports_page.content
        assert b"Edit" in reports_page.content

        bad = client.post(
            f"/api/staff/sessions/{session_id}/reopen-edit",
            json={"pin": pin, "edit_password": "wrong"},
        )
        assert bad.status_code == 403, bad.text

        ok = client.post(
            f"/api/staff/sessions/{session_id}/reopen-edit",
            json={"pin": pin, "edit_password": "polar2019"},
        )
        assert ok.status_code == 200, ok.text
        body = ok.json()
        assert body["ok"] is True
        assert body["table_code"] == "TABLE3"
        assert "edited=1" in body["redirect"]

        conn = db.connect()
        sess = db.get_session(conn, session_id)
        assert sess["status"] == "open"
        assert sess["business_date"]  # kept for same-night re-close
        original_biz = sess["business_date"]
        conn.close()

        bill_page = client.get(body["redirect"])
        assert bill_page.status_code == 200
        assert b"Editing paid bill" in bill_page.content
        assert b'data-bill-act="inc"' in bill_page.content

        # Fix the typo: bump coke 2 → 3, then mark paid again.
        conn = db.connect()
        row = conn.execute(
            """
            SELECT oi.id FROM order_items oi
            JOIN orders o ON o.id = oi.order_id
            WHERE o.session_id = ? AND o.status != 'cancelled'
            """,
            (session_id,),
        ).fetchone()
        conn.close()
        assert row is not None
        up = client.post(
            f"/api/staff/bill/TABLE3/items/{row['id']}",
            json={"pin": pin, "qty": 3},
        )
        assert up.status_code == 200, up.text

        closed2 = client.post(
            "/api/staff/bill/TABLE3/close",
            data={
                "pin": pin,
                "discount_percent": 0,
                "payment_method": "Visa",
            },
        )
        assert closed2.status_code == 200, closed2.text
        assert float(closed2.json()["total"]) > first_total

        conn = db.connect()
        sess2 = db.get_session(conn, session_id)
        assert sess2["status"] == "closed"
        assert sess2["business_date"] == original_biz
        assert sess2["payment_method"] == "Visa"
        conn.close()
