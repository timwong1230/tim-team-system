"""收入／支出 T-Account — cashflow budget for savings insurance sales."""

from __future__ import annotations

from typing import Any

INCOME_ITEMS: list[dict[str, str]] = [
    {"id": "work", "label": "工作收入"},
    {"id": "invest", "label": "投資收入"},
    {"id": "other", "label": "其他收入"},
    {"id": "income_extra_1", "label": "其他收入（自訂 1）"},
    {"id": "income_extra_2", "label": "其他收入（自訂 2）"},
]

EXPENSE_ITEMS: list[dict[str, str]] = [
    {"id": "household", "label": "家用"},
    {"id": "personal", "label": "個人開支"},
    {"id": "debt", "label": "負債"},
    {"id": "mpf", "label": "強積金"},
    {"id": "insurance", "label": "保險"},
    {"id": "invest_save", "label": "投資及儲蓄計劃"},
]

PRODUCT_HINTS = (
    "正 Cashflow = 客戶每月理論上可撥入儲蓄／保險的空間。"
    "見客時可建議先預留應急金，再用部分 Cashflow 做儲蓄保險保費。"
)


def _num(v: Any) -> float:
    try:
        if v is None or v == "":
            return 0.0
        return float(v)
    except Exception:
        return 0.0


def sum_items(values: dict[str, Any], items: list[dict[str, str]]) -> float:
    total = 0.0
    for it in items:
        total += _num(values.get(it["id"]))
    return total


def calc_cashflow(values: dict[str, Any]) -> dict[str, float]:
    income = sum_items(values, INCOME_ITEMS)
    expense = sum_items(values, EXPENSE_ITEMS)
    cashflow = income - expense
    return {
        "income": round(income, 2),
        "expense": round(expense, 2),
        "cashflow": round(cashflow, 2),
    }


def format_hkd(amount: float) -> str:
    sign = "-" if amount < 0 else ""
    return f"{sign}${abs(amount):,.0f}"


def budget_suggestion(cashflow: float) -> str:
    """Plain-language hint for savings-insurance premium budget."""
    if cashflow <= 0:
        return "而家 Cashflow ≤ 0，建議先整理開支／增加收入，暫緩加新儲蓄保費。"
    conservative = round(cashflow * 0.3, -1)  # ~30%, nearest 10
    balanced = round(cashflow * 0.5, -1)
    if conservative < 100:
        conservative = round(cashflow * 0.3, 0)
        balanced = round(cashflow * 0.5, 0)
    return (
        f"可考慮每月儲蓄保險保費 budget 約 {format_hkd(conservative)}"
        f"–{format_hkd(balanced)}（約 Cashflow 的 30–50%；其餘作應急／靈活儲蓄）。"
    )
