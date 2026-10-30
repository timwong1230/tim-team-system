"""Polar Lounge seat map + boss stations."""

from __future__ import annotations

import re

# Letters staff can use when one physical table hosts multiple parties.
TABLE_SPLIT_LETTERS = ("A", "B", "C", "D")

# code must be URL-safe and unique
SEATS: list[dict] = [
    # Training seat only — not printed on QR sheets; never share a real table code.
    {"code": "DEMO", "label": "Demo (staff practice)", "zone": "demo", "sort": 0},
]

# Floor map order: Table 1–5 (with 1A–1D splits) → Terrace 1–9 → Bar 1–6
for i in range(1, 6):
    SEATS.append(
        {
            "code": f"TABLE{i}",
            "label": f"Table {i}",
            "zone": "table",
            "sort": i * 10,
        }
    )
    for li, letter in enumerate(TABLE_SPLIT_LETTERS):
        SEATS.append(
            {
                "code": f"TABLE{i}{letter}",
                "label": f"Table {i}{letter}",
                "zone": "table_split",
                "parent_code": f"TABLE{i}",
                "sort": i * 10 + li + 1,
            }
        )

SEATS.extend(
    {
        "code": f"TERRACE{i}",
        "label": f"Terrace {i}",
        "zone": "terrace",
        "sort": 100 + i,
    }
    for i in range(1, 10)
)
SEATS.extend(
    {"code": f"BAR{i}", "label": f"Bar {i}", "zone": "bar", "sort": 200 + i}
    for i in range(1, 7)
)

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


def parse_table_split(code: str) -> tuple[int, str] | None:
    """Return (table_num, letter) for TABLE1A…TABLE5D, else None."""
    m = re.fullmatch(r"TABLE([1-5])([A-D])", (code or "").upper())
    if not m:
        return None
    return int(m.group(1)), m.group(2)


def parent_table_code(code: str) -> str | None:
    """Physical parent for a split seat, e.g. TABLE1A → TABLE1."""
    parsed = parse_table_split(code)
    if not parsed:
        return None
    return f"TABLE{parsed[0]}"


def next_split_letter(used_letters: set[str]) -> str | None:
    for letter in TABLE_SPLIT_LETTERS:
        if letter.upper() not in {x.upper() for x in used_letters}:
            return letter
    return None
