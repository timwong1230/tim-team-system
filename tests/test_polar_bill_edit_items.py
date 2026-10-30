"""Staff can change qty or remove items already on an open bill."""

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


def test_bill_edit_item_qty_and_remove():
    tmp = tempfile.mkdtemp(prefix="polar-bill-edit-")
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
    with TestClient(main.app) as client:
        page = client.get(f"/staff/bill/TABLE5?pin={pin}")
        # No session yet — still loads; place order first
        client.post(
            "/api/t/TABLE5/welcome",
            json={"guest_name": "Edit", "party_size": 2},
        )
        placed = client.post(
            "/api/t/TABLE5/orders",
            json={"items": [{"item_id": "coke", "qty": 2}]},
        )
        assert placed.status_code == 200, placed.text

        bill_page = client.get(f"/staff/bill/TABLE5?pin={pin}")
        assert bill_page.status_code == 200
        assert b'data-bill-act="inc"' in bill_page.content
        assert b'data-bill-act="dec"' in bill_page.content
        assert b'data-bill-act="rm"' in bill_page.content
        assert b"Change qty or remove" in bill_page.content

        conn = db.connect()
        row = conn.execute(
            """
            SELECT oi.id, oi.qty, oi.unit_price, oi.line_total
            FROM order_items oi
            JOIN orders o ON o.id = oi.order_id
            JOIN sessions s ON s.id = o.session_id
            JOIN tables t ON t.id = s.table_id
            WHERE t.code = 'TABLE5' AND o.status != 'cancelled'
            """
        ).fetchone()
        conn.close()
        assert row is not None
        item_id = row["id"]
        unit = float(row["unit_price"])
        assert int(row["qty"]) == 2

        # Increase qty 2 → 3
        up = client.post(
            f"/api/staff/bill/TABLE5/items/{item_id}",
            json={"pin": pin, "qty": 3},
        )
        assert up.status_code == 200, up.text
        up_data = up.json()
        assert up_data["ok"] is True
        assert up_data["action"] == "updated"
        assert up_data["qty"] == 3
        assert len(up_data["lines"]) == 1
        assert up_data["lines"][0]["qty"] == 3
        assert float(up_data["lines"][0]["line_total"]) == round(unit * 3, 1)
        assert float(up_data["bill"]["subtotal"]) == round(unit * 3, 1)

        # Decrease qty 3 → 1
        down = client.post(
            f"/api/staff/bill/TABLE5/items/{item_id}",
            json={"pin": pin, "qty": 1},
        )
        assert down.status_code == 200, down.text
        assert down.json()["qty"] == 1
        assert float(down.json()["bill"]["subtotal"]) == round(unit * 1, 1)

        # Remove line (qty=0) — cancels empty order
        rm = client.post(
            f"/api/staff/bill/TABLE5/items/{item_id}",
            json={"pin": pin, "qty": 0},
        )
        assert rm.status_code == 200, rm.text
        rm_data = rm.json()
        assert rm_data["action"] == "removed"
        assert rm_data["qty"] == 0
        assert rm_data["lines"] == []
        assert float(rm_data["bill"]["subtotal"]) == 0.0

        conn = db.connect()
        left = conn.execute(
            """
            SELECT oi.id FROM order_items oi
            JOIN orders o ON o.id = oi.order_id
            JOIN sessions s ON s.id = o.session_id
            JOIN tables t ON t.id = s.table_id
            WHERE t.code = 'TABLE5' AND o.status != 'cancelled'
            """
        ).fetchall()
        cancelled = conn.execute(
            """
            SELECT o.status FROM orders o
            JOIN sessions s ON s.id = o.session_id
            JOIN tables t ON t.id = s.table_id
            WHERE t.code = 'TABLE5'
            ORDER BY o.id DESC LIMIT 1
            """
        ).fetchone()
        conn.close()
        assert left == []
        assert cancelled["status"] == "cancelled"

        # Auth / missing item
        bad = client.post(
            f"/api/staff/bill/TABLE5/items/99999",
            json={"pin": "wrong", "qty": 1},
        )
        assert bad.status_code == 401

        miss = client.post(
            f"/api/staff/bill/TABLE5/items/99999",
            json={"pin": pin, "qty": 1},
        )
        assert miss.status_code == 404
