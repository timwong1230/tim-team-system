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
    from app.seats import SEATS

    tables = [s for s in SEATS if s["zone"] == "table"]
    bars = [s for s in SEATS if s["zone"] == "bar"]
    terraces = [s for s in SEATS if s["zone"] == "terrace"]
    assert len(tables) == 5
    assert len(bars) == 6
    assert len(terraces) == 9
    assert {s["code"] for s in tables} == {f"TABLE{i}" for i in range(1, 6)}
    assert {s["code"] for s in bars} == {f"BAR{i}" for i in range(1, 7)}
    assert {s["code"] for s in terraces} == {f"TERRACE{i}" for i in range(1, 10)}

    # Display order: Table → Terrace → Bar (demo/boss stay out of guest grid)
    guest = [s for s in SEATS if s["zone"] in ("table", "terrace", "bar")]
    guest_sorted = sorted(guest, key=lambda s: (s["sort"], s["code"]))
    assert [s["code"] for s in guest_sorted] == (
        [f"TABLE{i}" for i in range(1, 6)]
        + [f"TERRACE{i}" for i in range(1, 10)]
        + [f"BAR{i}" for i in range(1, 7)]
    )
    assert guest_sorted[0]["zone"] == "table"
    assert guest_sorted[5]["zone"] == "terrace"
    assert guest_sorted[14]["zone"] == "bar"

    # IDs must stay unique and clear of boss block (31+)
    ids = [_seat_id(s) for s in SEATS]
    assert len(ids) == len(set(ids))
    assert _seat_id({"code": "BAR6", "zone": "bar"}) == 16
    assert _seat_id({"code": "TERRACE9", "zone": "terrace"}) == 29
    assert max(i for i, s in zip(ids, SEATS) if s["zone"] != "boss") < 31
