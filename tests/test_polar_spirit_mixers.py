"""Glass spirits require mixer options; bottles do not."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_POLAR = _ROOT / "polar-order"
if str(_POLAR) not in sys.path:
    sys.path.insert(0, str(_POLAR))


def test_glass_spirits_have_mixer_options():
    tmp = tempfile.mkdtemp(prefix="polar-mixers-")
    os.environ["POLAR_DATA_DIR"] = tmp
    os.environ["POLAR_STAFF_PIN"] = "polar2026"

    import importlib

    import app.paths as paths
    import app.db as db
    import app.main as main
    from app.spirits import SPIRIT_MIXERS

    importlib.reload(paths)
    importlib.reload(db)
    importlib.reload(main)

    from fastapi.testclient import TestClient

    with TestClient(main.app) as client:
        welcome = client.post(
            "/api/t/TABLE1/welcome",
            json={"guest_name": "Mix", "party_size": 2},
        )
        assert welcome.status_code == 200

        page = client.get("/t/TABLE1")
        assert page.status_code == 200
        assert b"Choose mixer" in page.content
        assert b"Soda Water|Tonic Water|Coke" in page.content
        assert b"Pick a mixer" in page.content

        conn = db.connect()
        glass = conn.execute(
            """
            SELECT id, name FROM menu_items
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
        assert glass is not None
        assert bottle is not None

        # Menu payload via HTML data attrs: glass has mixers, bottle does not
        html = page.text
        assert f'data-id="{glass["id"]}"' in html
        glass_chunk = html.split(f'data-id="{glass["id"]}"', 1)[1][:400]
        assert "data-mixers=" in glass_chunk
        bottle_chunk = html.split(f'data-id="{bottle["id"]}"', 1)[1][:400]
        assert "data-mixers=" not in bottle_chunk

        placed = client.post(
            "/api/t/TABLE1/orders",
            json={
                "items": [
                    {
                        "item_id": glass["id"],
                        "qty": 1,
                        "note": f"Mixer: {SPIRIT_MIXERS[1]}",
                    }
                ]
            },
        )
        assert placed.status_code == 200, placed.text

        mine = client.get("/api/t/TABLE1/my-orders")
        assert mine.status_code == 200
        body = mine.json()
        notes = [i.get("note") for o in body["orders"] for i in o["items"]]
        assert any(n and "Tonic Water" in n for n in notes)
