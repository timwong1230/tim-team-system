"""FWD commission rates for 準客戶名單 FYC calculator.

Hot-selling products mirror the team's Client List Excel (Year-1 %).
QSB: once colleague YTD FYC ≥ $88,000, 危疾 / 5年供 Saving / 扣稅年金
get +10% FYC (rate × 1.1).
"""

from __future__ import annotations

from typing import Any

from tt_core.constants import Q1_TARGET

# QSB threshold = first-season / YTD gate used by the team ($88,000)
QSB_THRESHOLD = float(Q1_TARGET)
QSB_BONUS = 1.10

# Hot-selling products shown in the form (Excel columns).
# qsb=True → eligible for +10% after YTD ≥ QSB_THRESHOLD
PRODUCT_CATALOG: list[dict[str, Any]] = [
    # 醫療（熱賣；唔享 QSB）
    {"key": "vfamily", "label": "醫家保", "group": "醫療", "rate": 0.27, "qsb": False},
    {"key": "vprime", "label": "尊衛你", "group": "醫療", "rate": 0.25, "qsb": False},
    {"key": "ebeyond", "label": "智員善", "group": "醫療", "rate": 0.25, "qsb": False},
    # 危疾應援保 / 全應援（QSB）
    {"key": "crisis_20", "label": "危疾應援保 20pay", "group": "危疾應援保/全應援", "rate": 0.50, "qsb": True},
    {"key": "crisis_25", "label": "危疾應援保 25pay", "group": "危疾應援保/全應援", "rate": 0.52, "qsb": True},
    {"key": "crisis_30", "label": "危疾應援保 30pay", "group": "危疾應援保/全應援", "rate": 0.53, "qsb": True},
    # Saving
    {"key": "icon_1", "label": "智盈匯聚/超凡 1pay", "group": "Saving", "rate": 0.03, "qsb": False},
    {"key": "maxfocus_2", "label": "盈聚天下II 2pay", "group": "Saving", "rate": 0.07, "qsb": False},
    {"key": "maxfocus_3", "label": "盈聚天下II 3pay", "group": "Saving", "rate": 0.11, "qsb": False},
    # 5年供 Saving — QSB
    {"key": "maxfocus_5", "label": "盈聚天下II 5pay", "group": "Saving", "rate": 0.275, "qsb": True},
    # 扣稅年金（QSB）
    {"key": "annuity_5", "label": "扣稅年金 5pay", "group": "扣稅年金", "rate": 0.17, "qsb": True},
    {"key": "annuity_10", "label": "扣稅年金 10pay", "group": "扣稅年金", "rate": 0.30, "qsb": True},
    # 定期人壽+意外附約（唔享 QSB）
    {"key": "term_5", "label": "定期人壽+意外 5-yr", "group": "定期人壽+意外附約", "rate": 0.30, "qsb": False},
    {"key": "term_10", "label": "定期人壽+意外 10-yr", "group": "定期人壽+意外附約", "rate": 0.35, "qsb": False},
    {"key": "term_20", "label": "定期人壽+意外 20-yr", "group": "定期人壽+意外附約", "rate": 0.40, "qsb": False},
]

PRODUCT_BY_KEY = {p["key"]: p for p in PRODUCT_CATALOG}
QSB_ELIGIBLE_KEYS = {p["key"] for p in PRODUCT_CATALOG if p.get("qsb")}

PRODUCT_GROUPS: list[str] = []
_seen: set[str] = set()
for p in PRODUCT_CATALOG:
    if p["group"] not in _seen:
        PRODUCT_GROUPS.append(p["group"])
        _seen.add(p["group"])


def qsb_active(ytd_fyc: float, *, threshold: float = QSB_THRESHOLD) -> bool:
    try:
        return float(ytd_fyc or 0) >= float(threshold)
    except (TypeError, ValueError):
        return False


def rate_for(key: str, *, ytd_fyc: float = 0.0) -> float:
    p = PRODUCT_BY_KEY.get(key)
    if not p:
        return 0.0
    rate = float(p["rate"])
    if p.get("qsb") and qsb_active(ytd_fyc):
        rate *= QSB_BONUS
    return rate


