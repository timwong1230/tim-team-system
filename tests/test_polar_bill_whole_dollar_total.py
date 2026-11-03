"""Amount due is always a whole HKD so Visa settlement matches reports."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_POLAR = _ROOT / "polar-order"
if str(_POLAR) not in sys.path:
    sys.path.insert(0, str(_POLAR))

from app.pricing import compute_bill, round_hkd_whole  # noqa: E402


def test_round_hkd_whole_half_up_matches_js_math_round():
    assert round_hkd_whole(71.4) == 71.0
    assert round_hkd_whole(71.5) == 72.0
    assert round_hkd_whole(71.6) == 72.0
    assert round_hkd_whole(0) == 0.0
    assert round_hkd_whole(-1) == 0.0


def test_amount_due_whole_dollar_with_promo_tenths():
    # Happy Hour: $68 drink → $54.4 + snack $10 → service ceil(6.44)=7
    # raw total 71.4 → charge / store $71 (what bill UI Math.round shows)
    bill = compute_bill(
        [{"category_id": "drinks", "item_id": "x", "line_total": 54.4}],
        party_size=1,
        snack_waived=False,
    )
    assert bill["subtotal"] == 54.4
    assert bill["snack_charge"] == 10.0
    assert bill["service_charge"] == 7.0
    assert bill["total"] == 71.0
    assert float(bill["total"]).is_integer()

    # .6 tenths round up — Meditation-style leftover
    bill2 = compute_bill(
        [{"category_id": "drinks", "item_id": "y", "line_total": 47.6}],
        party_size=1,
        snack_waived=False,
    )
    # 47.6 + 10 + ceil(5.76)=6 → 63.6 → $64
    assert bill2["total"] == 64.0


def test_visa_night_sum_matches_whole_dollar_charges():
    """Report Visa column = sum of stored totals = sum of terminal charges."""
    bills = [
        compute_bill(
            [{"category_id": "drinks", "item_id": "a", "line_total": 54.4}],
            party_size=2,
            snack_waived=False,
        ),
        compute_bill(
            [{"category_id": "drinks", "item_id": "b", "line_total": 62.4}],
            party_size=1,
            snack_waived=False,
        ),
        compute_bill(
            [{"category_id": "drinks", "item_id": "c", "line_total": 47.6}],
            party_size=3,
            snack_waived=False,
        ),
    ]
    stored = sum(b["total"] for b in bills)
    assert stored == int(stored)
    assert all(float(b["total"]).is_integer() for b in bills)
