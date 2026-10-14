"""Daily production vs MDRT Progress report detection and mapping."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tt_core.constants import MDRT_PROGRESS_MONTH_KEY  # noqa: E402
from tt_core.iris import (  # noqa: E402
    auto_build_preview,
    detect_columns,
    detect_report_kind,
    load_iris_bytes,
    sample_mdrt_template_csv,
    sample_template_csv,
)


def test_daily_mtd_completion():
    csv = (
        "Agent Code,MTD_Sub_FYC,MTD_Comp_FYC,Month\n"
        "30947,90000,52000,2026-10\n"
        "59164,40000,10000,2026-10\n"
    )
    df = load_iris_bytes(csv.encode(), "daily_production_oct.csv")
    assert detect_report_kind(df, "daily_production_oct.csv") == "daily"
    cols = detect_columns(df)
    assert cols["fyc"] == "MTD_Comp_FYC"
    assert cols["mdrt_credit"] is None
    preview, detected = auto_build_preview(df, "2026-10", filename="daily.csv", report_kind="daily")
    assert detected["report_kind"] == "daily"
    by_code = {str(r.iris_code): r for r in preview.itertuples()}
    assert by_code["30947"].amount == 52000
    assert by_code["30947"].month == "2026-10"
    print("daily mtd ok")


def test_mdrt_total_credit():
    csv = (
        "Agent Code,Total Credit eligible for MDRT\n"
        "30947,398944\n"
        "59164,162848\n"
    )
    df = load_iris_bytes(csv.encode(), "MDRT Progress Report.csv")
    assert detect_report_kind(df, "MDRT Progress Report.csv") == "mdrt"
    cols = detect_columns(df)
    assert cols["mdrt_credit"] == "Total Credit eligible for MDRT"
    preview, detected = auto_build_preview(df, "2026-10", filename="mdrt.csv", report_kind="mdrt")
    assert detected["report_kind"] == "mdrt"
    by_code = {str(r.iris_code): r for r in preview.itertuples()}
    assert by_code["30947"].amount == 398944
    assert by_code["30947"].month == MDRT_PROGRESS_MONTH_KEY
    print("mdrt credit ok")


def test_templates():
    daily = load_iris_bytes(sample_template_csv().encode(), "t.csv")
    assert detect_columns(daily)["fyc"] == "MTD_Comp_FYC"
    mdrt = load_iris_bytes(sample_mdrt_template_csv().encode(), "m.csv")
    assert detect_columns(mdrt)["mdrt_credit"] == "Total Credit eligible for MDRT"
    print("templates ok")


if __name__ == "__main__":
    test_daily_mtd_completion()
    test_mdrt_total_credit()
    test_templates()
