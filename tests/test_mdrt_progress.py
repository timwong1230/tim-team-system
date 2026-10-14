"""MDRT temporary progress is separate from Iris FYC / YTD."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tt_core.constants import (  # noqa: E402
    IRIS_YTD_MONTH_KEY,
    MDRT_PROGRESS_MONTH_KEY,
    MDRT_TARGET,
)


def test_keys_distinct():
    assert MDRT_PROGRESS_MONTH_KEY == "MDRT_2027"
    assert MDRT_PROGRESS_MONTH_KEY != IRIS_YTD_MONTH_KEY
    assert MDRT_TARGET == 512_800
    print("mdrt progress keys ok")


def test_mdrt_remaining_formula():
    """Home card: 尚欠 = target − Total Credit eligible for MDRT."""
    progress = 397_457.0
    remaining = max(float(MDRT_TARGET) - progress, 0.0)
    pct = min(progress / MDRT_TARGET * 100, 100)
    assert abs(pct - 77.5) < 0.05
    assert remaining == 115_343.0
    assert max(float(MDRT_TARGET) - float(MDRT_TARGET), 0.0) == 0.0
    print("mdrt remaining formula ok")


def test_home_matches_leaderboard_amount():
    """Home must use MDRT_2027 map value, not YTD FYC."""
    from tt_core.data import lookup_mdrt_progress, mdrt_card_metrics

    progress_map = {"Tim": 376_881.0, "Oscar": 161_883.0}
    assert lookup_mdrt_progress("Tim", progress_map) == 376_881.0
    assert lookup_mdrt_progress("tim", progress_map) == 376_881.0  # case-insensitive
    # Missing user → 0 (same as Leaderboard), never invent YTD
    assert lookup_mdrt_progress("Unknown", progress_map) == 0.0

    m = mdrt_card_metrics("Tim", progress_map)
    assert m["mdrt_progress"] == 376_881.0
    assert abs(m["mdrt_pct"] - 73.494) < 0.01
    assert m["mdrt_remaining"] == 135_919.0
    assert m["mdrt_met"] is False
    # Screenshot case: YTD-looking amount must NOT be treated as met
    ytd_like = mdrt_card_metrics("Tim", {"Tim": 221_611.0})
    assert ytd_like["mdrt_met"] is False
    assert ytd_like["mdrt_remaining"] == 291_189.0
    print("home/leaderboard MDRT sync ok")


if __name__ == "__main__":
    test_keys_distinct()
    test_mdrt_remaining_formula()
    test_home_matches_leaderboard_amount()
