"""Guest nested category hub + staff table session transfer."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path


_ROOT = Path(__file__).resolve().parents[1]
_POLAR = _ROOT / "polar-order"
if str(_POLAR) not in sys.path:
    sys.path.insert(0, str(_POLAR))


def test_guest_nested_hub_and_staff_transfer():
    tmp = tempfile.mkdtemp(prefix="polar-cat-transfer-")
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
        assert "guest-cat-rail" in html
        assert "guest-shell" in html
        assert "Choose a category" in html
        assert "Tap a category on the left" in html
        # Cache-bust static assets for iPhone Safari
        assert f"app.css?v={main.ASSET_VERSION}" in html
        assert f"guest.js?v={main.ASSET_VERSION}" in html
        assert "promo-details" in html
        # Left rail stays mounted; promo sits above the shell
        assert html.index("promo-details") < html.index("guest-shell")
        assert html.index("guest-cat-rail") < html.index("guest-main")
        # Top-level only — not every DB category at once
        assert "Celestial Signature Cocktails" in html
        # Left-rail label breaks on word boundaries (not mid-word hyphens)
        assert "Celestial<br>Signature<br>Cocktails" in html
        assert "Spirit" in html
        assert "Wine" in html
        assert 'id="sub-wine"' in html
        assert 'id="sub-spirit"' in html
        assert 'id="sub-beer"' in html
        assert 'id="sub-non-alcohol"' in html
        assert "Red Wine" in html
        assert "Draft Beer" in html
        assert "Soft Drinks" in html
        assert "Special Tea" in html
        assert 'id="leaf-shisha"' in html
        assert "Regular Shisha" in html
        assert "Change Head" in html
        assert "← Categories" in html
        # Flat old cat buttons for every DB category should not be the root hub
        assert html.count('data-nav-kind="group"') >= 4
        assert html.count('data-nav-kind="products"') >= 9
        # Left rail must stay visible when switching categories (no hide-all on hub)
        js = (_POLAR / "static" / "js" / "guest.js").read_text(encoding="utf-8")
        assert "Left category rail stays visible" in js
        assert "hideAllNavPanels" not in js
        assert "openDefaultCategory" in js
        assert 'querySelector("#cats .cat-btn")' in js
        # First root category is Shisha (products leaf)
        assert guest_nav.GUEST_NAV_TREE[0]["id"] == "shisha"
        assert guest_nav.GUEST_NAV_TREE[0]["kind"] == "products"

        headers = client.get("/t/TABLE1").headers
        assert "no-store" in (headers.get("cache-control") or "").lower()

        conn = db.connect()
        tree = guest_nav.build_guest_nav(main._menu_payload(conn))
        item = conn.execute(
            "SELECT id FROM menu_items WHERE available = 1 ORDER BY id LIMIT 1"
        ).fetchone()
        conn.close()

        root_names = [r["name"] for r in tree["roots"]]
        assert root_names == [
            "Shisha",
            "Celestial Signature Cocktails",
            "Wine",
            "Beer",
            "Tower",
            "Spirit",
            "Champagne",
            "Non Alcohol",
            "Bar Snacks",
        ]
        spirit = next(r for r in tree["roots"] if r["id"] == "spirit")
        assert [c["name"] for c in spirit["children"]] == [
            "Vodka",
            "Gin",
            "Whisky",
            "Liqueur",
            "Tequila",
            "Cognac",
        ]
        leaves = {leaf["id"]: leaf for leaf in tree["leaves"]}
        assert any(i["name"] == "Regular Shisha" for i in leaves["shisha"]["items"])
        assert any(i["unit"] == "Glass" for i in leaves["draft-beer"]["items"])
        assert all(i["unit"] == "Bottle" for i in leaves["bottle-beer"]["items"])
        assert {i["id"] for i in leaves["juice"]["items"]} <= {"aj", "oj", "cran"}
        assert "tea-orange" in {i["id"] for i in leaves["special-tea"]["items"]}
        assert item is not None

        placed = client.post(
            "/api/t/TABLE1/orders",
            json={"items": [{"item_id": item["id"], "qty": 2}]},
        )
        assert placed.status_code == 200, placed.text

        bill1 = client.get(f"/staff/bill/TABLE1?pin={pin}")
        assert bill1.status_code == 200
        assert b"Move to another table" in bill1.content

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
        assert data["to_table"] == "TABLE3"

        conn = db.connect()
        s1 = db.get_open_session(conn, db.get_table_by_code(conn, "TABLE1")["id"])
        s3 = db.get_open_session(conn, db.get_table_by_code(conn, "TABLE3")["id"])
        assert s1 is None
        assert s3 is not None
        assert s3["guest_name"] == "Chris"
        conn.close()
