"""Glass spirits: Neat / On the Rocks. Bottle spirits: mixer choice."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_POLAR = _ROOT / "polar-order"
if str(_POLAR) not in sys.path:
    sys.path.insert(0, str(_POLAR))


def test_spirit_glass_style_and_bottle_mixer():
    tmp = tempfile.mkdtemp(prefix="polar-serve-")
    os.environ["POLAR_DATA_DIR"] = tmp
    os.environ["POLAR_STAFF_PIN"] = "polar2026"

    import importlib

    import app.paths as paths
    import app.db as db
    import app.main as main
    from app.spirits import SPIRIT_BOTTLE_MIXERS, SPIRIT_GLASS_SERVES

    importlib.reload(paths)
    importlib.reload(db)
    importlib.reload(main)

    from fastapi.testclient import TestClient

    with TestClient(main.app) as client:
        welcome = client.post(
            "/api/t/TABLE1/welcome",
            json={"guest_name": "Serve", "party_size": 2},
        )
        assert welcome.status_code == 200

        page = client.get("/t/TABLE1")
        assert page.status_code == 200
        html = page.text
        assert "How to serve" in html or "Choose mixer" in html
        assert "Neat|On the Rocks" in html
        assert "Soda Water|Tonic Water|Coke" in html

        conn = db.connect()
        glass = conn.execute(
            """
            SELECT id FROM menu_items
            WHERE category_id = 'vodka' AND unit = 'Glass' AND available = 1
            LIMIT 1
            """
        ).fetchone()
        bottle = conn.execute(
            """
            SELECT id FROM menu_items
            WHERE category_id = 'vodka' AND unit = 'Bottle' AND available = 1
            LIMIT 1
            """
        ).fetchone()
        conn.close()
        assert glass and bottle

        glass_chunk = html.split(f'data-id="{glass["id"]}"', 1)[1][:500]
        assert 'data-serve-kind="style"' in glass_chunk
        assert "Neat|On the Rocks" in glass_chunk
        assert "Soda Water" not in glass_chunk

        bottle_chunk = html.split(f'data-id="{bottle["id"]}"', 1)[1][:500]
        assert 'data-serve-kind="mixer"' in bottle_chunk
        assert "Soda Water|Tonic Water|Coke" in bottle_chunk

        assert SPIRIT_GLASS_SERVES == ("Neat", "On the Rocks")
        assert SPIRIT_BOTTLE_MIXERS == ("Soda Water", "Tonic Water", "Coke")

        placed = client.post(
            "/api/t/TABLE1/orders",
            json={
                "items": [
                    {"item_id": glass["id"], "qty": 1, "note": "Serve: On the Rocks"},
                    {
                        "item_id": bottle["id"],
                        "qty": 1,
                        "note": f"Mixer: {SPIRIT_BOTTLE_MIXERS[0]}",
                    },
                ]
            },
        )
        assert placed.status_code == 200, placed.text

        mine = client.get("/api/t/TABLE1/my-orders")
        notes = [i.get("note") or "" for o in mine.json()["orders"] for i in o["items"]]
        assert any("On the Rocks" in n for n in notes)
        assert any("Soda Water" in n for n in notes)
