"""Staff Celestial cocktails: Regular vs Birthday Free ($0)."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_POLAR = _ROOT / "polar-order"
if str(_POLAR) not in sys.path:
    sys.path.insert(0, str(_POLAR))


def test_staff_birthday_free_cocktail():
    tmp = tempfile.mkdtemp(prefix="polar-bday-cocktail-")
    os.environ["POLAR_DATA_DIR"] = tmp
    os.environ["POLAR_STAFF_PIN"] = "polar2026"

    import importlib

    import app.paths as paths
    import app.db as db
    import app.main as main
    import app.pricing as pricing
    import app.cocktails as cocktails

    importlib.reload(paths)
    importlib.reload(db)
    importlib.reload(cocktails)
    importlib.reload(pricing)
    importlib.reload(main)

    from fastapi.testclient import TestClient

    pin = "polar2026"
    with TestClient(main.app) as client:
        page = client.get(f"/staff/order/TABLE1?pin={pin}")
        assert page.status_code == 200
        html = page.content
        assert b"Birthday Free = $0" in html
        assert b'data-serve-kind="birthday"' in html
        assert b"Regular|Birthday Free" in html or b"Regular" in html
        # Guest menu must not offer birthday picker
        client.post(
            "/api/t/TABLE2/welcome",
            json={"guest_name": "Guest", "party_size": 2},
        )
        guest = client.get("/t/TABLE2")
        assert guest.status_code == 200
        assert b'data-serve-kind="birthday"' not in guest.content
        assert b"Birthday Free" not in guest.content

        # Regular cocktail keeps menu price
        paid = client.post(
            "/api/staff/bill/TABLE1/orders",
            json={
                "pin": pin,
                "guest_name": "Amy",
                "party_size": 2,
                "items": [
                    {
                        "item_id": "aries",
                        "qty": 1,
                        "note": "Promo: Regular",
                    }
                ],
            },
        )
        assert paid.status_code == 200, paid.text

        free = client.post(
            "/api/staff/bill/TABLE1/orders",
            json={
                "pin": pin,
                "items": [
                    {
                        "item_id": "leo",
                        "qty": 1,
                        "note": "Promo: Birthday Free",
                    }
                ],
            },
        )
        assert free.status_code == 200, free.text

        bill = client.get(f"/staff/bill/TABLE1?pin={pin}")
        assert bill.status_code == 200
        assert b"Birthday Free" in bill.content
        assert b"$0" in bill.content

        conn = db.connect()
        session = db.get_open_session(conn, db.get_table_by_code(conn, "TABLE1")["id"])
        lines = [
            dict(x)
            for x in conn.execute(
                """
                SELECT oi.* FROM order_items oi
                JOIN orders o ON o.id = oi.order_id
                WHERE o.session_id = ? AND o.status != 'cancelled'
                """,
                (session["id"],),
            ).fetchall()
        ]
        conn.close()
        by_id = {x["item_id"]: x for x in lines}
        assert float(by_id["aries"]["unit_price"]) == 129.0
        assert float(by_id["leo"]["unit_price"]) == 0.0
        assert float(by_id["leo"]["line_total"]) == 0.0

        # Second Birthday Free on same table blocked
        again = client.post(
            "/api/staff/bill/TABLE1/orders",
            json={
                "pin": pin,
                "items": [
                    {
                        "item_id": "virgo",
                        "qty": 1,
                        "note": "Promo: Birthday Free",
                    }
                ],
            },
        )
        assert again.status_code == 400

        # Qty 2 Birthday Free in one request blocked
        client.post(
            "/api/t/TABLE3/welcome",
            json={"guest_name": "Other", "party_size": 1},
        )
        double = client.post(
            "/api/staff/bill/TABLE3/orders",
            json={
                "pin": pin,
                "guest_name": "Other",
                "party_size": 1,
                "items": [
                    {
                        "item_id": "pisces",
                        "qty": 2,
                        "note": "Promo: Birthday Free",
                    }
                ],
            },
        )
        assert double.status_code == 400

    # Pricing helper zeros Birthday Free regardless of happy hour
    priced = pricing.price_order_lines(
        [
            {
                "item_id": "aries",
                "name": "Aries",
                "category_id": "celestial",
                "promo": "drinks",
                "base_price": 129,
                "qty": 1,
                "note": "Promo: Birthday Free",
            }
        ],
        promo={
            "id": "happy_hour",
            "label": "Happy Hour",
            "drinks_off": 0.20,
            "drinks_label": "20% OFF",
            "shisha_price": None,
            "snack_combo_price": 40.0,
        },
    )
    assert priced[0]["unit_price"] == 0.0
    assert priced[0]["promo_tag"] == "Birthday Free"