def label_for(key: str) -> str:
    p = PRODUCT_BY_KEY.get(key)
    return str(p["label"]) if p else key


def normalize_premiums(raw: dict | None) -> dict[str, float]:
    out: dict[str, float] = {}
    if not raw:
        return out
    for key, amt in raw.items():
        k = str(key)
        if k.startswith("_"):
            continue
        if k not in PRODUCT_BY_KEY:
            continue
        try:
            v = float(amt or 0)
        except (TypeError, ValueError):
            v = 0.0
        if v > 0:
            out[k] = v
    return out


def normalize_others(raw: list | None) -> list[dict[str, Any]]:
    """Other products: [{name, premium, rate}] — rate is Year-1 decimal (e.g. 0.25)."""
    out: list[dict[str, Any]] = []
    if not raw:
        return out
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        try:
            premium = float(item.get("premium") or 0)
        except (TypeError, ValueError):
            premium = 0.0
        try:
            rate = float(item.get("rate") or 0)
        except (TypeError, ValueError):
            rate = 0.0
        # Allow rate entered as percent (e.g. 25) or decimal (0.25)
        if rate > 1.0:
            rate = rate / 100.0
        if not name or premium <= 0 or rate <= 0:
            continue
        out.append({"name": name, "premium": premium, "rate": rate})
    return out


def calc_fyc(
    premiums: dict[str, float] | None,
    *,
    others: list[dict] | None = None,
    ytd_fyc: float = 0.0,
) -> float:
    """FYC = Σ (premium × effective Year-1 %). Applies QSB ×1.1 when eligible."""
    total = 0.0
    for key, amt in (premiums or {}).items():
        try:
            premium = float(amt or 0)
        except (TypeError, ValueError):
            premium = 0.0
        if premium <= 0:
            continue
        total += premium * rate_for(str(key), ytd_fyc=ytd_fyc)
    for item in normalize_others(others):
        total += float(item["premium"]) * float(item["rate"])
    return round(total, 2)


def products_summary(
    premiums: dict[str, float] | None,
    *,
    others: list[dict] | None = None,
    ytd_fyc: float = 0.0,
) -> str:
    parts: list[str] = []
    active = qsb_active(ytd_fyc)
    for p in PRODUCT_CATALOG:
        try:
            amt = float((premiums or {}).get(p["key"]) or 0)
        except (TypeError, ValueError):
            amt = 0.0
        if amt > 0:
            tag = " ·Extra 10" if (active and p.get("qsb")) else ""
            parts.append(f"{p['label']} ${amt:,.0f}{tag}")
    for item in normalize_others(others):
        parts.append(
            f"其他:{item['name']} ${item['premium']:,.0f}"
            f"（{item['rate']*100:g}%）"
        )
    return " · ".join(parts)


def fyc_breakdown(
    premiums: dict[str, float] | None,
    *,
    others: list[dict] | None = None,
    ytd_fyc: float = 0.0,
) -> list[dict[str, Any]]:
    """Per-line FYC for UI display."""
    rows: list[dict[str, Any]] = []
    active = qsb_active(ytd_fyc)
    for p in PRODUCT_CATALOG:
        try:
            amt = float((premiums or {}).get(p["key"]) or 0)
        except (TypeError, ValueError):
            amt = 0.0
        if amt <= 0:
            continue
        eff = rate_for(p["key"], ytd_fyc=ytd_fyc)
        rows.append(
            {
                "label": p["label"],
                "premium": amt,
                "base_rate": float(p["rate"]),
                "eff_rate": eff,
                "fyc": round(amt * eff, 2),
                "qsb": bool(active and p.get("qsb")),
            }
        )
    for item in normalize_others(others):
        rows.append(
            {
                "label": f"其他 · {item['name']}",
                "premium": float(item["premium"]),
                "base_rate": float(item["rate"]),
                "eff_rate": float(item["rate"]),
                "fyc": round(float(item["premium"]) * float(item["rate"]), 2),
                "qsb": False,
            }
        )
    return rows
