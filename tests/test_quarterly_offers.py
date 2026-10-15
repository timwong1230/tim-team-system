"""Quarterly offers helpers."""

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tt_core.quarterly_offers import (  # noqa: E402
    QUARTERS,
    current_quarter_key,
    default_items,
)


def test_quarters_complete():
    assert list(QUARTERS.keys()) == ["Q1", "Q2", "Q3", "Q4"]
    assert current_quarter_key(date(2026, 10, 15)) == "Q4"
    assert current_quarter_key(date(2026, 1, 1)) == "Q1"
    customers = default_items("Q4", "customer")
    agents = default_items("Q4", "agent")
    assert len(customers) >= 10
    assert len(agents) >= 4
    assert any("醫家保" in (c.get("title") or "") for c in customers)
    assert any("盈聚" in (a.get("title") or "") for a in agents)
    assert default_items("Q1", "customer") == []
    print("quarterly offers helpers ok")


if __name__ == "__main__":
    test_quarters_complete()
