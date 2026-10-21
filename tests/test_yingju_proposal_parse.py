"""Parse official FWD Yingju II illustration PDFs."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tt_core.yingju_proposal_parse import (  # noqa: E402
    focus_rows_from_illustration,
    parse_yingju_illustration_pdf,
    scenario_from_illustration,
)
from tt_core.yingju_angles import build_angle_story  # noqa: E402
from tt_core.proposal import build_saving_proposal, html_preview  # noqa: E402
from tt_core.proposal_pdf import build_proposal_pdf  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures" / "yingju"


def test_parse_base_breakeven_year6():
    parsed = parse_yingju_illustration_pdf(FIXTURES / "yingju_12800_age31.pdf")
    assert parsed["annual_usd"] == 12800.0
    assert parsed["meta"]["age"] == 31
    assert parsed["year6_sv_usd"] == 64000.0
    assert parsed["year6_total_prem_usd"] == 64000.0
    assert parsed["year5_sv_usd"] == 38051.0
    assert len(parsed["base_rows"]) >= 20
    # 第 6 年 = 已繳總保費（breakeven）
    assert parsed["year6_sv_usd"] == parsed["annual_usd"] * 5


def test_parse_withdrawal_from_year6():
    parsed = parse_yingju_illustration_pdf(FIXTURES / "yingju_7700_wd_y6.pdf")
    assert parsed["annual_usd"] == 7700.0
    assert parsed["has_withdrawal_scenario"] is True
    assert parsed["withdraw_start_year"] == 6
    assert parsed["withdraw_usd"] == 2695.0
    # base 第 6 年仍係未提款 SV（= 總保費）
    assert parsed["year6_sv_usd"] == 38500.0
    wd6 = next(r for r in parsed["withdrawal_rows"] if r["policy_year"] == 6)
    assert wd6["withdraw_usd"] == 2695.0
    assert wd6["sv_usd"] == 35805.0


def test_parse_education_withdrawal():
    parsed = parse_yingju_illustration_pdf(FIXTURES / "yingju_7700_edu.pdf")
    assert parsed["meta"]["age"] == 1
    assert parsed["withdraw_start_year"] == 18
    assert parsed["withdraw_usd"] == 12800.0
    assert parsed["withdraw_years"] == 4
    focus = focus_rows_from_illustration(parsed)
    years = {r["policy_year"] for r in focus}
    assert 6 in years and 18 in years
    y6 = next(r for r in focus if r["policy_year"] == 6)
    assert y6["av_end_usd"] == 38500.0
    assert y6["withdraw_usd"] == 0.0


def test_proposal_uses_official_numbers_only():
    parsed = parse_yingju_illustration_pdf(FIXTURES / "yingju_7700_edu.pdf")
    prop = build_saving_proposal(
        client_name="BB",
        age=30,  # form age ignored when PDF has age
        gender="女",
        occupation="Child",
        saving_id="yingju5",
        annual_usd=99999,  # ignored
        purpose="教育基金",
        illustration=parsed,
    )
    assert prop["ready"] is True
    assert prop["gaps"] == []
    assert prop["client"]["age"] == 1
    assert prop["client"]["gender"] == "男"
    sec = prop["sections"][0]
    assert sec["illustration"]["source"] == "official_illustration"
    assert sec["illustration"]["year6_sv_usd"] == 38500.0
    assert "官方利益說明" in str(sec["visual"]["cards"])
    assert "示意" not in str(sec["visual"]["cards"]) or "官方" in sec["angle_disclaimer"]
    html = html_preview(prop)
    assert "38500" in html.replace(",", "") or "38,500" in html
    assert "US$7,700" in html or "7700" in html.replace(",", "")
    pdf = build_proposal_pdf(prop, agent="Tim")
    assert pdf[:4] == b"%PDF"


def test_yingju_requires_illustration():
    prop = build_saving_proposal(
        client_name="X",
        age=30,
        gender="男",
        saving_id="yingju5",
        annual_usd=10000,
        purpose="儲蓄錢包",
    )
    assert prop["ready"] is False
    assert any("官方" in g for g in prop["gaps"])


def test_angle_story_from_illustration():
    parsed = parse_yingju_illustration_pdf(FIXTURES / "yingju_12800_age31.pdf")
    story = build_angle_story(
        "退休儲備",
        annual_usd=12800,
        age=31,
        illustration=parsed,
    )
    assert story["metrics"]["source"] == "official_illustration"
    assert story["metrics"]["year6_sv_usd"] == 64000.0
    assert story["metrics"]["withdraw_usd"] == 30000.0
    scen = scenario_from_illustration(parsed)
    assert scen["breakeven_prem_usd"] == 64000.0
