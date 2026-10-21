"""Yingju II 5-pay selling-angle stories."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tt_core.yingju_angles import SELLING_ANGLES, angle_metrics, build_angle_story  # noqa: E402
from tt_core.proposal import build_saving_proposal, html_preview  # noqa: E402
from tt_core.proposal_pdf import build_proposal_pdf  # noqa: E402


def test_four_angles_and_wallet_numbers():
    assert SELLING_ANGLES == ["儲蓄錢包", "教育基金", "退休儲備", "醫療融資"]
    m = angle_metrics(7700)
    assert m["year5_sv_usd"] == 22890  # 7700 * 2.9727
    assert m["year6_wd_usd"] == 2695  # 7700 * 0.35

    wallet = build_angle_story("儲蓄錢包", annual_usd=7700, age=30)
    assert wallet["title"] == "儲蓄錢包計劃書"
    assert len(wallet["visual"]["steps"]) == 4
    assert "第一桶金" in wallet["visual"]["steps"][1]["title"]
    assert wallet["metrics"]["year6_wd_usd"] == 2695


def test_proposal_differs_by_angle():
    common = dict(
        client_name="BB",
        age=30,
        gender="男",
        saving_id="yingju5",
        annual_usd=7700,
    )
    w = build_saving_proposal(**common, purpose="儲蓄錢包")
    e = build_saving_proposal(**common, purpose="教育基金")
    assert w["title"] != e["title"]
    assert w["sections"][0]["category"] == "儲蓄錢包"
    assert e["sections"][0]["category"] == "教育基金"
    assert w["sections"][0].get("visual")
    assert "vtrack" in html_preview(w)
    assert "強制儲錢" in html_preview(w) or "第一桶金" in html_preview(w)
    pdf = build_proposal_pdf(w, agent="Tim")
    assert pdf[:4] == b"%PDF"
    assert len(pdf) > 2000
