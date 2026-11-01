"""Staff must enter party size before opening a guest table."""

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


def test_staff_order_requires_party_size_to_open_table():
    tmp = tempfile.mkdtemp(prefix="polar-party-req-")
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
        order_page = client.get(f"/staff/order/TABLE4?pin={pin}")
        assert order_page.status_code == 200
        html = order_page.content.decode("utf-8")
        assert "staffPartySize" in html
        assert "必須先入人數" in html
        # No pre-filled default headcount on the party field
        party_snip = html.split('id="staffPartySize"', 1)[1][:220]
        assert 'value="2"' not in party_snip
        assert 'value=""' in party_snip or "value=''" in party_snip

        missing = client.post(
            "/api/staff/bill/TABLE4/orders",
            json={
                "pin": pin,
                "guest_name": "Amy",
                "items": [{"item_id": "coke", "qty": 1}],
            },
        )
        assert missing.status_code == 400, missing.text
        assert "party size" in missing.json()["detail"].lower()

        ok = client.post(
            "/api/staff/bill/TABLE4/orders",
            json={
                "pin": pin,
                "guest_name": "Amy",
                "party_size": 4,
                "items": [{"item_id": "coke", "qty": 1}],
            },
        )
        assert ok.status_code == 200, ok.text
        assert ok.json()["party_size"] == 4

        conn = db.connect()
        sess = conn.execute(
            """
            SELECT s.party_size, s.guest_name FROM sessions s
            JOIN tables t ON t.id = s.table_id
            WHERE t.code = 'TABLE4' AND s.status = 'open'
            """
        ).fetchone()
        conn.close()
        assert sess is not None
        assert int(sess["party_size"]) == 4
        assert sess["guest_name"] == "Amy"


def test_staff_nom_requires_party_size_to_open_table():
    tmp = tempfile.mkdtemp(prefix="polar-nom-party-")
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
        bill = client.get(f"/staff/bill/TABLE5?pin={pin}")
        assert bill.status_code == 200
        assert b"staffNomParty" in bill.content

        missing = client.post(
            "/api/staff/bill/TABLE5/custom",
            json={
                "pin": pin,
                "custom_name": "Special bottle",
                "custom_price": 500,
                "qty": 1,
            },
        )
        assert missing.status_code == 400, missing.text

        ok = client.post(
            "/api/staff/bill/TABLE5/custom",
            json={
                "pin": pin,
                "custom_name": "Special bottle",
                "custom_price": 500,
                "qty": 1,
                "party_size": 3,
                "guest_name": "Walk-in",
            },
        )
        assert ok.status_code == 200, ok.text

        conn = db.connect()
        sess = conn.execute(
            """
            SELECT s.party_size FROM sessions s
            JOIN tables t ON t.id = s.table_id
            WHERE t.code = 'TABLE5' AND s.status = 'open'
            """
        ).fetchone()
        conn.close()
        assert sess is not None
        assert int(sess["party_size"]) == 3
