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


if __name__ == "__main__":
    test_keys_distinct()
    test_mdrt_remaining_formula()
