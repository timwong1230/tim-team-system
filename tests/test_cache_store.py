"""Cache store tests (no Google Sheets / Streamlit runtime required)."""

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd


def test_save_load_roundtrip(monkeypatch_dir=None):
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["TIM_TEAM_CACHE_DIR"] = tmp
        # Re-import with new env
        import importlib
        import lib.cache_store as cs

        importlib.reload(cs)

        df = pd.DataFrame([{"id": "1", "username": "Tim", "amount": "100"}])
        cs.save_sheet("monthly_fyc", df, source="test")
        loaded, meta = cs.load_sheet("monthly_fyc")
        assert loaded is not None
        assert len(loaded) == 1
        assert loaded.iloc[0]["username"] == "Tim"
        assert meta.get("rows") == 1
        assert cs.next_id("monthly_fyc") == 2

        cs.upsert_row_cache(
            "monthly_fyc",
            {"id": "1", "username": "Tim", "amount": "200"},
        )
        loaded2, _ = cs.load_sheet("monthly_fyc")
        assert loaded2.iloc[0]["amount"] == "200"

        cs.delete_row_cache("monthly_fyc", "1")
        loaded3, _ = cs.load_sheet("monthly_fyc")
        assert loaded3 is not None and loaded3.empty

        status = cs.get_status()
        assert "monthly_fyc" in status["sheets"]
        print("cache_store ok")


if __name__ == "__main__":
    test_save_load_roundtrip()
