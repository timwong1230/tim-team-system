"""Staff can waive snacks and undo served orders."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_POLAR = _ROOT / "polar-order"
# Prefer polar-order package over repo-root app.py
sys.path = [str(_POLAR)] + [p for p in sys.path if Path(p).resolve() != _ROOT]
for _name in list(sys.modules):
    if _name == "app" or _name.startswith("app."):
        del sys.modules[_name]


def test_snack_waive_and_undo_served():
    tmp = tempfile.mkdtemp(prefix="polar-snack-served-")
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
        client.post(
            "/api/t/TABLE5/welcome",
            json={"guest_name": "Pat", "party_size": 2},
        )
        client.post(
            "/api/t/TABLE5/orders",
            json={"items": [{"item_id": "coke", "qty": 1}]},
        )

        bill = client.get(f"/staff/bill/TABLE5?pin={pin}")
        assert bill.status_code == 200
        assert b"Cancel snacks" in bill.content
        assert b'id="snackWaive"' in bill.content

        # Default: snacks charged (2 × $10)
        party = client.post(
            "/api/staff/bill/TABLE5/party",
            json={"pin": pin, "party_size": 2},
        )
        assert party.status_code == 200
        assert party.json()["bill"]["snack_charge"] == 20.0
        assert party.json()["snack_waived"] is False

        waived = client.post(
            "/api/staff/bill/TABLE5/snack",
            json={"pin": pin, "waived": True},
        )
        assert waived.status_code == 200, waived.text
        assert waived.json()["snack_waived"] is True
        assert waived.json()["bill"]["snack_charge"] == 0.0

        restored = client.post(
            "/api/staff/bill/TABLE5/snack",
            json={"pin": pin, "waived": False},
        )
        assert restored.status_code == 200
        assert restored.json()["bill"]["snack_charge"] == 20.0

        # Mark order served — still listed while session open
        orders = client.get(f"/api/staff/orders?pin={pin}").json()
        assert len(orders) == 1
        oid = orders[0]["id"]
        served = client.post(
            f"/api/staff/orders/{oid}/status",
            data={"pin": pin, "status": "served"},
        )
        assert served.status_code == 200

        still = client.get(f"/api/staff/orders?pin={pin}").json()
        assert len(still) == 1
        assert still[0]["status"] == "served"

        undo = client.post(
            f"/api/staff/orders/{oid}/status",
            data={"pin": pin, "status": "ready"},
        )
        assert undo.status_code == 200
        back = client.get(f"/api/staff/orders?pin={pin}").json()
        assert back[0]["status"] == "ready"

        cancel = client.post(
            f"/api/staff/orders/{oid}/status",
            data={"pin": pin, "status": "cancelled"},
        )
        assert cancel.status_code == 200
        gone = client.get(f"/api/staff/orders?pin={pin}").json()
        assert gone == []

        # Board JS exposes Undo served
        board = client.get(f"/staff/board?pin={pin}")
        assert board.status_code == 200
        js = Path(_POLAR / "static/js/staff.js").read_text(encoding="utf-8")
        assert "Undo served" in js
        assert 'data-status="ready"' in js
