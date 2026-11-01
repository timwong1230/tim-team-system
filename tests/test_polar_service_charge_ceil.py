"""Service charge always rounds UP to a whole dollar."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_POLAR = _ROOT / "polar-order"
if str(_POLAR) not in sys.path:
    sys.path.insert(0, str(_POLAR))

from app.pricing import compute_bill  # noqa: E402


def test_service_charge_rounds_up_to_whole_dollar():
    # Coke $59 + snack $20 = $79 → 10% = 7.9 → ceil $8
    bill = compute_bill(
        [{"category_id": "non-alcohol", "item_id": "coke", "line_total": 59}],
        party_size=2,
        snack_waived=False,
    )
    assert bill["service_charge"] == 8.0
    assert float(bill["service_charge"]).is_integer()
    assert bill["total"] == 59 + 20 + 8

    # Exact tenth: $40 snack only → 10% = $4 (no bump)
    exact = compute_bill([], party_size=4, snack_waived=False)
    assert exact["snack_charge"] == 40.0
    assert exact["service_charge"] == 4.0
    assert exact["total"] == 44.0

    # Tiny fraction still ceilings: $1 product → 0.1 → $1
    tiny = compute_bill(
        [{"category_id": "non-alcohol", "item_id": "x", "line_total": 1}],
        party_size=1,
        snack_waived=True,
    )
    assert tiny["service_charge"] == 1.0
