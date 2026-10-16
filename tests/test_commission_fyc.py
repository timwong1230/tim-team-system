"""準客戶名單 — hot products, 其他, QSB +10% after YTD ≥ $88k."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tt_core.commission import (  # noqa: E402
    PRODUCT_CATALOG,
    QSB_ELIGIBLE_KEYS,
    QSB_THRESHOLD,
    calc_fyc,
    products_summary,
    qsb_active,
    rate_for,
)
from tt_core.prospects import (  # noqa: E402
    decode_deal,
    display_products,
    encode_products,
    factfind_template,
)


def test_catalog_and_qsb_keys():
    assert QSB_THRESHOLD == 88_000
    assert qsb_active(87_999) is False
    assert qsb_active(88_000) is True
    assert QSB_ELIGIBLE_KEYS == {
        "crisis_20",
        "crisis_25",
        "crisis_30",
        "maxfocus_5",
        "annuity_5",
        "annuity_10",
    }
    # Medical / short-pay saving / term are NOT QSB
    assert "vfamily" not in QSB_ELIGIBLE_KEYS
    assert "maxfocus_2" not in QSB_ELIGIBLE_KEYS
    assert "term_10" not in QSB_ELIGIBLE_KEYS


def test_calc_fyc_ben_without_qsb():
    premiums = {"vfamily": 4082, "crisis_30": 13378, "maxfocus_5": 40108}
    expected = 4082 * 0.27 + 13378 * 0.53 + 40108 * 0.275
    assert abs(calc_fyc(premiums, ytd_fyc=50_000) - expected) < 0.05
    assert abs(calc_fyc(premiums, ytd_fyc=50_000) - 19222.18) < 0.05


def test_calc_fyc_with_qsb():
    """After $88k YTD: crisis + maxfocus_5 get ×1.1; medical unchanged."""
    premiums = {"vfamily": 4082, "crisis_30": 13378, "maxfocus_5": 40108}
    base_med = 4082 * 0.27
    base_ci = 13378 * 0.53 * 1.1
    base_save = 40108 * 0.275 * 1.1
    expected = base_med + base_ci + base_save
    got = calc_fyc(premiums, ytd_fyc=88_000)
    assert abs(got - expected) < 0.05
    assert abs(rate_for("crisis_30", ytd_fyc=88_000) - 0.53 * 1.1) < 1e-9
    assert rate_for("vfamily", ytd_fyc=88_000) == 0.27


def test_other_products_manual():
    others = [{"name": "危疾緻尚保 20pay", "premium": 20000, "rate": 50}]  # 50%
    assert abs(calc_fyc({}, others=others) - 10000) < 0.01
    # decimal rate also ok
    others2 = [{"name": "X", "premium": 10000, "rate": 0.25}]
    assert abs(calc_fyc({}, others=others2) - 2500) < 0.01
    # Other does NOT get auto QSB
    assert abs(calc_fyc({}, others=others2, ytd_fyc=100_000) - 2500) < 0.01


def test_encode_decode_with_other():
    raw = encode_products(
        {"vfamily": 4082},
        [{"name": "某某計劃", "premium": 5000, "rate": 0.2}],
    )
    premiums, others = decode_deal(raw)
    assert premiums == {"vfamily": 4082.0}
    assert others == [{"name": "某某計劃", "premium": 5000.0, "rate": 0.2}]
    summary = display_products(raw, ytd_fyc=0)
    assert "醫家保" in summary
    assert "其他:某某計劃" in summary


def test_factfind_kept():
    t = factfind_template()
    assert "1. 性格" in t
    assert "15." in t


def test_menu_renamed():
    src = (_ROOT / "app.py").read_text(encoding="utf-8")
    block = src.split("menu_items = [")[1].split("]")[0]
    assert "📋 準客戶名單" in block
    assert "Extra 10 已開" in src
    assert "QSB 已開" not in src


if __name__ == "__main__":
    test_catalog_and_qsb_keys()
    test_calc_fyc_ben_without_qsb()
    test_calc_fyc_with_qsb()
    test_other_products_manual()
    test_encode_decode_with_other()
    test_factfind_kept()
    test_menu_renamed()
    print("commission fyc + qsb ok")
