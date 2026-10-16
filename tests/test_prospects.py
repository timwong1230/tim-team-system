"""Prospect list — sales / recruit quarterly helpers."""

from __future__ import annotations

import pandas as pd

from tt_core.prospects import (
    LIST_RECRUIT,
    LIST_SALES,
    RECRUIT_CATEGORIES,
    factfind_template,
    quarter_counts,
    quarter_fyc_total,
    year_fyc_total,
)


def _sample_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "id": "1",
                "username": "Tim",
                "list_type": LIST_SALES,
                "year": 2026,
                "quarter": 1,
                "name": "A",
                "selling_products": "醫家保",
                "fyc": 10000,
                "recruit_category": "",
                "factfind": "x",
            },
            {
                "id": "2",
                "username": "Tim",
                "list_type": LIST_SALES,
                "year": 2026,
                "quarter": 1,
                "name": "B",
                "selling_products": "盈聚",
                "fyc": 5000,
                "recruit_category": "",
                "factfind": "y",
            },
            {
                "id": "3",
                "username": "Tim",
                "list_type": LIST_SALES,
                "year": 2026,
                "quarter": 2,
                "name": "C",
                "selling_products": "危疾",
                "fyc": 8000,
                "recruit_category": "",
                "factfind": "z",
            },
            {
                "id": "4",
                "username": "Tim",
                "list_type": LIST_RECRUIT,
                "year": 2026,
                "quarter": 1,
                "name": "D",
                "selling_products": "",
                "fyc": 0,
                "recruit_category": "Organic",
                "factfind": "r",
            },
            {
                "id": "5",
                "username": "Tim",
                "list_type": LIST_RECRUIT,
                "year": 2026,
                "quarter": 3,
                "name": "E",
                "selling_products": "",
                "fyc": 0,
                "recruit_category": "MCV",
                "factfind": "r2",
            },
        ]
    )


def test_factfind_has_15_questions():
    t = factfind_template()
    assert "1. 性格" in t
    assert "15." in t


def test_recruit_categories():
    assert RECRUIT_CATEGORIES == ["Organic", "IRP", "MCV"]


def test_fyc_totals():
    df = _sample_df()
    assert quarter_fyc_total(df, 2026, 1) == 15000
    assert quarter_fyc_total(df, 2026, 2) == 8000
    assert year_fyc_total(df, 2026) == 23000


def test_recruit_quarter_counts():
    df = _sample_df()
    counts = quarter_counts(df, 2026, LIST_RECRUIT)
    assert counts[1] == 1
    assert counts[2] == 0
    assert counts[3] == 1
    assert counts[4] == 0
