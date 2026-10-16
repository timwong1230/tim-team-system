"""龍虎榜 merge + Dashboard recruit progress target."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tt_core.constants import MDRT_TARGET, RECRUIT_YEAR_TARGET  # noqa: E402


def test_recruit_year_target():
    assert RECRUIT_YEAR_TARGET == 2
    assert MDRT_TARGET == 512_800


def test_recruit_progress_ratio():
    """Progress bar should scale linearly against yearly goal of 2."""
    target = float(RECRUIT_YEAR_TARGET)
    assert min(max(0 / target * 100, 0), 100) == 0.0
    assert min(max(1 / target * 100, 0), 100) == 50.0
    assert min(max(2 / target * 100, 0), 100) == 100.0
    assert min(max(3 / target * 100, 0), 100) == 100.0  # capped


def test_app_menu_merged():
    src = (_ROOT / "app.py").read_text(encoding="utf-8")
    block = src.split("menu_items = [")[1].split("]")[0]
    assert "🏅 龍虎榜" in block
    assert "業績龍虎榜" not in block
    assert "page_performance_leaderboard" in src
    assert "📅 每月業績" not in block
    assert "🏆 年度挑戰" not in block
    assert "⚖️ 每週挑戰" not in block
    assert "🤝 招募龍虎榜" not in block
    assert "招募進度" in src
    assert "RECRUIT_YEAR_TARGET" in src
    assert '_section_recruit()' in src or "_section_recruit" in src
    # Dashboard sits directly under 我的主頁
    home_i = block.index("🏠 我的主頁")
    dash_i = block.index("📊 團隊 Dashboard")
    assert dash_i > home_i
    between = block[home_i:dash_i]
    assert between.count('"') <= 2  # no other menu item between


if __name__ == "__main__":
    test_recruit_year_target()
    test_recruit_progress_ratio()
    test_app_menu_merged()
    print("leaderboard merge ok")
