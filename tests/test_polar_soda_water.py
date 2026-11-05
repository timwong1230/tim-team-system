"""Soda Water under Non Alcohol Soft Drinks."""

from __future__ import annotations

import json
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_POLAR = _ROOT / "polar-order"
_MENU = _POLAR / "data" / "menu.json"


def test_soda_water_in_non_alcohol_menu_json():
    menu = json.loads(_MENU.read_text(encoding="utf-8"))
    non_alc = next(c for c in menu["categories"] if c["id"] == "non-alcohol")
    item = next(i for i in non_alc["items"] if i["id"] == "soda-water")
    assert item["name"] == "Soda Water"
    assert item["price"] == 59
    assert item["unit"] == "Glass"
    assert item["image"].endswith("soda-water.jpg")
    assert (_POLAR / "static/images/menu/soda-water.jpg").is_file()


def test_soda_water_in_guest_soft_drinks_leaf():
    import sys

    sys.path = [str(_POLAR)] + [p for p in sys.path if Path(p).resolve() != _ROOT]
    for _name in list(sys.modules):
        if _name == "app" or _name.startswith("app."):
            del sys.modules[_name]

    from app.guest_nav import GUEST_NAV_TREE, _filter_items

    menu = json.loads(_MENU.read_text(encoding="utf-8"))
    non_alc = next(c for c in menu["categories"] if c["id"] == "non-alcohol")
    non_group = next(n for n in GUEST_NAV_TREE if n["id"] == "non-alcohol")
    soft = next(c for c in non_group["children"] if c["id"] == "soft-drinks")
    names = [i["name"] for i in _filter_items(non_alc["items"], soft)]
    assert "Soda Water" in names
    assert "Apple Juice" not in names
