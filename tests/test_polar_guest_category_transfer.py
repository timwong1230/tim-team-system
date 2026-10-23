"""Guest category-first menu + staff table session transfer."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path


_ROOT = Path(__file__).resolve().parents[1]
_POLAR = _ROOT / "polar-order"
if str(_POLAR) not in sys.path:
    sys.path.insert(0, str(_POLAR))


def test_guest_category_hub_and_staff_transfer():
    tmp = tempfile.mkdtemp(prefix="polar-cat-transfer-")
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

    pin = "polar2026"
    with TestClient(main.app) as client:
        welcome = client.post(
            "/api/t/TABLE1/welcome",
            json={"guest_name": "Chris", "party_size": 2},
        )
        assert welcome.status_code == 200

        page = client.get("/t/TABLE1")
        assert page.status_code == 200
        html = page.text
        assert 'id="catHub"' in html
        assert "Choose a category" in html
        assert 'class="section section-products"' in html
        assert "← Categories" in html
        assert html.count("section-products") >= 1
        # Product sections start hidden until a category is tapped
        assert 'section-products" id="' in html or 'section-products"' in html
        assert "hidden" in html

        conn = db.connect()
        item = conn.execute(
            "SELECT id FROM menu_items WHERE available = 1 ORDER BY id LIMIT 1"
        ).fetchone()
        conn.close()
        assert item is not None

        placed = client.post(
            "/api/t/TABLE1/orders",
            json={"items": [{"item_id": item["id"], "qty": 2}]},
        )
        assert placed.status_code == 200, placed.text

        bill1 = client.get(f"/staff/bill/TABLE1?pin={pin}")
        assert bill1.status_code == 200
        assert b"Move to another table" in bill1.content
        assert b"TABLE3" in bill1.content or b"Table 3" in bill1.content

        # Occupied target rejected
        client.post(
            "/api/t/TABLE2/welcome",
            json={"guest_name": "Other", "party_size": 1},
        )
        busy = client.post(
            "/api/staff/bill/TABLE1/transfer",
            json={"pin": pin, "target_table": "TABLE2"},
        )
        assert busy.status_code == 400

        ok = client.post(
            "/api/staff/bill/TABLE1/transfer",
            json={"pin": pin, "target_table": "TABLE3"},
        )
        assert ok.status_code == 200, ok.text
        data = ok.json()
        assert data["ok"] is True
        assert data["from_table"] == "TABLE1"
        assert data["to_table"] == "TABLE3"
        assert "/staff/bill/TABLE3" in data["redirect"]

        conn = db.connect()
        s1 = db.get_open_session(conn, db.get_table_by_code(conn, "TABLE1")["id"])
        s3 = db.get_open_session(conn, db.get_table_by_code(conn, "TABLE3")["id"])
        assert s1 is None
        assert s3 is not None
        assert s3["guest_name"] == "Chris"
        orders = conn.execute(
            "SELECT table_id FROM orders WHERE session_id = ?",
            (s3["id"],),
        ).fetchall()
        t3_id = db.get_table_by_code(conn, "TABLE3")["id"]
        assert orders
        assert all(o["table_id"] == t3_id for o in orders)
        conn.close()

        bill3 = client.get(f"/staff/bill/TABLE3?pin={pin}")
        assert bill3.status_code == 200
        assert b"Chris" in bill3.content

        empty1 = client.get(f"/staff/bill/TABLE1?pin={pin}")
        assert empty1.status_code == 200
        assert b"No open session" in empty1.content
