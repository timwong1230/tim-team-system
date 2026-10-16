"""Medical financing calculator — 醫家保 + 盈聚 5yr funding."""

from __future__ import annotations

from tt_core.medical_finance import (
    inflated_medical_schedule,
    load_calibration,
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


def test_k5_age_independent_from_illustrations():
    """All USD10k illustrations (ages 25–50 M/F) share year-5 SV 29727 → k5=2.9727."""
    cal = load_calibration()
    assert abs(cal["k5_sv_per_annual_prem"] - 2.9727) < 1e-6
    checked = 0
    for ill in cal.get("illustrations") or []:
        if ill.get("annual_prem_usd") != 10000 or "year5_sv_usd" not in ill:
            continue
        assert ill["year5_sv_usd"] == 29727
        assert abs(ill["k5"] - 2.9727) < 1e-6
        checked += 1
    assert checked >= 7  # 25M,30M,30F,35M,40M,40F,45M,50M


def test_older_entry_needs_higher_annual_prem():
    young = min_annual_savings_usd(start_age=30, gender="男", inflation=0.0261, end_age=100)
    older = min_annual_savings_usd(start_age=50, gender="男", inflation=0.0261, end_age=100)
    assert older["annual_prem_usd"] > young["annual_prem_usd"]
