"""Staff-only Free Flow category — hidden from guest QR menu."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_POLAR = _ROOT / "polar-order"
if str(_POLAR) not in sys.path:
    sys.path.insert(0, str(_POLAR))


def test_free_flow_staff_only_not_on_guest_menu():
    tmp = tempfile.mkdtemp(prefix="polar-free-flow-")
    os.environ["POLAR_DATA_DIR"] = tmp
    os.environ["POLAR_STAFF_PIN"] = "polar2026"

    import importlib

    import app.paths as paths
    import app.db as db
    import app.main as main
    import app.guest_nav as guest_nav

    importlib.reload(paths)
    importlib.reload(db)
    importlib.reload(guest_nav)
    importlib.reload(main)

    from fastapi.testclient import TestClient

    menu_json = json.loads((_POLAR / "data" / "menu.json").read_text(encoding="utf-8"))
    ff = next(c for c in menu_json["categories"] if c["id"] == "free-flow")
    assert ff.get("staff_only") is True
    assert ff["name"] == "Free Flow"
    by_id = {i["id"]: i for i in ff["items"]}
    assert by_id["free-flow-with-shisha"]["price"] == 450
    assert by_id["free-flow-with-shisha"]["name"] == "With Shisha"
    assert by_id["free-flow-without-shisha"]["price"] == 300
    assert by_id["free-flow-without-shisha"]["name"] == "Without Shisha"

    pin = "polar2026"
    with TestClient(main.app) as client:
        staff = client.get(f"/staff/order/TABLE1?pin={pin}")
        assert staff.status_code == 200
        assert b"Free Flow" in staff.content
        assert b"With Shisha" in staff.content
        assert b"Without Shisha" in staff.content
        assert b"$450" in staff.content or b">450<" in staff.content
        assert b"$300" in staff.content or b">300<" in staff.content
        assert b'id="cat-free-flow"' in staff.content

        # Guest check-in then menu — Free Flow must not appear
        welcome = client.post(
            "/api/t/TABLE1/welcome",
            json={"guest_name": "FF Guest", "party_size": 2},
        )
        assert welcome.status_code == 200, welcome.text
        guest = client.get("/t/TABLE1")
        assert guest.status_code == 200
        assert b"Free Flow" not in guest.content
        assert b"free-flow-with-shisha" not in guest.content
        assert b"Without Shisha" not in guest.content
        assert b'id="cat-free-flow"' not in guest.content

        # Staff can actually order Free Flow onto the bill
        ordered = client.post(
            "/api/staff/bill/TABLE2/orders",
            json={
                "pin": pin,
                "guest_name": "FF Party",
                "party_size": 4,
                "items": [
                    {"item_id": "free-flow-with-shisha", "qty": 1},
                    {"item_id": "free-flow-without-shisha", "qty": 1},
                ],
            },
        )
        assert ordered.status_code == 200, ordered.text
        bill = client.get(f"/staff/bill/TABLE2?pin={pin}")
        assert bill.status_code == 200
        assert b"With Shisha" in bill.content
        assert b"Without Shisha" in bill.content

    # Guest nav tree must not reference free-flow
    tree_src = (_POLAR / "app" / "guest_nav.py").read_text(encoding="utf-8")
    assert "free-flow" not in tree_src
