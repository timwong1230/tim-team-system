"""Rosé bottle belongs under White Wine, not Red Wine."""

from __future__ import annotations

import json
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_MENU = _ROOT / "polar-order" / "data" / "menu.json"


def test_rose_in_white_wine_not_red():
    menu = json.loads(_MENU.read_text(encoding="utf-8"))
    by_id = {c["id"]: c for c in menu["categories"]}
    red_ids = {i["id"] for i in by_id["red-wine"]["items"]}
    white_ids = {i["id"] for i in by_id["white-wine"]["items"]}
    assert "rose-b" not in red_ids
    assert "rose-b" in white_ids
    rose = next(i for i in by_id["white-wine"]["items"] if i["id"] == "rose-b")
    assert "Rosé" in rose["name"] or "Rose" in rose["name"]
