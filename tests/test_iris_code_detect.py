"""Iris column heuristics for agent-code-only exports."""

import io
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tt_core.iris import detect_columns, load_iris_bytes, build_sync_preview  # noqa: E402


def test_numeric_name_becomes_code():
    csv = "Agent Name,FYC,Month\n30947,12000,2026-09\n59164,8000,2026-09\n"
    df = load_iris_bytes(csv.encode(), "t.csv")
    cols = detect_columns(df)
    assert cols["code"] == "Agent Name"
    assert cols["agent"] is None
    preview = build_sync_preview(df, None, cols["code"], "FYC", "Month", "2026-09")
    assert set(preview["iris_code"]) == {"30947", "59164"}
    assert (preview["iris_name"] == "").all()
    print("code detect ok")


if __name__ == "__main__":
    test_numeric_name_becomes_code()
