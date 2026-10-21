"""Yingju II 5-pay selling-angle stories."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tt_core.yingju_angles import (  # noqa: E402
    SELLING_ANGLES,
    build_angle_story,
    project_scenario,
)
from tt_core.proposal import build_saving_proposal, html_preview  # noqa: E402
from tt_core.proposal_pdf import build_proposal_pdf  # noqa: E402


def test_four_angles_and_year6_projection():
    assert SELLING_ANGLES == ["儲蓄錢包", "教育基金", "退休儲備", "醫療融資"]
    scen = project_scenario(20000, age=2, withdraw_start_year=16, withdraw_years=4)
    assert scen["year5_sv_usd"] == 59454
    assert scen["year6_sv_usd"] == round(59454 * 1.1189, 0)
    assert scen["withdraw_usd"] == 7000
    assert scen["av_after_withdrawals_usd"] is not None
    assert scen["av_after_withdrawals_usd"] > 0

    edu = build_angle_story(
        "教育基金",
        annual_usd=20000,
        age=2,
        withdraw_start_year=16,
        withdraw_years=4,
        withdraw_usd=7000,
    )
    assert edu["title"] == "教育基金計劃書"
    assert edu["tagline"] == "子女教育金規劃方案"
    assert "着落" not in edu["tagline"]
    assert "開始儲" not in edu["tagline"]
    assert "Yr5" not in str(edu["visual"]["cards"])
    assert any("第 6 年" in str(c.get("label")) for c in edu["visual"]["cards"])
    assert edu["visual"]["value_table"]


def test_proposal_no_summary_and_tc():
    prop = build_saving_proposal(
        client_name="BB",
        age=2,
        gender="男",
        occupation="Child",
        saving_id="yingju5",
        annual_usd=20000,
        purpose="教育基金",
        withdraw_start_year=16,
        withdraw_years=4,
        withdraw_usd=7000,
    )
    assert prop["skip_summary"] is True
    assert prop["summary_rows"] == []
    assert prop["title"] == "教育基金計劃書"
    html = html_preview(prop)
    assert "SUMMARY" not in html
    assert "着落" not in html
    assert "保险公司" not in html
    assert "保險公司" in html
    assert "第 6 年" in html
    assert "期末戶口" in html
    pdf = build_proposal_pdf(prop, agent="Tim")
    assert pdf[:4] == b"%PDF"
    # Saving proposal should be cover + section pages, no dedicated summary
    import fitz

    doc = fitz.open(stream=pdf, filetype="pdf")
    texts = "\n".join(p.get_text() for p in doc)
    assert "SUMMARY" not in texts
    assert "子女教育金規劃方案" in texts
    assert "保险公司" not in texts
