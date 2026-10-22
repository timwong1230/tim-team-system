"""Guest View Order lists sent items with qty only — no prices."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_POLAR = _ROOT / "polar-order"
if str(_POLAR) not in sys.path:
    sys.path.insert(0, str(_POLAR))


def test_guest_my_orders_hides_prices():
    tmp = tempfile.mkdtemp(prefix="polar-view-order-")
    os.environ["POLAR_DATA_DIR"] = tmp
    os.environ["POLAR_STAFF_PIN"] = "polar2026"

    import importlib

    import app.paths as paths
    import app.db as db
    import app.main as main

    importlib.reload(paths)
    importlib.reload(db)
    importlib.reload(main)

    from fastapi.testclient import TestClient

    with TestClient(main.app) as client:
        empty = client.get("/api/t/TABLE1/my-orders")
        assert empty.status_code == 200
        assert empty.json()["items"] == []

        welcome = client.post(
            "/api/t/TABLE1/welcome",
            json={"guest_name": "Sam", "party_size": 2},
        )
        assert welcome.status_code == 200

        conn = db.connect()
        item = conn.execute(
            "SELECT id, name FROM menu_items WHERE available = 1 ORDER BY id LIMIT 1"
        ).fetchone()
        conn.close()
        assert item is not None

        placed = client.post(
            "/api/t/TABLE1/orders",
            json={"items": [{"item_id": item["id"], "qty": 2}]},
        )
        assert placed.status_code == 200, placed.text

        mine = client.get("/api/t/TABLE1/my-orders")
        assert mine.status_code == 200
        body = mine.json()
        assert body["ok"] is True
        assert len(body["items"]) == 1
        assert body["items"][0]["name"] == item["name"]
        assert body["items"][0]["qty"] == 2

        blob = mine.text.lower()
        for forbidden in ("unit_price", "line_total", "price", "total", "$"):
            assert forbidden not in blob, f"price leak: {forbidden} in {mine.text}"

        page = client.get("/t/TABLE1")
        assert page.status_code == 200
        assert b"View Order" in page.content
        assert b"viewOrderDrawer" in page.content
