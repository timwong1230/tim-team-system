"""Row id matching — prospects delete/update must hit id column, not quarter."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd


def test_normalize_id_canonical():
    from tt_core.cache_store import normalize_id

    assert normalize_id(1) == "1"
    assert normalize_id(1.0) == "1"
    assert normalize_id("1") == "1"
    assert normalize_id("1.0") == "1"
    assert normalize_id(" 12.0 ") == "12"
    assert normalize_id("abc") == "abc"
    assert normalize_id(None) == ""
    assert normalize_id(float("nan")) == ""


def test_cache_delete_matches_float_and_str_ids():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["TIM_TEAM_CACHE_DIR"] = tmp
        import importlib
        import tt_core.cache_store as cs

        importlib.reload(cs)

        df = pd.DataFrame(
            [
                {"id": "1.0", "name": "A", "quarter": "1"},
                {"id": "2", "name": "B", "quarter": "1"},
            ]
        )
        cs.save_sheet("prospects", df, source="test")

        # Delete by int 1 should remove the "1.0" row
        cs.delete_row_cache("prospects", 1)
        loaded, _ = cs.load_sheet("prospects")
        assert loaded is not None
        assert list(loaded["name"]) == ["B"]

        cs.upsert_row_cache("prospects", {"id": 2.0, "name": "B2", "quarter": "1"})
        loaded2, _ = cs.load_sheet("prospects")
        assert loaded2.iloc[0]["name"] == "B2"
        assert cs.normalize_id(loaded2.iloc[0]["id"]) == "2"


def test_find_sheet_row_by_id_ignores_quarter_column():
    """ws.find('1') used to hit quarter=1 before id=1 — must use id column only."""
    import tt_core.db as db

    ws = MagicMock()
    # headers + three data rows; quarter column has "1" before id "1" in scan order
    ws.row_values.return_value = [
        "id",
        "username",
        "list_type",
        "year",
        "quarter",
        "name",
    ]
    # col_values(1) = id column
    ws.col_values.return_value = ["id", "5", "1", "3"]

    row = db._find_sheet_row_by_id(ws, 1)
    assert row == 3  # third sheet row (header + 5 + 1)
    ws.col_values.assert_called_with(1)

    # float / "1.0" must still resolve
    assert db._find_sheet_row_by_id(ws, "1.0") == 3
    assert db._find_sheet_row_by_id(ws, 5.0) == 2
    assert db._find_sheet_row_by_id(ws, 99) is None


def test_normalize_df_canonicalizes_ids():
    import tt_core.db as db

    raw = pd.DataFrame([{"id": 1.0, "username": "Tim", "name": "X"}])
    out = db._normalize_df(raw, "prospects")
    assert out.iloc[0]["id"] == "1"
