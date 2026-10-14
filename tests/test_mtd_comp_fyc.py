"""Monthly FYC must use MTD_Comp_FYC, never MTD_Sub_FYC."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tt_core.iris import detect_columns, load_iris_bytes, sample_template_csv  # noqa: E402


def test_prefers_mtd_comp_not_sub():
    csv = (
        "Agent Code,MTD_Sub_FYC,MTD_Comp_FYC,Month\n"
        "30947,90000,52000,2026-10\n"
        "59164,40000,10000,2026-10\n"
    )
    df = load_iris_bytes(csv.encode(), "Daily_Production.csv")
    cols = detect_columns(df)
    assert cols["fyc"] == "MTD_Comp_FYC", cols
    assert cols["fyc"] != "MTD_Sub_FYC"
    print("mtd_comp preferred ok")


def test_rejects_sub_only_file_for_completion_alias():
    # If only Sub exists, fallback must still not pick it as completion via 'fyc'
    csv = "Agent Code,MTD_Sub_FYC,Month\n30947,90000,2026-10\n"
    df = load_iris_bytes(csv.encode(), "daily.csv")
    cols = detect_columns(df)
    assert cols["fyc"] != "MTD_Sub_FYC"
    print("mtd_sub rejected ok")


def test_template():
    df = load_iris_bytes(sample_template_csv().encode(), "t.csv")
    cols = detect_columns(df)
    assert cols["fyc"] == "MTD_Comp_FYC"
    print("template ok")


if __name__ == "__main__":
    test_prefers_mtd_comp_not_sub()
    test_rejects_sub_only_file_for_completion_alias()
    test_template()
