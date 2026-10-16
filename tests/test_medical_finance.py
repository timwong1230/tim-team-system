"""Medical financing calculator — 醫家保 + 盈聚 5yr funding."""

from __future__ import annotations

from tt_core.medical_finance import (
    inflated_medical_schedule,
    load_vfamily_premiums,
    medical_annual_hkd,
    min_annual_savings_usd,
    simulate_fund,
    withdrawal_schedule_usd,
)


def test_premium_table_loaded():
    table = load_vfamily_premiums()
    assert 30 in table and 99 in table
    assert medical_annual_hkd(30, "男") == 4917
    assert medical_annual_hkd(30, "女") == 6464


def test_inflation_raises_later_years():
    rows = inflated_medical_schedule(start_age=30, gender="男", inflation=0.05, end_age=40)
    assert rows[0]["premium_hkd"] == 4917
    assert rows[-1]["premium_hkd"] > rows[0]["premium_hkd"]


def test_withdrawals_start_year6():
    wds = withdrawal_schedule_usd(start_age=30, gender="男", inflation=0.0, end_age=40, fx=7.85)
    assert wds[0]["age"] == 35
    assert wds[0]["policy_year"] == 6
    assert wds[-1]["age"] == 40
    # USD = HKD / 7.85
    assert abs(wds[0]["withdraw_usd"] - medical_annual_hkd(35, "男") / 7.85) < 0.1


def test_level_7pct_feasible_like_illustration():
    # Constant withdraw 3500 with P=10000 should survive ~65 years at calibrated g
    wds = [{"withdraw_usd": 3500, "policy_year": 6 + i, "age": 36 + i, "premium_hkd": 0} for i in range(65)]
    sim = simulate_fund(10000, wds)
    assert sim["ok"]
    assert sim["final_av_usd"] > 0


def test_min_savings_positive_and_scales_with_inflation():
    low = min_annual_savings_usd(start_age=30, gender="男", inflation=0.0, end_age=80, fx=7.85)
    high = min_annual_savings_usd(start_age=30, gender="男", inflation=0.05, end_age=80, fx=7.85)
    assert low.get("annual_prem_usd", 0) > 0
    assert high["annual_prem_usd"] >= low["annual_prem_usd"]
    assert low["annual_prem_hkd"] == round(low["annual_prem_usd"] * 7.85, 0)
