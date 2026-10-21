"""Premium financing (PFin) calculator — ICON V + bank snapshot."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tt_core import pfin  # noqa: E402


def test_banks_and_illustration_loaded():
    banks = pfin.list_banks()
    assert len(banks) == 6
    ids = {b["id"] for b in banks}
    assert ids == {
        "za-bank",
        "dah-sing",
        "dbs",
        "citic",
        "ocbc",
        "shanghai-comm",
    }
    za = pfin.get_bank("za-bank")
    assert za is not None
    assert za["maxLTV"]["sameCurrencyRatio"] == 0.95
    assert za["isRecommendedForIconV"] is True

    meta = pfin.illustration_meta()
    assert meta["base_premium_usd"] == 400_000
    assert meta["day1_guaranteed_cv_ratio"] == 0.82
    rows = pfin.scale_illustration(400_000)
    assert rows[0]["year"] == 1
    assert rows[0]["totalSurrenderValue"] == 328_000
    assert rows[-1]["year"] == 116


def test_promo_tiers_and_levy():
    assert pfin.promo_discount_rate(100_000) == 0.04
    assert pfin.promo_discount_rate(200_000) == 0.06
    assert pfin.promo_discount_rate(400_000) == 0.06
    assert pfin.promo_discount_rate(500_000) == 0.08
    # Cap at HKD 100 / FX (~US$12.74); small premiums use 0.1% until cap
    assert abs(pfin.levy_usd(400_000, 7.85) - (100 / 7.85)) < 1e-9
    assert abs(pfin.levy_usd(5_000, 7.85) - 5.0) < 1e-9


def test_za_bank_financing_matches_spa_core():
    r = pfin.compute_financing(400_000, "za-bank", apply_promotion=True)
    s = r["summary"]
    assert s["day1_guaranteed_cv_usd"] == 328_000
    assert s["loan_usd"] == round(328_000 * 0.95)
    assert s["discount_rate"] == 0.06
    assert s["discount_usd"] == 24_000
    # loan HKD > 2M → setup fee waived
    assert s["loan_hkd"] > 2_000_000
    assert s["setup_fee_usd"] == 0
    assert s["initial_outlay_usd"] > 0
    assert s["leverage_ratio"] > 1
    y6 = next(y for y in r["years"] if y["year"] == 6)
    assert y6["total_sv_usd"] == 478_916
    assert y6["net_sv_usd"] == y6["total_sv_usd"] - s["loan_usd"]
    assert "示意" in r["disclaimer"]


def test_scale_linear_and_irr_sign():
    half = pfin.scale_illustration(200_000)
    full = pfin.scale_illustration(400_000)
    assert half[5]["totalSurrenderValue"] == round(full[5]["totalSurrenderValue"] / 2)
    r = pfin.compute_financing(200_000, "shanghai-comm", apply_promotion=False)
    y20 = next(y for y in r["years"] if y["year"] == 20)
    # Long-run leveraged exit should be able to produce a finite IRR
    assert isinstance(y20["leveraged_irr_pct"], float)


def test_app_wires_pfin_into_client_tools():
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "🏦 保費融資計算機" in app
    assert "def page_pfin" in app
    assert 'elif "保費融資" in pick:' in app
    assert 'pdf_data={"kind": "pfin"' in app or '"kind": "pfin"' in app
    assert "_render_whatsapp_share" in app[
        app.index("def page_pfin") : app.index("def page_medical_finance")
    ]
    # Must live under client tools hub, not root menu
    start = app.index("CLIENT_TOOL_LABELS = [")
    end = app.index("]", start)
    assert "🏦 保費融資計算機" in app[start:end]
    menu_start = app.index("menu_items = [")
    menu_end = app.index("]", menu_start)
    assert "🏦 保費融資計算機" not in app[menu_start:menu_end]


def test_pfin_pdf_and_whatsapp():
    from tt_core.client_pdf import build_client_pdf, build_pfin_pdf, pdf_filename

    r = pfin.compute_financing(400_000, "za-bank", apply_promotion=True)
    highlights = dict(pfin.key_highlights(r))
    assert "自己出本金" in highlights
    assert "保單價值" in highlights
    assert "產品優惠" in highlights
    assert "每月利息支出" in highlights
    assert "10年後退保價值" in highlights
    assert highlights["保單價值"] == "US$328,000"
    assert highlights["產品優惠"].startswith("6%")
    assert "US$624,182" in highlights["10年後退保價值"]
    assert r["summary"]["monthly_interest_usd"] == round(
        r["summary"]["annual_interest_usd"] / 12
    )

    wa = pfin.whatsapp_summary(r, client="陳生")
    assert "保費融資計劃書" in wa
    assert "陳生" in wa
    assert "見客重點" in wa
    for label in (
        "自己出本金",
        "保單價值",
        "產品優惠",
        "每月利息支出",
        "10年後退保價值",
    ):
        assert label in wa

    pdf = build_pfin_pdf(
        title="保費融資計劃書",
        client="陳生",
        agent="Tim",
        result=r,
    )
    assert pdf[:4] == b"%PDF"
    assert len(pdf) > 2000
    import pymupdf

    texts = "\n".join(p.get_text() for p in pymupdf.open(stream=pdf, filetype="pdf"))
    assert "見客重點" in texts
    assert "自己出本金" in texts
    assert "每月利息支出" in texts
    assert "10年後退保價值" in texts

    via = build_client_pdf(
        title="保費融資計劃書",
        body=wa,
        client="陳生",
        tool_name="保費融資計算機",
        agent="Tim",
        pdf_data={"kind": "pfin", "result": r},
    )
    assert via[:4] == b"%PDF"
    fname = pdf_filename(title="保費融資計劃書", client="陳生", tool="保費融資計算機")
    assert fname.endswith(".pdf")
