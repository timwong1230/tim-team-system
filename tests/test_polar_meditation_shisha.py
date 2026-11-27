"""Staff-only Meditation Hour Shisha stays $250 after 5pm."""

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


def test_meditation_shisha_is_staff_only_and_stays_250():
    tmp = tempfile.mkdtemp(prefix="polar-meditation-shisha-")
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

    menu_json = json.loads((_POLAR / "data" / "menu.json").read_text(encoding="utf-8"))
    shisha = next(c for c in menu_json["categories"] if c["id"] == "shisha")
    item = next(i for i in shisha["items"] if i["id"] == "shisha-meditation")
    assert item["name"] == "Meditation Hour Shisha"
    assert item["price"] == 250
    assert item.get("staff_only") is True
    assert shisha.get("staff_only") is not True

    happy = {
        "id": "happy_hour",
        "label": "Happy Hour",
        "drinks_off": 0.20,
        "drinks_label": "20% OFF",
        "shisha_price": None,
        "snack_combo_price": 40.0,
    }
    regular = {
        "id": "regular",
        "label": "Regular pricing",
        "drinks_off": 0.0,
        "drinks_label": None,
        "shisha_price": None,
        "snack_combo_price": 40.0,
    }
    meditation = {
        "id": "meditation",
        "label": "Meditation Hour",
        "drinks_off": 0.30,
        "drinks_label": "30% OFF",
        "shisha_price": 250.0,
        "snack_combo_price": 40.0,
    }
    for promo in (happy, regular, meditation):
        price, tag = pricing.price_item(
            250, "shisha", promo, item_id="shisha-meditation"
        )
        assert price == 250.0
        assert tag is None
    late_regular, _ = pricing.price_item(
        398, "shisha", happy, item_id="shisha-regular"
    )
    assert late_regular == 398.0

    priced = pricing.price_order_lines(
        [
            {
                "item_id": "shisha-meditation",
                "name": "Meditation Hour Shisha",
                "category_id": "shisha",
                "promo": "shisha",
                "base_price": 250,
                "qty": 1,
            },
            {
                "item_id": "fries",
                "name": "French Fries",
                "category_id": "snacks",
                "promo": "snacks",
                "base_price": 58,
                "qty": 1,
            },
        ],
        promo=happy,
    )
    by_id = {row["item_id"]: row for row in priced}
    assert by_id["shisha-meditation"]["unit_price"] == 250.0
    assert by_id["fries"]["unit_price"] == 40.0

    pin = "polar2026"
    with TestClient(main.app) as client:
        staff = client.get(f"/staff/order/TABLE1?pin={pin}")
        assert staff.status_code == 200
        assert b"Meditation Hour Shisha" in staff.content
        assert b"shisha-meditation" in staff.content
        assert b"$250" in staff.content

        welcome = client.post(
            "/api/t/TABLE1/welcome",
            json={"guest_name": "Late Shisha", "party_size": 2},
        )
        assert welcome.status_code == 200, welcome.text
        guest = client.get("/t/TABLE1")
        assert guest.status_code == 200
        assert b"Meditation Hour Shisha" not in guest.content
        assert b"shisha-meditation" not in guest.content

        blocked = client.post(
            "/api/t/TABLE1/orders",
            json={"items": [{"item_id": "shisha-meditation", "qty": 1}]},
        )
        assert blocked.status_code == 400, blocked.text

        ordered = client.post(
            "/api/staff/bill/TABLE1/orders",
            json={
                "pin": pin,
                "items": [
                    {"item_id": "shisha-meditation", "qty": 1, "note": "apple"},
                    {"item_id": "fries", "qty": 1},
                ],
            },
        )
        assert ordered.status_code == 200, ordered.text

        conn = db.connect()
        session = db.get_open_session(conn, db.get_table_by_code(conn, "TABLE1")["id"])
        rows = conn.execute(
            """
            SELECT oi.item_id, oi.unit_price, oi.line_total
            FROM order_items oi
            JOIN orders o ON o.id = oi.order_id
            WHERE o.session_id = ? AND o.status != 'cancelled'
            """,
            (session["id"],),
        ).fetchall()
        conn.close()
        saved = {r["item_id"]: r for r in rows}
        assert float(saved["shisha-meditation"]["unit_price"]) == 250.0
        assert float(saved["fries"]["unit_price"]) == 40.0
