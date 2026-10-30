"""Tower items show (2 Litres) in the display name."""

from __future__ import annotations

import json
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_MENU = _ROOT / "polar-order" / "data" / "menu.json"


def test_tower_items_end_with_2_litres():
    menu = json.loads(_MENU.read_text(encoding="utf-8"))
    tower = next(c for c in menu["categories"] if c["id"] == "tower")
    names = {i["id"]: i["name"] for i in tower["items"]}
    assert names["bottle-tower"].endswith("(2 Litres)")
    assert names["draft-tower"].endswith("(2 Litres)")
    assert names["single-mix"].endswith("(2 Litres)")
    assert names["bottle-tower"] == "Bottle Beer Tower (2 Litres)"
    assert names["draft-tower"] == "Draft Beer Tower (2 Litres)"
    assert names["single-mix"] == "Single Mix (2 Litres)"
