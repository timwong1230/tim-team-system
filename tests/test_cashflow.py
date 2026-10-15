"""Tests for 收入／支出 T-Account cashflow helpers."""

from __future__ import annotations

from tt_core.cashflow import (
    EXPENSE_ITEMS,
    INCOME_ITEMS,
    budget_suggestion,
    calc_cashflow,
    format_hkd,
)


def test_item_labels_match_taccount():
    income_labels = [i["label"] for i in INCOME_ITEMS]
    assert "工作收入" in income_labels
    assert "投資收入" in income_labels
    assert "其他收入" in income_labels
    expense_labels = [i["label"] for i in EXPENSE_ITEMS]
    assert expense_labels == [
        "家用",
        "個人開支",
        "負債",
        "強積金",
        "保險",
        "投資及儲蓄計劃",
    ]


def test_calc_cashflow():
    values = {
        "work": 30000,
        "invest": 2000,
        "other": 0,
        "household": 10000,
        "personal": 5000,
        "debt": 3000,
        "mpf": 1500,
        "insurance": 2000,
        "invest_save": 1000,
    }
    r = calc_cashflow(values)
    assert r["income"] == 32000
    assert r["expense"] == 22500
    assert r["cashflow"] == 9500


def test_format_and_budget_hint():
    assert format_hkd(12345) == "$12,345"
    assert format_hkd(-500) == "-$500"
    assert "暫緩" in budget_suggestion(0)
    assert "budget" in budget_suggestion(10000).lower() or "Budget" in budget_suggestion(10000) or "保費" in budget_suggestion(10000)
