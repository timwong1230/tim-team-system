"""Yager Bomb sits under Liqueur Glass without spirit serve picker."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_POLAR = _ROOT / "polar-order"
_MENU = _POLAR / "data" / "menu.json"


def test_yager_bomb_in_liqueur_glass_menu_json():
    menu = json.loads(_MENU.read_text(encoding="utf-8"))
    liqueur = next(c for c in menu["categories"] if c["id"] == "liqueur")
    item = next(i for i in liqueur["items"] if i["id"] == "yager-bomb")
    assert item["name"] == "Yager Bomb"
    assert item["price"] == 109
    assert item["unit"] == "Glass"
    assert item["image"].endswith("yager-bomb.jpg")
    assert (_POLAR / "static/images/menu/yager-bomb.jpg").is_file()
    glass_ids = [i["id"] for i in liqueur["items"] if i.get("unit") == "Glass"]
    bottle_ids = [i["id"] for i in liqueur["items"] if i.get("unit") == "Bottle"]
    assert "yager-bomb" in glass_ids
    assert "yager-bomb" not in bottle_ids
    # Listed with other Glass pours (before Bottle block)
    assert glass_ids.index("yager-bomb") < len(glass_ids)
    yager_pos = next(i for i, x in enumerate(liqueur["items"]) if x["id"] == "yager-bomb")
    first_bottle = next(i for i, x in enumerate(liqueur["items"]) if x.get("unit") == "Bottle")
    assert yager_pos < first_bottle


def test_yager_bomb_no_serve_picker_on_guest_page():
    sys.path = [str(_POLAR)] + [p for p in sys.path if Path(p).resolve() != _ROOT]
    for _name in list(sys.modules):
        if _name == "app" or _name.startswith("app."):
            del sys.modules[_name]

    tmp = tempfile.mkdtemp(prefix="polar-yager-")
    os.environ["POLAR_DATA_DIR"] = tmp
    os.environ["POLAR_STAFF_PIN"] = "polar2026"

    import importlib

    import app.paths as paths
    import app.db as db
    import app.main as main
    import app.spirits as spirits

    importlib.reload(paths)
    importlib.reload(db)
    importlib.reload(spirits)
    importlib.reload(main)

    assert spirits.spirit_serve_for("liqueur", "Glass", item_id="yager-bomb") is None
    assert spirits.spirit_serve_for("liqueur", "Glass", item_id="jager-g") is not None

    from fastapi.testclient import TestClient

    with TestClient(main.app) as client:
        client.post(
            "/api/t/TABLE1/welcome",
            json={"guest_name": "Yager", "party_size": 2},
        )
        page = client.get("/t/TABLE1")
        assert page.status_code == 200
        assert b"Yager Bomb" in page.content
        assert b"yager-bomb.jpg" in page.content
        # Item card should not advertise mixer chip
        html = page.text
        start = html.index('data-id="yager-bomb"')
        chunk = html[start : start + 900]
        assert "data-serve-kind" not in chunk
