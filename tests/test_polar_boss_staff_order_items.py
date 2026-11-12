"""Boss staff orders must keep all items visible after Credit / reorder."""

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


def test_boss_multi_item_order_survives_credit_and_order_page():
    tmp = tempfile.mkdtemp(prefix="polar-boss-items-")
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
    js = (_POLAR / "static/js/staff_order.js").read_text(encoding="utf-8")
    assert "allowNote" in js
    assert "Missing item id" in js
    assert "n${Date.now()" in js or "Date.now().toString(36)" in js

    with TestClient(main.app) as client:
        conn = db.connect()
        items = conn.execute(
            "SELECT id, name FROM menu_items WHERE available = 1 ORDER BY id LIMIT 3"
        ).fetchall()
        conn.close()
        assert len(items) == 3
        names = [i["name"] for i in items]

        placed = client.post(
            "/api/staff/bill/BOSSJON/orders",
            json={
                "pin": pin,
                "items": [
                    {"item_id": items[0]["id"], "qty": 1},
                    {"item_id": items[1]["id"], "qty": 1, "note": "Grape"},
                    {"item_id": items[2]["id"], "qty": 2},
                ],
            },
        )
        assert placed.status_code == 200, placed.text

        bill = client.get(f"/staff/bill/BOSSJON?pin={pin}")
        assert bill.status_code == 200
        for name in names:
            assert name.encode() in bill.content
        assert b"Grape" in bill.content

        closed = client.post(
            "/api/staff/bill/BOSSJON/close",
            data={"pin": pin, "discount_percent": 0},
        )
        assert closed.status_code == 200, closed.text
        credit_total = float(closed.json()["total"])
        assert credit_total > 0

        # Opening the order page must NOT create a blank open tab that hides Credit items.
        order_page = client.get(f"/staff/order/BOSSJON?pin={pin}")
        assert order_page.status_code == 200
        assert b"Personal tab" in order_page.content

        conn = db.connect()
        open_n = conn.execute(
            """
            SELECT COUNT(*) AS n FROM sessions s
            JOIN tables t ON t.id = s.table_id
            WHERE t.code = 'BOSSJON' AND s.status = 'open'
            """
        ).fetchone()["n"]
        conn.close()
        assert open_n == 0

        bill_after = client.get(f"/staff/bill/BOSSJON?pin={pin}")
        assert bill_after.status_code == 200
        assert b"Last Credit (recorded)" in bill_after.content
        for name in names:
            assert name.encode() in bill_after.content
        assert b"Grape" in bill_after.content

        # New order starts a fresh open tab; prior Credit remains listed above.
        again = client.post(
            "/api/staff/bill/BOSSJON/orders",
            json={"pin": pin, "items": [{"item_id": items[0]["id"], "qty": 1}]},
        )
        assert again.status_code == 200, again.text
        bill2 = client.get(f"/staff/bill/BOSSJON?pin={pin}")
        assert bill2.status_code == 200
        assert b"Last Credit (recorded)" in bill2.content
        # Open tab shows the new line; last credit still lists the old names.
        for name in names:
            assert name.encode() in bill2.content
