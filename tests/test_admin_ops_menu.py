"""Admin home ops desk + client-tools menu consolidation."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from tt_core.constants import WEEKLY_MIN_ACTS
from tt_core.data import weekly_activity_shortfall

_ROOT = Path(__file__).resolve().parents[1]
_APP = (_ROOT / "app.py").read_text(encoding="utf-8")


def test_weekly_activity_shortfall_filters_and_sorts():
    overview = pd.DataFrame(
        [
            {"username": "Oscar", "wk_count": 1, "needs_acts": True, "stuck_count": 0},
            {"username": "Hanes", "wk_count": WEEKLY_MIN_ACTS, "needs_acts": False, "stuck_count": 1},
            {"username": "Amy", "wk_count": 0, "needs_acts": True, "stuck_count": 2},
        ]
    )
    short = weekly_activity_shortfall(overview)
    assert list(short["username"]) == ["Amy", "Oscar"]
    assert all(short["needs_acts"])


def test_weekly_activity_shortfall_empty():
    assert weekly_activity_shortfall(pd.DataFrame()).empty
    assert weekly_activity_shortfall(
        pd.DataFrame([{"username": "A", "wk_count": 3, "needs_acts": False}])
    ).empty


def test_root_menu_uses_client_tools_hub():
    assert 'CLIENT_TOOLS_MENU = "🧰 客戶工具"' in _APP
    assert "def page_client_tools" in _APP
    assert "def _render_admin_ops_desk" in _APP
    # Leaf tools must not sit in the root menu_items list literal
    menu_block_start = _APP.index("menu_items = [")
    menu_block_end = _APP.index("]", menu_block_start)
    menu_block = _APP[menu_block_start:menu_block_end]
    for leaf in (
        "🩺 常見疾病核保",
        "💹 收入／支出 T-Account",
        "🛡️ 保障缺口",
        "🏥 醫療融資計算機",
        "🆚 保險公司新人 Package 對比",
    ):
        assert leaf not in menu_block
    assert "CLIENT_TOOLS_MENU" in menu_block


def test_admin_ops_desk_has_iris_and_weekly_entrypoints():
    assert "去同步最新業績檔" in _APP
    assert "每週戰報（WhatsApp）" in _APP
    assert "本週欠活動" in _APP
    assert "build_weekly_settlement_report" in _APP
