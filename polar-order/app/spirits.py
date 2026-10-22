"""Spirit serve choices: glass style/mixer, bottle mixer, Single Mix tower."""

from __future__ import annotations

from typing import Any

# Keep in sync with Ask AI mood playbooks (ai_host.SPIRIT_CATS).
SPIRIT_CATS = ("vodka", "gin", "whisky", "liqueur", "tequila", "rum", "cognac")

SPIRIT_MIXERS = ("Soda Water", "Tonic Water", "Coke")
SPIRIT_BOTTLE_MIXERS = SPIRIT_MIXERS

# Glass → pour style + same mixers as bottle.
SPIRIT_GLASS_STYLES = ("Neat", "On the Rocks")
SPIRIT_GLASS_SERVES = SPIRIT_GLASS_STYLES  # back-compat name

SINGLE_MIX_ITEM_ID = "single-mix"


def note_prefix_for_choice(choice: str) -> str:
    if choice in SPIRIT_GLASS_STYLES:
        return "Serve"
    return "Mixer"


def spirit_serve_for(category_id: str, unit: str | None) -> dict[str, Any] | None:
    """Return serve picker config for spirit items, or None if not applicable."""
    if category_id not in SPIRIT_CATS:
        return None
    u = (unit or "").strip()
    if u == "Bottle":
        return {
            "kind": "mixer",
            "options": list(SPIRIT_MIXERS),
            "title": "Choose mixer",
            "chip": "Pick a mixer",
            "note_prefix": "Mixer",
        }
    if u == "Glass":
        return {
            "kind": "glass",
            "options": list(SPIRIT_GLASS_STYLES) + list(SPIRIT_MIXERS),
            "title": "How to serve",
            "chip": "Neat, rocks or mixer",
            "note_prefix": "Serve",  # client overrides for mixer picks
        }
    return None


def single_mix_serve(spirit_options: list[dict[str, str]]) -> dict[str, Any]:
    """Two-step picker: spirit brand, then mixer."""
    return {
        "kind": "single_mix",
        "options": [],  # filled client-side in two steps
        "spirits": spirit_options,
        "mixers": list(SPIRIT_MIXERS),
        "title": "Single Mix",
        "chip": "Pick spirit + mixer",
        "note_prefix": "Spirit",
    }


def list_spirit_glass_options(conn) -> list[dict[str, str]]:
    """Glass spirit brands for Single Mix (category label + name)."""
    rows = conn.execute(
        """
        SELECT mi.id, mi.name, mc.name AS category_name, mc.sort_order
        FROM menu_items mi
        JOIN menu_categories mc ON mc.id = mi.category_id
        WHERE mi.available = 1
          AND mi.unit = 'Glass'
          AND mc.id IN ({placeholders})
        ORDER BY mc.sort_order ASC, mi.name ASC
        """.format(placeholders=",".join("?" * len(SPIRIT_CATS))),
        SPIRIT_CATS,
    ).fetchall()
    return [
        {
            "id": r["id"],
            "name": r["name"],
            "category": r["category_name"],
            "label": f"{r['category_name']} · {r['name']}",
        }
        for r in rows
    ]
