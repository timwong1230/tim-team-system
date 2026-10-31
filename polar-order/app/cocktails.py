"""Celestial cocktail staff options (birthday free promo)."""

from __future__ import annotations

from typing import Any

CELESTIAL_CATEGORY_ID = "celestial"
BIRTHDAY_FREE_LABEL = "Birthday Free"
BIRTHDAY_REGULAR_LABEL = "Regular"
BIRTHDAY_FREE_MARKER = "birthday free"


def cocktail_birthday_serve(category_id: str) -> dict[str, Any] | None:
    """Staff-only picker: Regular (paid) vs Birthday Free ($0)."""
    if category_id != CELESTIAL_CATEGORY_ID:
        return None
    return {
        "kind": "birthday",
        "options": [BIRTHDAY_REGULAR_LABEL, BIRTHDAY_FREE_LABEL],
        "title": "Regular or Birthday Free?",
        "chip": "Birthday Free = $0",
        "note_prefix": "Promo",
    }


def note_is_birthday_free(note: str | None) -> bool:
    return BIRTHDAY_FREE_MARKER in (note or "").lower()


def count_birthday_free_qty(lines: list[dict], *, extra_notes: list[str] | None = None) -> int:
    """Count Birthday Free cocktail portions (session lines + optional new notes)."""
    total = 0
    for line in lines:
        if note_is_birthday_free(line.get("note")):
            total += int(line.get("qty") or 0)
    for note in extra_notes or []:
        if note_is_birthday_free(note):
            total += 1
    return total
