"""Staff Open seats: Boss tabs can open staff order and place items."""

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


def test_staff_can_order_from_boss_tabs():
    tmp = tempfile.mkdtemp(prefix="polar-boss-staff-order-")
    os.environ["POLAR_DATA_DIR"] = tmp
    os.environ["POLAR_STAFF_PIN"] = "polar2026"

    import importlib

    import app.paths as paths
    import app.db as db
    import app.main as main
    import app.pricing as pricing

    importlib.reload(paths)
    importlib.reload(db)
    importlib.reload(pricing)
    importlib.reload(main)

    from fastapi.testclient import TestClient

    pin = "polar2026"
    tables_html = (_POLAR / "templates/staff_tables.html").read_text(encoding="utf-8")
    assert "Order for boss" in tables_html
    assert 'href="/staff/order/{{ row.table.code }}?pin={{ pin }}"' in tables_html

    bill_html = (_POLAR / "templates/staff_bill.html").read_text(encoding="utf-8")
    assert "＋ Order for boss" in bill_html

    with TestClient(main.app) as client:
        seats = client.get(f"/staff/tables?pin={pin}")
        assert seats.status_code == 200
        assert b"Boss tabs" in seats.content
        assert b"Order for boss" in seats.content
        assert b"/staff/order/BOSSJON?pin=" in seats.content

        # Staff order page stays in staff UI (no redirect away to /boss/jon)
        page = client.get(f"/staff/order/BOSSJON?pin={pin}", follow_redirects=False)
        assert page.status_code == 200
        assert b"STAFF ORDER" in page.content
        assert b"Personal tab" in page.content
        assert b"staffCheckin" not in page.content
        assert b"Send order for table" in page.content

        bill = client.get(f"/staff/bill/BOSSJON?pin={pin}")
        assert bill.status_code == 200
        assert b"Order for boss" in bill.content

        conn = db.connect()
        item = conn.execute(
            "SELECT id FROM menu_items WHERE available = 1 ORDER BY id LIMIT 1"
        ).fetchone()
        conn.close()
        assert item is not None

        res = client.post(
            "/api/staff/bill/BOSSJON/orders",
            json={"pin": pin, "items": [{"item_id": item["id"], "qty": 1}]},
        )
        assert res.status_code == 200, res.text
        data = res.json()
        assert data["ok"] is True
        assert data["guest_name"] == "Jon"
        assert data["party_size"] == 1

        bill2 = client.get(f"/staff/bill/BOSSJON?pin={pin}")
        assert bill2.status_code == 200
        assert b"Jon" in bill2.content
