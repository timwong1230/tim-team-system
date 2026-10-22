"""Staff ops labels: payment tenders + nightly claim categories."""

from __future__ import annotations

PAYMENT_METHODS: tuple[str, ...] = (
    "Cash",
    "Visa",
    "Mastercard",
    "American Express",
    "AlipayHK",
    "UnionPay",
    "WeChat pay",
)

CLAIM_PRESETS: tuple[str, ...] = (
    "Staff Meal",
    "Ice",
    "Fruits",
    "Groceries",
    "Food",
    "Beer",
    "Delivery Fee",
)
