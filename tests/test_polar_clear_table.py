"""Staff can clear (void) a wrongly opened table — not a sale."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_POLAR = _ROOT / "polar-order"
if str(_POLAR) not in sys.path:
    sys.path.insert(0, str(_POLAR))


def test_staff_clear_table_voids_session_not_sales():
    tmp = tempfile.mkdtemp(prefix="polar-clear-table-")
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

    pin = "polar2026"
    bill_html = (_POLAR / "templates/staff_bill.html").read_text(encoding="utf-8")
    assert 'id="clearTableBtn"' in bill_html
    assert "Clear table" in bill_html
    assert "/api/staff/bill/" in bill_html and "/clear" in bill_html

    with TestClient(main.app) as client:
        # Accidental open + order on wrong table
        placed = client.post(
            "/api/staff/bill/TABLE4/orders",
            json={
                "pin": pin,
                "guest_name": "WrongSeat",
                "party_size": 2,
                "items": [{"item_id": "coke", "qty": 1}],
            },
        )
        assert placed.status_code == 200, placed.text

        page = client.get(f"/staff/bill/TABLE4?pin={pin}")
        assert page.status_code == 200
        assert b"Clear table" in page.content
        assert b"clearTableBtn" in page.content
        assert b"WrongSeat" in page.content

        empty = client.post(
            "/api/staff/bill/TABLE5/clear",
            json={"pin": pin},
        )
        assert empty.status_code == 400

        bad = client.post(
            "/api/staff/bill/TABLE4/clear",
            json={"pin": "wrong"},
        )
        assert bad.status_code == 401

        cleared = client.post(
            "/api/staff/bill/TABLE4/clear",
            json={"pin": pin},
        )
        assert cleared.status_code == 200, cleared.text
        data = cleared.json()
        assert data["ok"] is True
        assert data["cleared"] is True
        assert data["table_code"] == "TABLE4"
        sid = data["session_id"]

        conn = db.connect()
        session = db.get_session(conn, sid)
        assert session["status"] == "voided"
        assert float(session["total"] or 0) == 0
        assert session["payment_method"] is None
        assert db.get_open_session(conn, db.get_table_by_code(conn, "TABLE4")["id"]) is None

        open_orders = conn.execute(
            """
            SELECT COUNT(*) AS c FROM orders
            WHERE session_id = ? AND status != 'cancelled'
            """,
            (sid,),
        ).fetchone()["c"]
        assert open_orders == 0
        cancelled = conn.execute(
            """
            SELECT COUNT(*) AS c FROM orders
            WHERE session_id = ? AND status = 'cancelled'
            """,
            (sid,),
        ).fetchone()["c"]
        assert cancelled >= 1

        day = business_date(datetime.now(ZoneInfo("Asia/Hong_Kong")))
        daily = reports.daily_sales_report(conn, day)
        conn.close()
        assert daily["gross_sales"] == 0
        assert daily["session_count"] == 0

        # Bill page now empty; clear card gone with no session
        after = client.get(f"/staff/bill/TABLE4?pin={pin}")
        assert after.status_code == 200
        assert b"No open session" in after.content
        assert b'id="clearTableBox"' not in after.content
        assert b"WrongSeat" not in after.content

        tables = client.get(f"/staff/tables?pin={pin}")
        assert tables.status_code == 200
        # TABLE4 tile should show empty again
        assert b"WrongSeat" not in tables.content
