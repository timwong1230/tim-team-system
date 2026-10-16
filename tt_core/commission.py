"""FWD commission rates for 準客戶名單 FYC calculator.

Rates mirror the team's Client List Excel (Year-1 %) and align with
Commission Schedule v5.7 Aug 2026 for the products used in that sheet.
"""

from __future__ import annotations

from typing import Any

# key → (label, group, year1_rate)
# Groups match Excel header categories.
PRODUCT_CATALOG: list[dict[str, Any]] = [
    # 醫療
    {"key": "vfamily", "label": "醫家保", "group": "醫療", "rate": 0.27},
    {"key": "vprime", "label": "尊衛你", "group": "醫療", "rate": 0.25},
    {"key": "ebeyond", "label": "智員善", "group": "醫療", "rate": 0.25},
    # 危疾應援保 / 全應援
    {"key": "crisis_20", "label": "危疾應援保 20pay", "group": "危疾應援保/全應援", "rate": 0.50},
    {"key": "crisis_25", "label": "危疾應援保 25pay", "group": "危疾應援保/全應援", "rate": 0.52},
    {"key": "crisis_30", "label": "危疾應援保 30pay", "group": "危疾應援保/全應援", "rate": 0.53},
    # Saving
    {"key": "icon_1", "label": "智盈匯聚/超凡 1pay", "group": "Saving", "rate": 0.03},
    {"key": "maxfocus_2", "label": "盈聚天下II 2pay", "group": "Saving", "rate": 0.07},
    {"key": "maxfocus_3", "label": "盈聚天下II 3pay", "group": "Saving", "rate": 0.11},
    {"key": "maxfocus_5", "label": "盈聚天下II 5pay", "group": "Saving", "rate": 0.275},
    # 扣稅年金
    {"key": "annuity_5", "label": "扣稅年金 5pay", "group": "扣稅年金", "rate": 0.17},
    {"key": "annuity_10", "label": "扣稅年金 10pay", "group": "扣稅年金", "rate": 0.30},
    # 定期人壽+意外附約
    {"key": "term_5", "label": "定期人壽+意外 5-yr", "group": "定期人壽+意外附約", "rate": 0.30},
    {"key": "term_10", "label": "定期人壽+意外 10-yr", "group": "定期人壽+意外附約", "rate": 0.35},
    {"key": "term_20", "label": "定期人壽+意外 20-yr", "group": "定期人壽+意外附約", "rate": 0.40},
]

PRODUCT_BY_KEY = {p["key"]: p for p in PRODUCT_CATALOG}
PRODUCT_GROUPS = []
_seen = set()
for p in PRODUCT_CATALOG:
    if p["group"] not in _seen:
        PRODUCT_GROUPS.append(p["group"])
        _seen.add(p["group"])


def rate_for(key: str) -> float:
    p = PRODUCT_BY_KEY.get(key)
    return float(p["rate"]) if p else 0.0


def label_for(key: str) -> str:
    p = PRODUCT_BY_KEY.get(key)
    return str(p["label"]) if p else key


def calc_fyc(premiums: dict[str, float] | None) -> float:
    """FYC = Σ (annual premium × Year-1 commission %)."""
    total = 0.0
    if not premiums:
        return 0.0
    for key, amt in premiums.items():
        try:
            premium = float(amt or 0)
        except (TypeError, ValueError):
            premium = 0.0
        if premium <= 0:
            continue
        total += premium * rate_for(str(key))
    return round(total, 2)


def products_summary(premiums: dict[str, float] | None) -> str:
    """Human-readable product list for display."""
    if not premiums:
        return ""
    parts = []
    for p in PRODUCT_CATALOG:
        try:
            amt = float(premiums.get(p["key"]) or 0)
        except (TypeError, ValueError):
            amt = 0.0
        if amt > 0:
            parts.append(f"{p['label']} ${amt:,.0f}")
    return " · ".join(parts)


def normalize_premiums(raw: dict | None) -> dict[str, float]:
    out: dict[str, float] = {}
    if not raw:
        return out
    for key, amt in raw.items():
        k = str(key)
        if k not in PRODUCT_BY_KEY:
            continue
        try:
            v = float(amt or 0)
        except (TypeError, ValueError):
            v = 0.0
        if v > 0:
            out[k] = v
    return out
