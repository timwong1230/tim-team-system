"""Staff can place full menu orders for guest tables."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_POLAR = _ROOT / "polar-order"
if str(_POLAR) not in sys.path:
    sys.path.insert(0, str(_POLAR))


def test_staff_place_order_api_and_page():
    tmp = tempfile.mkdtemp(prefix="polar-staff-order-")
    os.environ["POLAR_DATA_DIR"] = tmp
    os.environ["POLAR_STAFF_PIN"] = "polar2026"

    # Re-import paths/db against temp dir
    import importlib

    import app.paths as paths
    import app.db as db
    import app.main as main

    importlib.reload(paths)
    importlib.reload(db)
    importlib.reload(main)

    from fastapi.testclient import TestClient

    pin = "polar2026"
    # Context manager runs FastAPI lifespan → init_db()
    with TestClient(main.app) as client:
        page = client.get(f"/staff/order/TABLE1?pin={pin}")
        assert page.status_code == 200
        assert b"STAFF ORDER" in page.content
        assert b"Send order for table" in page.content
        assert b"staff-order-shell" in page.content
        assert b'id="staffCatRail"' in page.content
        assert b'id="staffOrderMain"' in page.content
        # First category visible; others start hidden
        assert b'id="cat-shisha"' in page.content
        js = (_POLAR / "static/js/staff_order.js").read_text(encoding="utf-8")
        assert "/staff/tables?pin=" in js
        assert "back to tables" in js
        assert "openStaffCategory" in js
        css = (_POLAR / "static/css/app.css").read_text(encoding="utf-8")
        assert ".guest-cat-rail" in css

        bad = client.post(
            "/api/staff/bill/TABLE1/orders",
            json={"pin": "wrong", "items": [{"item_id": "shisha-regular", "qty": 1}]},
        )
        assert bad.status_code == 401

        conn = db.connect()
        item = conn.execute(
            "SELECT id FROM menu_items WHERE available = 1 ORDER BY id LIMIT 1"
        ).fetchone()
        conn.close()
        assert item is not None
        item_id = item["id"]

        res = client.post(
            "/api/staff/bill/TABLE1/orders",
            json={
                "pin": pin,
                "guest_name": "Amy",
                "party_size": 3,
                "note": "Staff ordered",
                "items": [{"item_id": item_id, "qty": 2}],
            },
        )
        assert res.status_code == 200, res.text
        data = res.json()
        assert data["ok"] is True
        assert data["created_by"] == "Staff"
        assert data["guest_name"] == "Amy"
        assert data["party_size"] == 3

        res2 = client.post(
            "/api/staff/bill/TABLE1/orders",
            json={"pin": pin, "items": [{"item_id": item_id, "qty": 1}]},
        )
        assert res2.status_code == 200, res2.text

        bill = client.get(f"/staff/bill/TABLE1?pin={pin}")
        assert bill.status_code == 200
        assert b"Order for this table" in bill.content

        tables = client.get(f"/staff/tables?pin={pin}")
        assert tables.status_code == 200
        assert b"Order for table" in tables.content
