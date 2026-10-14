"""Iris should use Monthly Completion / YTD Completion, never Submission."""

import io
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tt_core.iris import (  # noqa: E402
    detect_columns,
    load_iris_bytes,
    build_sync_preview,
    sample_template_csv,
)


def test_prefers_monthly_completion_not_submission():
    csv = (
        "Agent Code,Monthly Submission,Monthly Completion,YTD Completion,Month\n"
        "30947,90000,52000,397457,2026-10\n"
        "59164,40000,10000,162848,2026-10\n"
    )
    df = load_iris_bytes(csv.encode(), "iris.csv")
    cols = detect_columns(df)
    assert cols["fyc"] == "Monthly Completion"
    assert cols["ytd"] == "YTD Completion"
    assert cols["code"] == "Agent Code"

    preview = build_sync_preview(
        df,
        None,
        cols["code"],
        cols["fyc"],
        "Month",
        "2026-10",
        col_ytd=cols["ytd"],
    )
    # amounts must be completion, not submission
    by_code = {str(r.iris_code): r for r in preview.itertuples()}
    assert by_code["30947"].amount == 52000
    assert by_code["30947"].ytd_amount == 397457
    assert by_code["59164"].amount == 10000
    print("completion cols ok")


def test_sample_template_detects():
    df = pd.read_csv(io.StringIO(sample_template_csv()))
    cols = detect_columns(df)
    assert cols["fyc"] == "Monthly Completion"
    assert cols["ytd"] == "YTD Completion"
    print("template ok")


if __name__ == "__main__":
    test_prefers_monthly_completion_not_submission()
    test_sample_template_detects()
