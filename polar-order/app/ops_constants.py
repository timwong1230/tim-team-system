"""Staff ops labels: payment tenders + nightly claim categories."""

from __future__ import annotations

import os

# Password to reopen a Mark-paid bill for item edits (separate from staff PIN).
BILL_EDIT_PASSWORD: str = (
    os.getenv("POLAR_BILL_EDIT_PASSWORD", "polar2019").strip() or "polar2019"
)

PAYMENT_METHODS: tuple[str, ...] = (
    "Cash",
    "Visa",
    "Mastercard",
    "American Express",
    "AlipayHK",
    "UnionPay",
    "WeChat pay",
    "Deposit",
)

# Boss tabs record Polar credit usage — not a guest tender, never guest sales.
BOSS_CREDIT_METHOD = "Credit"

# WhatsApp nightly close labels → matching payment_method values in DB
WHATSAPP_PAYMENT_LINES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Cash", ("Cash",)),
    ("Visa", ("Visa",)),
    ("Master", ("Mastercard", "Master")),
    ("AE", ("American Express", "AE", "Amex")),
    ("Alipay", ("AlipayHK", "Alipay")),
    ("UnionPay", ("UnionPay",)),
    ("WeChat pay", ("WeChat pay", "WeChat Pay")),
    ("Deposit", ("Deposit",)),
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
