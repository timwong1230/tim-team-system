"""Customer-offer matching for proposal pages."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tt_core.proposal_offers import find_customer_offer  # noqa: E402


def test_vfamily_q4_three_months():
    offer = find_customer_offer("vfamily", annual_hkd=4917, quarter="Q4")
    assert offer
    assert "子女之家" not in (offer.get("product_label") or "")
    assert "無子女" in (offer.get("product_label") or "")
    assert "3 個月" in offer["detail"]
    assert offer["first_year_hkd"] == 3688


def test_vbooster_deductible_band():
    zero = find_customer_offer("vbooster", deductible=0, annual_hkd=8260, quarter="Q4")
    assert zero and "自付費 0" in zero["detail"]
    assert zero["first_year_hkd"] == 6195  # 8260 * 9/12

    high = find_customer_offer(
        "vbooster", deductible=100000, annual_hkd=5000, quarter="Q4"
    )
    assert high and "≥$100k" in high["detail"]
    assert high["first_year_hkd"] == 2917  # 5000 * 7/12 rounded


def test_gba_op_year2_only_no_first_year_net():
    offer = find_customer_offer("gba_op", annual_hkd=2480, quarter="Q4")
    assert offer
    assert "第 2 年" in offer["detail"]
    assert offer.get("first_year_hkd") is None


def test_zizhubao_percent_discount():
    offer = find_customer_offer("zizhubao_term", annual_hkd=1000, quarter="Q4")
    assert offer
    assert "25%" in offer["detail"]
    assert offer["first_year_hkd"] == 750


def test_life_accident_no_force_match():
    # 人身意外附約唔喺 Q4 客戶優惠表；唔好亂掛全意守護
    assert find_customer_offer("life_accident_rider", annual_hkd=1208, quarter="Q4") is None


def test_allsupporter_q4_100pct_promo():
    offer = find_customer_offer(
        "ci_essential", annual_hkd=30000, pay_term=20, quarter="Q4"
    )
    assert offer
    assert "全應援" in (offer.get("product_label") or "")
    assert "100%" in offer["detail"] or "100％" in offer["detail"]
    assert "第2年20%" in offer["detail"] or "第2年20％" in offer["detail"]
    assert "台北" in offer["detail"]
    assert offer.get("first_year_hkd") is None  # 折扣由第2年起，首年唔減
    assert "20 年供" in (offer.get("first_year_display") or "")
    assert "100%" in (offer.get("first_year_display") or "")


def test_allsupporter_5pay_band():
    offer = find_customer_offer(
        "ci_premier", annual_hkd=40000, pay_term=5, quarter="Q4"
    )
    assert offer and "全應援" in (offer.get("product_label") or "")
    assert "5 年供" in (offer.get("first_year_display") or "")
    assert "10%" in (offer.get("first_year_display") or "")


def test_yingyuan_still_matches_double18_not_allsupporter():
    offer = find_customer_offer("ci_yingyuan", annual_hkd=20000, quarter="Q4")
    assert offer
    assert "應援保" in (offer.get("product_label") or "")
    assert "全應援" not in (offer.get("product_label") or "")
    assert "雙 18" in offer["detail"] or "18%" in offer["detail"]
