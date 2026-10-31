"""Free Flow packages do not attract 10% service charge."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_POLAR = _ROOT / "polar-order"
if str(_POLAR) not in sys.path:
    sys.path.insert(0, str(_POLAR))

from app.pricing import compute_bill  # noqa: E402


def test_free_flow_excluded_from_service_charge():
    lines = [
        {
            "category_id": "free-flow",
            "item_id": "free-flow-with-shisha",
            "line_total": 450,
        },
        {
            "category_id": "free-flow",
            "item_id": "free-flow-without-shisha",
            "line_total": 300,
        },
    ]
    bill = compute_bill(lines, party_size=2, snack_waived=True)
    assert bill["subtotal"] == 750.0
    assert bill["serviceable_subtotal"] == 0.0
    assert bill["service_charge"] == 0.0
    assert bill["total"] == 750.0

    mixed = compute_bill(
        lines
        + [
            {
                "category_id": "non-alcohol",
                "item_id": "coke",
                "line_total": 59,
            }
        ],
        party_size=2,
        snack_waived=True,
    )
    assert mixed["subtotal"] == 809.0
    assert mixed["serviceable_subtotal"] == 59.0
    assert mixed["service_charge"] == 5.9
    assert mixed["total"] == 814.9
