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


if __name__ == "__main__":
    test_keys_distinct()
