"""Tests for 保障缺口 helpers."""

from __future__ import annotations

from tt_core.protection_gap import (
    POLICY_TYPES,
    aggregate,
    gap_table,
    normalize_rows,
    pie_current_cover,
    pie_gap_vs_covered,
    suggested_targets,
    total_monthly_premium,
)


def test_policy_types():
    assert "人壽保險" in POLICY_TYPES
    assert "危疾保險" in POLICY_TYPES
    assert "醫療保險" in POLICY_TYPES
    assert "意外保險" in POLICY_TYPES


def test_suggested_targets_from_income():
    t = suggested_targets(50_000)  # 600k annual
    assert t["人壽保險"] == 6_000_000  # 10x
    assert t["危疾保險"] == 2_400_000  # 4x
    assert t["意外保險"] == 1_800_000  # 3x
    assert t["醫療保險"] == 1_000_000


def test_gap_and_pies():
    rows = normalize_rows(
        [
            {"保單類型": "人壽保險", "保險公司": "FWD", "保額": 1_000_000, "保費": 800},
            {"保單類型": "危疾保險", "保險公司": "AIA", "保額": 500_000, "保費": 600},
            {"保單類型": "人壽保險", "保險公司": "", "保額": 0, "保費": 0},  # drop empty
        ]
    )
    assert len(rows) == 2
    assert total_monthly_premium(rows) == 1400
    agg = aggregate(rows)
    assert agg["人壽保險"]["cover"] == 1_000_000
    targets = {"人壽保險": 5_000_000, "危疾保險": 2_000_000, "醫療保險": 1_000_000, "意外保險": 1_000_000, "其他": 0}
    gaps = gap_table(rows, targets)
    life = next(g for g in gaps if g["保單類型"] == "人壽保險")
    assert life["保障缺口"] == 4_000_000
    pie = pie_current_cover(rows)
    assert any(p["類型"] == "人壽保險" for p in pie)
    overview = pie_gap_vs_covered(gaps)
    labels = {p["項目"] for p in overview}
    assert "已有保障" in labels
    assert "保障缺口" in labels
