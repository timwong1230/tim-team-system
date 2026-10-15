"""Quarterly customer offers & salesperson rewards.

Content is seeded from team promo documents. Leaders can also override
via the `quarterly_offers` Google Sheet (same columns as OFFER_COLUMNS).
"""

from __future__ import annotations

from datetime import date

# quarter_key -> metadata + default items (filled from uploaded promo docs)
# kind: "customer" = 客戶優惠, "agent" = 營業員獎賞
QUARTERS = {
    "Q1": {
        "label": "第一季",
        "period": "1月 – 3月",
        "months": (1, 2, 3),
    },
    "Q2": {
        "label": "第二季",
        "period": "4月 – 6月",
        "months": (4, 5, 6),
    },
    "Q3": {
        "label": "第三季",
        "period": "7月 – 9月",
        "months": (7, 8, 9),
    },
    "Q4": {
        "label": "第四季",
        "period": "10月 – 12月",
        "months": (10, 11, 12),
    },
}

# Default catalogue — replace/extend when promo PDFs are available.
# Each item: title, detail, note (optional), sort (int)
DEFAULT_OFFERS: dict[str, dict[str, list[dict]]] = {
    "Q1": {"customer": [], "agent": []},
    "Q2": {"customer": [], "agent": []},
    "Q3": {"customer": [], "agent": []},
    "Q4": {"customer": [], "agent": []},
}

OFFER_COLUMNS = [
    "id",
    "quarter",
    "kind",
    "title",
    "detail",
    "note",
    "sort",
    "updated_at",
]


def current_quarter_key(today: date | None = None) -> str:
    d = today or date.today()
    m = d.month
    if m <= 3:
        return "Q1"
    if m <= 6:
        return "Q2"
    if m <= 9:
        return "Q3"
    return "Q4"


def default_items(quarter: str, kind: str) -> list[dict]:
    q = DEFAULT_OFFERS.get(str(quarter).upper(), {})
    items = list(q.get(kind, []) or [])
    return sorted(items, key=lambda x: int(x.get("sort", 0) or 0))
