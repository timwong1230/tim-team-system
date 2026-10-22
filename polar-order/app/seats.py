"""Polar Lounge seat map + boss stations."""

from __future__ import annotations

# code must be URL-safe and unique
SEATS: list[dict] = [
    # Training seat only — not printed on QR sheets; never share a real table code.
    {"code": "DEMO", "label": "Demo (staff practice)", "zone": "demo", "sort": 0},
    # Floor map: 5 tables · 6 bar chairs · 9 terrace chairs
    *[
        {"code": f"TABLE{i}", "label": f"Table {i}", "zone": "table", "sort": i}
        for i in range(1, 6)
    ],
    *[
        {"code": f"BAR{i}", "label": f"Bar {i}", "zone": "bar", "sort": 100 + i}
        for i in range(1, 7)
    ],
    *[
        {
            "code": f"TERRACE{i}",
            "label": f"Terrace {i}",
            "zone": "terrace",
            "sort": 200 + i,
        }
        for i in range(1, 10)
    ],
]

BOSSES = [
    {"id": "jon", "name": "Jon"},
    {"id": "barry", "name": "Barry"},
    {"id": "tim", "name": "Tim"},
    {"id": "ziv", "name": "Ziv"},
]

# Dedicated order tabs — not guest seats, excluded from sales reports
for i, b in enumerate(BOSSES):
    SEATS.append(
        {
            "code": f"BOSS{b['id'].upper()}",
            "label": f"Boss · {b['name']}",
            "zone": "boss",
            "sort": 900 + i,
            "boss_id": b["id"],
        }
    )


def boss_by_id(boss_id: str) -> dict | None:
    for b in BOSSES:
        if b["id"] == boss_id.lower():
            return b
    return None


def boss_seat_code(boss_id: str) -> str | None:
    b = boss_by_id(boss_id)
    if not b:
        return None
    return f"BOSS{b['id'].upper()}"


def is_boss_name(name: str | None) -> bool:
    if not name:
        return False
    return name.strip().lower() in {b["name"].lower() for b in BOSSES}
