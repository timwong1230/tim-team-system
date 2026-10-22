"""Spirit serve choices: glass style/mixer, bottle mixer, Single Mix tower."""

from __future__ import annotations

from typing import Any

# Keep in sync with Ask AI mood playbooks (ai_host.SPIRIT_CATS).
SPIRIT_CATS = ("vodka", "gin", "whisky", "liqueur", "tequila", "rum", "cognac")

# Single Mix tower — house spirits only (no liqueur / tequila / cognac).
SINGLE_MIX_SPIRIT_CATS = ("vodka", "gin", "whisky", "rum")

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
    """Two-step picker: house spirit (cheapest per type), then mixer."""
    return {
        "kind": "single_mix",
        "options": [],  # filled client-side in two steps
        "spirits": spirit_options,
        "mixers": list(SPIRIT_MIXERS),
        "title": "Single Mix",
        "chip": "House spirit + mixer",
        "note_prefix": "Spirit",
    }


def list_spirit_glass_options(conn) -> list[dict[str, str]]:
    """Cheapest glass (house) spirit per Single Mix category."""
    cats = SINGLE_MIX_SPIRIT_CATS
    rows = conn.execute(
        """
        SELECT mi.id, mi.name, mi.price, mc.id AS category_id,
               mc.name AS category_name, mc.sort_order
        FROM menu_items mi
        JOIN menu_categories mc ON mc.id = mi.category_id
        WHERE mi.available = 1
          AND mi.unit = 'Glass'
          AND mc.id IN ({placeholders})
        ORDER BY mc.sort_order ASC, mi.price ASC, mi.name ASC
        """.format(placeholders=",".join("?" * len(cats))),
        cats,
    ).fetchall()
    # One house pour per spirit type — lowest Glass price (name tie-break).
    best: dict[str, Any] = {}
    for r in rows:
        cid = r["category_id"]
        if cid in best:
            continue
        best[cid] = {
            "id": r["id"],
            "name": r["name"],
            "category": r["category_name"],
            "category_id": cid,
            "price": float(r["price"]),
            "label": f"{r['category_name']} · {r['name']}",
        }
    order = {cid: i for i, cid in enumerate(cats)}
    return sorted(best.values(), key=lambda x: order.get(x["category_id"], 99))
