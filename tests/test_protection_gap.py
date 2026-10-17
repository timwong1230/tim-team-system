"""Tests for 保障缺口 helpers."""

from __future__ import annotations

from tt_core.protection_gap import (
    CORE_PILLARS,
    POLICY_TYPES,
    aggregate,
    classify_pillar,
    completeness_summary,
    gap_table,
    html_gap_detail_cards,
    html_pillar_gap_bars,
    normalize_rows,
    pie_current_cover,
    pie_gap_vs_covered,
    pillar_status,
    suggested_targets,
    svg_pillar_status_pie,
    total_monthly_premium,
)


def test_policy_types():
    assert "人壽保險" in POLICY_TYPES
    assert "危疾保險" in POLICY_TYPES
    assert "醫療保險" in POLICY_TYPES
    assert "意外保險" in POLICY_TYPES
    assert CORE_PILLARS == ["人壽保險", "危疾保險", "醫療保險", "意外保險"]


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


def test_classify_pillar():
    assert classify_pillar(0, 1_000_000) == "missing"
    assert classify_pillar(1_000_000, 1_000_000) == "ok"
    assert classify_pillar(900_000, 1_000_000) == "ok"  # >= 80%
    assert classify_pillar(500_000, 1_000_000) == "short"


def test_pillar_status_always_four_and_missing_visible():
    """Only life cover → medical / CI / accident stay visible as missing."""
    rows = normalize_rows(
        [{"保單類型": "人壽保險", "保險公司": "FWD", "保額": 1_000_000, "保費": 800}]
    )
    targets = {
        "人壽保險": 11_200_000,
        "危疾保險": 2_000_000,
        "醫療保險": 1_000_000,
        "意外保險": 1_000_000,
        "其他": 0,
    }
    gaps = gap_table(rows, targets)
    pillars = pillar_status(gaps)
    assert len(pillars) == 4
    assert [p["保單類型"] for p in pillars] == CORE_PILLARS
    by = {p["保單類型"]: p for p in pillars}
    assert by["人壽保險"]["status"] == "short"
    assert by["危疾保險"]["status"] == "missing"
    assert by["醫療保險"]["status"] == "missing"
    assert by["意外保險"]["status"] == "missing"
    assert all(p["weight"] == 1.0 for p in pillars)

    summary = completeness_summary(pillars)
    assert summary["missing"] == 3
    assert summary["short"] == 1
    assert summary["ready"] == 0
    assert "危疾" in summary["missing_names"]

    svg = svg_pillar_status_pie(pillars)
    assert "危疾" in svg and "醫療" in svg and "意外" in svg
    assert "#DC2626" in svg  # missing red
    bars = html_pillar_gap_bars(pillars)
    assert "人壽" in bars and "未做／缺口" in bars

    cards = html_gap_detail_cards(gaps)
    assert "人壽保險" in cards and "危疾保險" in cards
    assert "$1,000,000" in cards
    assert "已有" in cards and "建議" in cards and "缺口" in cards
    assert "tt-gap-detail-cards" in cards
    assert "#DC2626" in cards  # missing status accent
