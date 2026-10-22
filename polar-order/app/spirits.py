"""Spirit serve choices: glass style vs bottle mixer."""

from __future__ import annotations

from typing import Any

# Keep in sync with Ask AI mood playbooks (ai_host.SPIRIT_CATS).
SPIRIT_CATS = ("vodka", "gin", "whisky", "liqueur", "tequila", "rum", "cognac")

# Bottle → mixer with the spirit.
SPIRIT_BOTTLE_MIXERS = ("Soda Water", "Tonic Water", "Coke")

# Glass → how to pour.
SPIRIT_GLASS_SERVES = ("Neat", "On the Rocks")


def spirit_serve_for(category_id: str, unit: str | None) -> dict[str, Any] | None:
    """Return serve picker config for spirit items, or None if not applicable."""
    if category_id not in SPIRIT_CATS:
        return None
    u = (unit or "").strip()
    if u == "Bottle":
        return {
            "kind": "mixer",
            "options": list(SPIRIT_BOTTLE_MIXERS),
            "title": "Choose mixer",
            "chip": "Pick a mixer",
            "note_prefix": "Mixer",
        }
    if u == "Glass":
        return {
            "kind": "style",
            "options": list(SPIRIT_GLASS_SERVES),
            "title": "How to serve",
            "chip": "Neat or rocks",
            "note_prefix": "Serve",
        }
    return None
