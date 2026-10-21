"""Medical financing calculator — 醫家保 + 盈聚 5yr funding."""

from __future__ import annotations

from tt_core.medical_finance import (
    MIN_ANNUAL_SAVINGS_USD,
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
    assert low["annual_prem_usd"] >= MIN_ANNUAL_SAVINGS_USD
    assert high["annual_prem_usd"] >= MIN_ANNUAL_SAVINGS_USD


def test_company_min_annual_premium_floor():
    """盈聚 5年供 company minimum is US$4,000 / year."""
    assert MIN_ANNUAL_SAVINGS_USD == 4_000
    # Low medical / short horizon → funding need under floor → must lift to US$4k
    low = min_annual_savings_usd(
        start_age=30, gender="男", inflation=0.0, end_age=50, fx=7.85, plan_id="vfamily"
    )
    assert low["annual_prem_usd"] == 4_000
    assert low.get("floor_applied") is True
    assert low.get("funding_prem_usd", 0) < 4_000
    assert low["annual_prem_hkd"] == round(4_000 * 7.85, 0)
    # High-need case may exceed floor without forcing
    rich = min_annual_savings_usd(
        start_age=30,
        gender="男",
        inflation=0.05,
        end_age=100,
        fx=7.85,
        plan_id="vtheone",
        level="優等",
        deductible=0,
    )
    assert rich["annual_prem_usd"] >= 4_000


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


def test_new_medical_plans_loaded():
    from tt_core.medical_finance import list_plans, medical_annual_hkd, plan_label

    ids = {p["id"] for p in list_plans()}
    assert ids >= {"vfamily", "vprime", "vbooster", "vtheone", "veasy", "gba_op"}
    assert medical_annual_hkd(30, "男", plan_id="veasy", level="標準") == 5745
    assert medical_annual_hkd(30, "女", plan_id="veasy", level="標準") == 7552
    assert medical_annual_hkd(30, "男", plan_id="veasy", level="特等") == 10707
    # 尊衛您 標準 age30 ded0 = 12058 from brochure
    assert medical_annual_hkd(30, "男", plan_id="vprime", level="標準", deductible=0) == 12058
    assert medical_annual_hkd(30, "女", plan_id="vprime", level="標準", deductible=0) == 12058  # unisex
    assert medical_annual_hkd(30, "男", plan_id="vbooster", deductible=0) == 8260
    assert medical_annual_hkd(30, "男", plan_id="vtheone", level="標準", deductible=0) == 19531
    # 大灣區門診：實際年齡 30 → 下次生日 31；1–70 歲段個人計劃
    assert medical_annual_hkd(30, "男", plan_id="gba_op", level="計劃1") == 2480
    assert medical_annual_hkd(30, "女", plan_id="gba_op", level="計劃2") == 5380
    assert medical_annual_hkd(30, "男", plan_id="gba_op", level="計劃3") == 6480
    assert medical_annual_hkd(70, "男", plan_id="gba_op", level="計劃1") == 3050
    assert medical_annual_hkd(30, "男", plan_id="gba_op", level="家庭計劃A") == 4800
    assert medical_annual_hkd(30, "男", plan_id="gba_op", level="家庭計劃B") == 17500
    # 家庭計劃唔適用 1–18 歲（下次生日）；超齡唔好 clamp
    assert medical_annual_hkd(10, "男", plan_id="gba_op", level="家庭計劃A") == 0
    assert medical_annual_hkd(85, "男", plan_id="gba_op", level="計劃1") == 0
    assert "尊衛您" in plan_label("vprime", level="特等", deductible=25000)
    assert "大灣區" in plan_label("gba_op", level="計劃1")


def test_higher_tier_costs_more_to_fund():
    base = min_annual_savings_usd(
        start_age=30, gender="男", inflation=0.0261, end_age=90, plan_id="vfamily"
    )
    richer = min_annual_savings_usd(
        start_age=30,
        gender="男",
        inflation=0.0261,
        end_age=90,
        plan_id="vprime",
        level="特等",
        deductible=0,
    )
    assert richer["annual_prem_usd"] > base["annual_prem_usd"]
    assert "尊衛您" in (richer.get("medical_plan") or "")
