"""Staff can place Not on Menu as the first bill item (no prior menu order)."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_POLAR = _ROOT / "polar-order"
if str(_POLAR) not in sys.path:
    sys.path.insert(0, str(_POLAR))


def test_staff_not_on_menu_as_first_item():
    tmp = tempfile.mkdtemp(prefix="polar-staff-nom-")
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
    js = (_POLAR / "static/js/staff_order.js").read_text(encoding="utf-8")
    assert "Always show the bar" in js or "Not on Menu" in js
    assert 'cartBar.style.display = "none"' not in js
    assert 'openBtn.textContent = "Not on Menu"' in js

    html = (_POLAR / "templates/staff_order.html").read_text(encoding="utf-8")
    assert 'id="cartBar"' in html
    assert 'style="display:none"' not in html.split('id="cartBar"')[1].split(">")[0]
    assert ">Not on Menu</button>" in html

    bill_html = (_POLAR / "templates/staff_bill.html").read_text(encoding="utf-8")
    # NOM block is outside `{% if bill %}` so empty tables can add it first
    bill_if = bill_html.find("{% if bill %}")
    nom_idx = bill_html.find('class="card nom-box"')
    assert bill_if != -1 and nom_idx != -1 and nom_idx > bill_if
    clear_idx = bill_html.find('id="clearTableBtn"')
    assert clear_idx != -1 and clear_idx < nom_idx
    bill_close = bill_html.find("{% endif %}", clear_idx)
    assert bill_close != -1 and bill_close < nom_idx

    with TestClient(main.app) as client:
        order_page = client.get(f"/staff/order/TABLE2?pin={pin}")
        assert order_page.status_code == 200
        assert b'id="cartBar"' in order_page.content
        assert b'id="nomBox"' in order_page.content
        assert b">Not on Menu</button>" in order_page.content

        # Empty table — bill page still shows Not on Menu (no prior menu item)
        empty_bill = client.get(f"/staff/bill/TABLE2?pin={pin}")
        assert empty_bill.status_code == 200
        assert b"No open session" in empty_bill.content
        assert b"Not on Menu" in empty_bill.content
        assert b"staffNomAdd" in empty_bill.content

        # API: NOM-only order via staff place-order (first item)
        res = client.post(
            "/api/staff/bill/TABLE2/orders",
            json={
                "pin": pin,
                "guest_name": "NOM Guest",
                "party_size": 2,
                "items": [
                    {
                        "item_id": "not-on-menu",
                        "qty": 1,
                        "custom_name": "Guest bottle",
                        "custom_price": 880,
                    }
                ],
            },
        )
        assert res.status_code == 200, res.text
        data = res.json()
        assert data["ok"] is True
        assert data["guest_name"] == "NOM Guest"

        bill = client.get(f"/staff/bill/TABLE2?pin={pin}")
        assert bill.status_code == 200
        assert b"Guest bottle" in bill.content
        assert b"Not on Menu" in bill.content

        # Fresh table — custom endpoint creates Walk-in session for first NOM line
        # Party size is required to open the table.
        res2 = client.post(
            "/api/staff/bill/TABLE3/custom",
            json={
                "pin": pin,
                "custom_name": "Off-menu shot",
                "custom_price": 68,
                "qty": 2,
                "party_size": 2,
                "guest_name": "Walk-in",
            },
        )
        assert res2.status_code == 200, res2.text
        assert res2.json()["ok"] is True

        bill3 = client.get(f"/staff/bill/TABLE3?pin={pin}")
        assert bill3.status_code == 200
        assert b"Off-menu shot" in bill3.content
