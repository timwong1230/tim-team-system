"""Tests for 常見疾病核保 helpers."""

from __future__ import annotations

from tt_core.medical_uw import (
    PRODUCT_LABELS,
    get_disease,
    list_diseases,
    match_scenarios,
    outcome_tone,
    search_diseases,
    summarize_answers,
)


def test_catalog_has_core_diseases():
    ids = {d["id"] for d in list_diseases()}
    assert "anaemia" in ids
    assert "hypertension" in ids
    assert "diabetes" in ids
    assert "fatty_liver" in ids
    assert len(ids) >= 25


def test_search_chinese():
    hits = search_diseases("高血壓")
    assert any(d["id"] == "hypertension" for d in hits)
    hits2 = search_diseases("脂肪肝")
    assert any(d["id"] == "fatty_liver" for d in hits2)


def test_match_anaemia_iron_clear():
    d = get_disease("anaemia")
    assert d is not None
    matched = match_scenarios(
        d,
        {"type": "iron", "years": "gt2", "status": "clear", "complication": "no"},
    )
    assert matched
    assert matched[0]["id"] == "iron_gt2_clear"
    assert matched[0]["outcomes"]["life"] == "標準保費"


def test_match_fallback_returns_all_when_incomplete():
    d = get_disease("asthma")
    assert d is not None
    # Incomplete answers → no auto match → return all scenarios for manual pick
    matched = match_scenarios(d, {"age_group": "adult"})
    assert len(matched) == len(d["scenarios"])
    assert match_scenarios(d, {"age_group": "adult"}, fallback_all=False) == []


def test_outcome_tone_and_summary():
    assert outcome_tone("標準保費") == "good"
    assert outcome_tone("拒絕受保") == "bad"
    assert outcome_tone("延遲受保") == "warn"
    d = get_disease("hypertension")
    rows = summarize_answers(d, {"status": "med_good"})
    assert rows and "控制良好" in rows[0][1]
    assert set(PRODUCT_LABELS) == {"life", "ci", "medical", "accident", "cancer"}
