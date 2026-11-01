"""Free Flow party: custom head price, collect as guests arrive."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_POLAR = _ROOT / "polar-order"
if str(_POLAR) not in sys.path:
    sys.path.insert(0, str(_POLAR))


def test_ff_party_custom_head_prices():
    tmp = tempfile.mkdtemp(prefix="polar-ff-party-")
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
        bill = client.get(f"/staff/bill/TABLE1?pin={pin}")
        assert bill.status_code == 200
        assert b"Free Flow party" in bill.content
        assert b"Start Free Flow party" in bill.content

        enabled = client.post(
            "/api/staff/bill/TABLE1/ff-party/enable",
            json={
                "pin": pin,
                "party_name": "Amy birthday",
                "expected_size": 7,
                "default_price": 400,
                "waive_snacks": True,
            },
        )
        assert enabled.status_code == 200, enabled.text
        body = enabled.json()
        assert body["ff_party"] is True
        assert body["ff_expected"] == 7
        assert body["ff_default_price"] == 400
        assert body["snack_waived"] is True
        assert body["summary"]["paid_count"] == 0

        page = client.get(f"/staff/bill/TABLE1?pin={pin}")
        assert page.status_code == 200
        assert b"Amy birthday" in page.content or b"Expected 7" in page.content
        assert b"Guest arrives" in page.content
        assert b"Add &amp; collect" in page.content or b"Add & collect" in page.content

        # First guest — custom price, collect now
        g1 = client.post(
            "/api/staff/bill/TABLE1/ff-party/guests",
            json={
                "pin": pin,
                "guest_label": "Amy",
                "head_price": 450,
                "package_label": "With Shisha",
                "collect_now": True,
            },
        )
        assert g1.status_code == 200, g1.text
        assert g1.json()["guest"]["status"] == "paid"
        assert g1.json()["summary"]["paid_count"] == 1
        assert g1.json()["summary"]["paid_total"] == 450

        # Second guest — different price, pending then collect
        g2 = client.post(
            "/api/staff/bill/TABLE1/ff-party/guests",
            json={
                "pin": pin,
                "guest_label": "Ben",
                "head_price": 300,
                "package_label": "Without Shisha",
                "collect_now": False,
            },
        )
        assert g2.status_code == 200, g2.text
        pending_id = g2.json()["guest"]["id"]
        assert g2.json()["guest"]["status"] == "pending"
        assert g2.json()["summary"]["pending_count"] == 1

        paid = client.post(
            f"/api/staff/bill/TABLE1/ff-party/guests/{pending_id}/pay",
            json={"pin": pin},
        )
        assert paid.status_code == 200, paid.text
        assert paid.json()["summary"]["paid_count"] == 2
        assert paid.json()["summary"]["paid_total"] == 750

        bill2 = client.get(f"/staff/bill/TABLE1?pin={pin}")
        assert bill2.status_code == 200
        html = bill2.content.decode("utf-8")
        assert "Free Flow · Amy" in html
        assert "Free Flow · Ben" in html

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
        assert len(lines) == 2
        assert all(x["category_id"] == "free-flow" for x in lines)
        prices = sorted(float(x["unit_price"]) for x in lines)
        assert prices == [300.0, 450.0]

        calc = pricing.compute_bill(lines, party_size=7, snack_waived=True)
        # Free Flow heads: no service charge
        assert calc["serviceable_subtotal"] == 0.0
        assert calc["service_charge"] == 0.0
        assert calc["snack_charge"] == 0.0
        assert calc["subtotal"] == 750.0
        assert calc["total"] == 750.0

        # Staff order shows Free Flow party banner
        order = client.get(f"/staff/order/TABLE1?pin={pin}")
        assert order.status_code == 200
        assert b"Head fees are collected on the" in order.content

        # Cannot remove paid guest
        bad_del = client.post(
            f"/api/staff/bill/TABLE1/ff-party/guests/{g1.json()['guest']['id']}/delete",
            json={"pin": pin},
        )
        assert bad_del.status_code == 400
