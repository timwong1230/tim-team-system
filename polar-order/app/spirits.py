"""Spirit categories and mixer choices for glass pours."""

from __future__ import annotations

# Keep in sync with Ask AI mood playbooks (ai_host.SPIRIT_CATS).
SPIRIT_CATS = ("vodka", "gin", "whisky", "liqueur", "tequila", "rum", "cognac")

# Guest / staff must pick one when ordering a Glass spirit.
SPIRIT_MIXERS = ("Soda Water", "Tonic Water", "Coke")


def mixer_options_for(category_id: str, unit: str | None) -> list[str] | None:
    if category_id not in SPIRIT_CATS:
        return None
    if (unit or "").strip() != "Glass":
        return None
    return list(SPIRIT_MIXERS)
