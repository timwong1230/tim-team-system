"""Quarterly offers helpers."""

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tt_core.quarterly_offers import (  # noqa: E402
    QUARTERS,
    current_quarter_key,
    default_catalog,
    default_items,
)


def test_quarters_complete():
    assert list(QUARTERS.keys()) == ["Q1", "Q2", "Q3", "Q4"]
    assert current_quarter_key(date(2026, 10, 15)) == "Q4"
    assert current_quarter_key(date(2026, 1, 1)) == "Q1"

    cat = default_catalog("Q4", "customer")
    assert cat["sections"]
    assert cat["sections"][0]["columns"]
    assert cat["sections"][0]["rows"]
    assert any("醫家保" in str(row[0]) for sec in cat["sections"] for row in sec["rows"])

    agent = default_catalog("Q4", "agent")
    assert any("盈聚" in (sec.get("title") or "") for sec in agent["sections"])
    assert default_catalog("Q1", "customer")["sections"] == []
    assert len(default_items("Q4", "customer")) >= 10
    print("quarterly offers helpers ok")


if __name__ == "__main__":
    test_quarters_complete()
