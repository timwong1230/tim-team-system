"""Unit tests for Iris import helpers (no Google Sheets required)."""

import io
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tt_core.iris import (  # noqa: E402
    detect_columns,
    normalize_month,
    parse_amount,
    sample_template_csv,
)


def test_parse_amount():
    assert parse_amount("HK$52,000") == 52000
    assert parse_amount("$1,234.5") == 1234.5
    assert parse_amount(1000) == 1000
    assert parse_amount(None) == 0


def test_normalize_month():
    assert normalize_month("2026-10", "2026-01") == "2026-10"
    assert normalize_month("2026/9", "2026-01") == "2026-09"
    assert normalize_month("202610", "2026-01") == "2026-10"
    assert normalize_month("", "2026-03") == "2026-03"


def test_detect_columns_english():
    df = pd.read_csv(io.StringIO(sample_template_csv()))
    cols = detect_columns(df)
    assert cols["agent"] == "Agent Name"
    assert cols["code"] == "Agent Code"
    assert cols["fyc"] == "MTD-COMPLETION"
    assert cols["month"] == "Month"


def test_detect_columns_chinese():
    df = pd.DataFrame(
        {
            "代理人姓名": ["Tim"],
            "代理人編號": ["A1"],
            "首年佣金": [100],
            "業績月份": ["2026-10"],
        }
    )
    cols = detect_columns(df)
    assert cols["agent"] == "代理人姓名"
    assert cols["code"] == "代理人編號"
    assert cols["fyc"] == "首年佣金"
    assert cols["month"] == "業績月份"


if __name__ == "__main__":
    test_parse_amount()
    test_normalize_month()
    test_detect_columns_english()
    test_detect_columns_chinese()
    print("ok")
