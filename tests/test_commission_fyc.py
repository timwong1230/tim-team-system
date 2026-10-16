"""準客戶名單 — product premiums → FYC via commission rates."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tt_core.commission import (  # noqa: E402
    PRODUCT_CATALOG,
    calc_fyc,
    products_summary,
)
from tt_core.prospects import (  # noqa: E402
    decode_products,
    display_products,
    encode_products,
    factfind_template,
)


def test_catalog_matches_excel_columns():
    keys = [p["key"] for p in PRODUCT_CATALOG]
    assert keys == [
        "vfamily",
        "vprime",
        "ebeyond",
        "crisis_20",
        "crisis_25",
        "crisis_30",
        "icon_1",
        "maxfocus_2",
        "maxfocus_3",
        "maxfocus_5",
        "annuity_5",
        "annuity_10",
        "term_5",
        "term_10",
        "term_20",
    ]
    rates = {p["key"]: p["rate"] for p in PRODUCT_CATALOG}
    assert rates["vfamily"] == 0.27
    assert rates["vprime"] == 0.25
    assert rates["crisis_20"] == 0.50
    assert rates["crisis_25"] == 0.52
    assert rates["crisis_30"] == 0.53
    assert rates["icon_1"] == 0.03
    assert rates["maxfocus_5"] == 0.275
    assert rates["annuity_10"] == 0.30
    assert rates["term_10"] == 0.35


def test_calc_fyc_ben_example():
    """Excel row Ben: 醫家保 4082 + 危疾30pay 13378 + 盈聚5pay 40108."""
    premiums = {"vfamily": 4082, "crisis_30": 13378, "maxfocus_5": 40108}
    # 4082*0.27 + 13378*0.53 + 40108*0.275
    expected = 4082 * 0.27 + 13378 * 0.53 + 40108 * 0.275
    assert abs(calc_fyc(premiums) - expected) < 0.02
    assert abs(calc_fyc(premiums) - 19222.18) < 0.05


def test_encode_decode_roundtrip():
    raw = encode_products({"vfamily": 4082, "crisis_30": 0, "maxfocus_5": 40108})
    decoded = decode_products(raw)
    assert decoded == {"vfamily": 4082.0, "maxfocus_5": 40108.0}
    assert "醫家保" in display_products(raw)
    assert "盈聚天下II 5pay" in products_summary(decoded)


def test_legacy_free_text_decode():
    assert decode_products("醫家保 + 盈聚") == {}
    assert display_products("醫家保 + 盈聚") == "醫家保 + 盈聚"


def test_factfind_kept():
    t = factfind_template()
    assert "1. 性格" in t
    assert "15." in t


def test_menu_renamed():
    src = (_ROOT / "app.py").read_text(encoding="utf-8")
    block = src.split("menu_items = [")[1].split("]")[0]
    assert "📋 準客戶名單" in block
    assert "Prospect List" not in block


if __name__ == "__main__":
    test_catalog_matches_excel_columns()
    test_calc_fyc_ben_example()
    test_encode_decode_roundtrip()
    test_legacy_free_text_decode()
    test_factfind_kept()
    test_menu_renamed()
    print("commission fyc ok")
