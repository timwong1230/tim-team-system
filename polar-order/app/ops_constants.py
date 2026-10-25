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
    "Deposit",
)

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
