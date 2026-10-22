"""Polar Lounge seat map."""

from __future__ import annotations

# code must be URL-safe and unique
SEATS: list[dict] = [
    *[
        {"code": f"TABLE{i}", "label": f"Table {i}", "zone": "table", "sort": i}
        for i in range(1, 6)
    ],
    *[
        {"code": f"BAR{i}", "label": f"Bar {i}", "zone": "bar", "sort": 100 + i}
        for i in range(1, 6)
    ],
    *[
        {
            "code": f"TERRACE{i}",
            "label": f"Terrace {i}",
            "zone": "terrace",
            "sort": 200 + i,
        }
        for i in range(1, 9)
    ],
]

BOSSES = [
    {"id": "jon", "name": "Jon"},
    {"id": "barry", "name": "Barry"},
    {"id": "tim", "name": "Tim"},
    {"id": "ziv", "name": "Ziv"},
]


def boss_by_id(boss_id: str) -> dict | None:
    for b in BOSSES:
        if b["id"] == boss_id.lower():
            return b
    return None
