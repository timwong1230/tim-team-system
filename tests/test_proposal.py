"""Client proposal builder — Full Protection / Saving Plan."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def test_catalog_loads():
    from tt_core.proposal import load_catalog, missing_data_notes, plan_types, products_in

    cat = load_catalog()
    assert plan_types()
    assert len(products_in("medical")) >= 4
    assert len(products_in("critical_illness")) >= 7  # 全應援3 + 應援保2 + 緻尚保2 + 好易揀
    assert len(products_in("accident")) >= 2
    assert len(products_in("saving")) >= 1
    assert any("危疾" in n for n in missing_data_notes())
    # Drive-sourced highlights should be substantive
    fam = next(p for p in products_in("medical") if p["id"] == "vfamily")
    assert any("55" in h for h in fam["highlights"])
    assert len(fam["highlights"]) >= 6
    assert cat.get("source_note")


def test_full_protection_medical_auto_premium():
    from tt_core.proposal import build_protection_proposal

    prop = build_protection_proposal(
        client_name="Mathilda",
        age=30,
        gender="女",
        occupation="行政",
        include_medical=True,
        include_ci=False,
        include_accident=False,
        medical_id="vbooster",
        medical_deductible=0,
    )
    assert prop["kind"] == "full_protection"
    assert len(prop["sections"]) == 1
    sec = prop["sections"][0]
    assert sec["category"] == "醫療保險"
    assert sec["premium_ok"] is True
    assert sec["premium_annual_hkd"] > 0
    assert prop["total_annual_hkd"] == sec["premium_annual_hkd"]
    assert not prop["gaps"]


def test_full_protection_ci_requires_manual_premium():
    from tt_core.proposal import build_protection_proposal

    prop = build_protection_proposal(
        client_name="Mathilda",
        age=30,
        gender="女",
        include_medical=False,
        include_ci=True,
        include_accident=False,
        ci_id="ci_advanced",
        ci_sa_usd=128000,
        ci_pay_term=20,
        ci_annual_hkd=0,
    )
    assert prop["sections"]
    assert prop["sections"][0]["premium_ok"] is False
    assert any("危疾" in g and "保費" in g for g in prop["gaps"])

    prop2 = build_protection_proposal(
        client_name="Mathilda",
        age=30,
        gender="女",
        include_medical=False,
        include_ci=True,
        include_accident=False,
        ci_id="ci_advanced",
        ci_sa_usd=128000,
        ci_pay_term=20,
        ci_annual_hkd=29238,
    )
    assert prop2["sections"][0]["premium_ok"] is True
    assert prop2["total_annual_hkd"] == 29238
    assert prop2["ready"] is True


def test_saving_proposal_yingju():
    from tt_core.proposal import build_saving_proposal

    prop = build_saving_proposal(
        client_name="Fai BB",
        age=35,
        gender="男",
        occupation="工程",
        saving_id="yingju5",
        annual_usd=10000,
        purpose="教育基金",
    )
    assert prop["kind"] == "saving"
    assert prop["ready"] is True
    sec = prop["sections"][0]
    assert "盈聚" in sec["product_name"]
    assert sec["premium_annual_hkd"] > 0
    assert sec.get("illustration")


def test_no_duplicate_premium_meta_and_rich_highlights():
    from tt_core.proposal import build_protection_proposal, get_product

    prop = build_protection_proposal(
        client_name="Tim",
        age=35,
        gender="男",
        include_medical=True,
        include_ci=True,
        include_accident=True,
        medical_id="vfamily",
        ci_id="ci_essential",
        ci_sa_usd=128000,
        ci_pay_term=20,
        ci_annual_hkd=30000,
        accident_id="life_accident_rider",
        accident_sa_hkd=800000,
        accident_annual_hkd=1208,
    )
    for sec in prop["sections"]:
        meta_keys = [k for k, _ in sec.get("meta_rows") or []]
        assert "保費" not in meta_keys
        assert "產品" not in meta_keys
        assert len(sec.get("highlights") or []) >= 5
    for row in prop["summary_rows"]:
        prem = str(row.get("年供保費") or "")
        assert "／月" not in prem
        assert "約" not in prem

    fam = get_product("medical", "vfamily")
    assert fam and len(fam.get("highlights") or []) >= 6
    # New CI lines from Drive leaflets are selectable
    assert get_product("critical_illness", "ci_zhishang_plus")
    assert get_product("critical_illness", "ci_easy")
    assert get_product("accident", "life_accident_rider")["short"] == "人身意外附約"


def test_html_and_whatsapp_and_pdf():
    from tt_core.proposal import (
        build_protection_proposal,
        html_preview,
        proposal_whatsapp,
    )
    from tt_core.proposal_pdf import build_proposal_pdf

    prop = build_protection_proposal(
        client_name="Mathilda",
        age=30,
        gender="女",
        include_medical=True,
        include_ci=True,
        include_accident=True,
        medical_id="vbooster",
        medical_deductible=0,
        ci_id="ci_advanced",
        ci_sa_usd=128000,
        ci_pay_term=20,
        ci_annual_hkd=29238,
        accident_id="life_accident_rider",
        accident_sa_hkd=800000,
        accident_annual_hkd=1188,
    )
    html = html_preview(prop)
    assert "Mathilda" in html
    assert "SUMMARY" in html
    assert "倍衛您" in html or "醫療" in html

    wa = proposal_whatsapp(prop)
    assert "Mathilda" in wa
    assert "危疾" in wa

    pdf = build_proposal_pdf(prop, agent="Tim")
    assert pdf[:4] == b"%PDF"
    assert len(pdf) > 2000


def test_app_wires_proposal_tool():
    src = (_ROOT / "app.py").read_text(encoding="utf-8")
    assert "📋 計劃書" in src
    assert "def page_proposal" in src
    assert 'if "計劃書" in pick' in src
