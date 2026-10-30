"""Polar floor seat map counts."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_POLAR = _ROOT / "polar-order"
if str(_POLAR) not in sys.path:
    sys.path.insert(0, str(_POLAR))


def test_seat_counts_table5_bar6_terrace9():
    from app.db import _seat_id
    from app.seats import SEATS, TABLE_SPLIT_LETTERS, parse_table_split

    tables = [s for s in SEATS if s["zone"] == "table"]
    splits = [s for s in SEATS if s["zone"] == "table_split"]
    bars = [s for s in SEATS if s["zone"] == "bar"]
    terraces = [s for s in SEATS if s["zone"] == "terrace"]
    assert len(tables) == 5
    assert len(splits) == 5 * len(TABLE_SPLIT_LETTERS)
    assert len(bars) == 6
    assert len(terraces) == 9
    assert {s["code"] for s in tables} == {f"TABLE{i}" for i in range(1, 6)}
    assert {s["code"] for s in bars} == {f"BAR{i}" for i in range(1, 7)}
    assert {s["code"] for s in terraces} == {f"TERRACE{i}" for i in range(1, 10)}
    assert {s["code"] for s in splits} == {
        f"TABLE{i}{letter}"
        for i in range(1, 6)
        for letter in TABLE_SPLIT_LETTERS
    }

    # Display order: Table (+splits) → Terrace → Bar
    guest = [
        s
        for s in SEATS
        if s["zone"] in ("table", "table_split", "terrace", "bar")
    ]
    guest_sorted = sorted(guest, key=lambda s: (s["sort"], s["code"]))
    assert guest_sorted[0]["code"] == "TABLE1"
    assert guest_sorted[1]["code"] == "TABLE1A"
    assert any(s["code"] == "TERRACE1" for s in guest_sorted)
    assert guest_sorted[-1]["code"] == "BAR6"
    assert guest_sorted[-1]["sort"] > next(
        s["sort"] for s in guest_sorted if s["code"] == "TERRACE9"
    )

    # IDs unique; splits sit above boss block
    ids = [_seat_id(s) for s in SEATS]
    assert len(ids) == len(set(ids))
    assert _seat_id({"code": "BAR6", "zone": "bar"}) == 16
    assert _seat_id({"code": "TERRACE9", "zone": "terrace"}) == 29
    assert _seat_id({"code": "TABLE1A", "zone": "table_split"}) == 41
    assert _seat_id({"code": "TABLE5D", "zone": "table_split"}) == 60
    assert parse_table_split("TABLE2C") == (2, "C")
    core = [
        i
        for i, s in zip(ids, SEATS)
        if s["zone"] not in ("boss", "table_split")
    ]
    assert max(core) < 31
