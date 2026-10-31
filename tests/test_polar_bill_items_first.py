"""Staff bill shows Items before move-table / party-size controls."""

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


def test_bill_page_items_before_admin_sections():
    tmp = tempfile.mkdtemp(prefix="polar-bill-order-")
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
            "/api/t/TABLE1/welcome",
            json={"guest_name": "ItemsFirst", "party_size": 2},
        )
        client.post(
            "/api/t/TABLE1/orders",
            json={"items": [{"item_id": "coke", "qty": 1}]},
        )
        # Open a second table so transfer targets exist
        client.post(
            "/api/t/TABLE2/welcome",
            json={"guest_name": "Other", "party_size": 1},
        )

        page = client.get(f"/staff/bill/TABLE1?pin={pin}")
        assert page.status_code == 200
        html = page.text
        assert 'id="billItemsCard"' in html
        assert 'id="partyConfirm"' in html
        assert 'id="transferBox"' in html
        items_at = html.index('id="billItemsCard"')
        transfer_at = html.index('id="transferBox"')
        party_at = html.index('id="partyConfirm"')
        pay_at = html.index("pay-method-card")
        clear_at = html.index('id="clearTableBox"')
        # Items → party → pay → clear → move table at the bottom
        assert items_at < party_at < pay_at < clear_at < transfer_at
