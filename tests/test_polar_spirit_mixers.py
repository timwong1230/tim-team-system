"""Glass: Neat/Rocks + mixers. Bottle: mixers. Single Mix: spirit + mixer."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_POLAR = _ROOT / "polar-order"
if str(_POLAR) not in sys.path:
    sys.path.insert(0, str(_POLAR))


def test_spirit_serve_and_single_mix():
    tmp = tempfile.mkdtemp(prefix="polar-serve-")
    os.environ["POLAR_DATA_DIR"] = tmp
    os.environ["POLAR_STAFF_PIN"] = "polar2026"

    import importlib

    import app.paths as paths
    import app.db as db
    import app.main as main
    from app.spirits import SPIRIT_MIXERS, SPIRIT_GLASS_STYLES

    importlib.reload(paths)
    importlib.reload(db)
    importlib.reload(main)

    from fastapi.testclient import TestClient

    with TestClient(main.app) as client:
        assert client.post(
            "/api/t/TABLE1/welcome",
            json={"guest_name": "Serve", "party_size": 2},
        ).status_code == 200

        page = client.get("/t/TABLE1")
        assert page.status_code == 200
        html = page.text
        assert "Neat|On the Rocks|Soda Water|Tonic Water|Coke" in html
        assert "Soda Water|Tonic Water|Coke" in html
        assert 'data-serve-kind="single_mix"' in html
        assert b"POLAR_SINGLE_MIX_SPIRITS" in page.content
        assert "House spirit + mixer" in html

        conn = db.connect()
        from app.spirits import list_spirit_glass_options, SINGLE_MIX_SPIRIT_CATS

        house = list_spirit_glass_options(conn)
        assert len(house) == len(SINGLE_MIX_SPIRIT_CATS)
        assert {h["category_id"] for h in house} == set(SINGLE_MIX_SPIRIT_CATS)
        house_names = {h["name"] for h in house}
        assert "Jessy's Barrel" in house_names  # vodka/gin/rum house
        assert "Claymore" in house_names
        assert "Baileys" not in house_names
        assert "Jose Cuervo Silver" not in house_names
        assert "VSOP" not in house_names
        assert "Belvedere" not in house_names

        # Embedded JSON for Single Mix must only list allowed house pours
        import json
        import re

        m = re.search(r"POLAR_SINGLE_MIX_SPIRITS = (\[.*?\]);", html, re.S)
        assert m, "missing POLAR_SINGLE_MIX_SPIRITS"
        embedded = json.loads(m.group(1))
        assert len(embedded) == len(SINGLE_MIX_SPIRIT_CATS)
        assert {e["name"] for e in embedded} == house_names
        assert not any(
            x in html[m.start() : m.end()]
            for x in ("Baileys", "Jose Cuervo", "VSOP", "Tequila", "Cognac", "Liqueur")
        )

        glass = conn.execute(
            "SELECT id FROM menu_items WHERE category_id='vodka' AND unit='Glass' AND available=1 LIMIT 1"
        ).fetchone()
        bottle = conn.execute(
            "SELECT id FROM menu_items WHERE category_id='vodka' AND unit='Bottle' AND available=1 LIMIT 1"
        ).fetchone()
        conn.close()

        glass_chunk = html.split(f'data-id="{glass["id"]}"', 1)[1][:600]
        assert 'data-serve-kind="glass"' in glass_chunk
        assert "Neat|On the Rocks|Soda Water" in glass_chunk

        bottle_chunk = html.split(f'data-id="{bottle["id"]}"', 1)[1][:500]
        assert 'data-serve-kind="mixer"' in bottle_chunk
        assert "Neat|" not in bottle_chunk

        assert SPIRIT_GLASS_STYLES == ("Neat", "On the Rocks")
        assert SPIRIT_MIXERS == ("Soda Water", "Tonic Water", "Coke")

        vodka_house = next(h for h in house if h["category_id"] == "vodka")
        placed = client.post(
            "/api/t/TABLE1/orders",
            json={
                "items": [
                    {"item_id": glass["id"], "qty": 1, "note": "Mixer: Coke"},
                    {
                        "item_id": "single-mix",
                        "qty": 1,
                        "note": f"Spirit: {vodka_house['name']} · Mixer: Tonic Water",
                    },
                ]
            },
        )
        assert placed.status_code == 200, placed.text
        mine = client.get("/api/t/TABLE1/my-orders").json()
        notes = [i.get("note") or "" for o in mine["orders"] for i in o["items"]]
        assert any("Coke" in n for n in notes)
        assert any(vodka_house["name"] in n and "Tonic Water" in n for n in notes)
