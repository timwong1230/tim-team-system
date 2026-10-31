"""Table 1–5 can be split into A/B/C/D parties with own name + headcount."""

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


def test_table_splits_separate_sessions():
    tmp = tempfile.mkdtemp(prefix="polar-table-split-")
    os.environ["POLAR_DATA_DIR"] = tmp
    os.environ["POLAR_STAFF_PIN"] = "polar2026"

    import importlib

    import app.paths as paths
    import app.db as db
    import app.main as main
    import app.pricing as pricing
    import app.seats as seats

    importlib.reload(paths)
    importlib.reload(seats)
    importlib.reload(db)
    importlib.reload(pricing)
    importlib.reload(main)

    from fastapi.testclient import TestClient

    pin = "polar2026"
    with TestClient(main.app) as client:
        # QR sheet still only prints physical Table 1–5 (no 1A)
        qrs = client.get(f"/staff/qrs?pin={pin}")
        assert qrs.status_code == 200
        assert b">Table 1<" in qrs.content
        assert b">Table 1A<" not in qrs.content

        tables = client.get(f"/staff/tables?pin={pin}")
        assert tables.status_code == 200
        # Idle A–D cards stay off Open seats (open splits from Table 1–5 instead)
        assert b"Table 1A" not in tables.content
        assert b"Table 1B" not in tables.content
        assert b"Split party" in tables.content
        assert b"Active splits appear here only when in use" in tables.content

        # Main table party
        main_order = client.post(
            "/api/staff/bill/TABLE1/orders",
            json={
                "pin": pin,
                "guest_name": "Amy",
                "party_size": 4,
                "items": [{"item_id": "coke", "qty": 1}],
            },
        )
        assert main_order.status_code == 200, main_order.text
        assert main_order.json()["guest_name"] == "Amy"
        assert main_order.json()["party_size"] == 4

        # Next free split → 1A
        split = client.post(
            "/api/staff/tables/TABLE1/split",
            json={"pin": pin},
        )
        assert split.status_code == 200, split.text
        data = split.json()
        assert data["code"] == "TABLE1A"
        assert data["label"] == "Table 1A"
        assert "/staff/order/TABLE1A" in data["redirect"]

        # Separate party on 1A
        a_order = client.post(
            "/api/staff/bill/TABLE1A/orders",
            json={
                "pin": pin,
                "guest_name": "Ben",
                "party_size": 2,
                "items": [{"item_id": "coke", "qty": 2}],
            },
        )
        assert a_order.status_code == 200, a_order.text
        assert a_order.json()["guest_name"] == "Ben"
        assert a_order.json()["party_size"] == 2

        # Busy split shows on Open seats; idle 1B/1C/1D still hidden
        tables_busy = client.get(f"/staff/tables?pin={pin}")
        assert tables_busy.status_code == 200
        assert b"Table 1A" in tables_busy.content
        assert b"Ben" in tables_busy.content
        assert b"Table 1B" not in tables_busy.content
        assert b"Table 1C" not in tables_busy.content

        # Next free → 1B
        split2 = client.post(
            "/api/staff/tables/TABLE1/split",
            json={"pin": pin},
        )
        assert split2.status_code == 200
        assert split2.json()["code"] == "TABLE1B"

        # Sessions stay independent
        conn = db.connect()
        s1 = db.get_open_session(conn, db.get_table_by_code(conn, "TABLE1")["id"])
        sa = db.get_open_session(conn, db.get_table_by_code(conn, "TABLE1A")["id"])
        conn.close()
        assert s1["guest_name"] == "Amy" and s1["party_size"] == 4
        assert sa["guest_name"] == "Ben" and sa["party_size"] == 2

        bill_a = client.get(f"/staff/bill/TABLE1A?pin={pin}")
        assert bill_a.status_code == 200
        assert b"Ben" in bill_a.content
        assert b"Parties at Table 1" in bill_a.content
