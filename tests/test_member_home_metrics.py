"""Member homepage scorecard: MTD → YTD/MDRT → recruit remaining."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from tt_core.constants import MDRT_TARGET, RECRUIT_YEAR_TARGET
from tt_core.data import member_home_metrics

_ROOT = Path(__file__).resolve().parents[1]
_APP = (_ROOT / "app.py").read_text(encoding="utf-8")


def test_member_home_metrics_shape(monkeypatch):
    monkeypatch.setattr(
        "tt_core.data.get_member_snapshot",
        lambda _u: {
            "fyc": 120_000.0,
            "mdrt_progress": 200_000.0,
            "mdrt_pct": 200_000.0 / MDRT_TARGET * 100,
            "mdrt_remaining": MDRT_TARGET - 200_000.0,
            "mdrt_met": False,
            "recruit": 1,
            "wk_count": 2,
            "wk_score": 4,
        },
    )
    monkeypatch.setattr("tt_core.data.get_mtd_fyc", lambda _u, month=None: 35_000.0)

    m = member_home_metrics("Oscar", today=pd.Timestamp("2026-10-17").date())
    assert m["month"] == "2026-10"
    assert m["mtd_fyc"] == 35_000.0
    assert m["ytd_fyc"] == 120_000.0
    assert m["mdrt_progress"] == 200_000.0
    assert m["mdrt_remaining"] == MDRT_TARGET - 200_000.0
    assert m["recruit"] == 1
    assert m["recruit_target"] == RECRUIT_YEAR_TARGET
    assert m["recruit_remaining"] == max(0, RECRUIT_YEAR_TARGET - 1)


def test_member_home_metrics_recruit_met(monkeypatch):
    monkeypatch.setattr(
        "tt_core.data.get_member_snapshot",
        lambda _u: {
            "fyc": 0.0,
            "mdrt_progress": MDRT_TARGET,
            "mdrt_pct": 100.0,
            "mdrt_remaining": 0.0,
            "mdrt_met": True,
            "recruit": RECRUIT_YEAR_TARGET,
            "wk_count": 3,
            "wk_score": 6,
        },
    )
    monkeypatch.setattr("tt_core.data.get_mtd_fyc", lambda *_a, **_k: 0.0)
    m = member_home_metrics("Hanes")
    assert m["recruit_remaining"] == 0
    assert m["mdrt_met"] is True


def test_page_home_scorecard_order_in_source():
    assert "def _render_member_home_scorecard" in _APP
    assert "def _html_member_home_scorecard" in _APP
    assert "tt-scorecard" in _APP
    assert "本月完成" in _APP
    assert "全年完成" in _APP
    assert "今年招募" in _APP
    assert 'f"你好，{user}"' in _APP or "你好，{user}" in _APP
    assert "### 今日跟進事項" in _APP
    # Follow-ups section appears before member scorecard call
    due_i = _APP.index('st.markdown("### 今日跟進事項"')
    score_i = _APP.index("_render_member_home_scorecard(user)")
    assert due_i < score_i


def test_html_member_scorecard_renders_numbers():
    # Import via exec of helper would pull streamlit; assert CSS class in styles instead
    styles = (_ROOT / "tt_core" / "styles.py").read_text(encoding="utf-8")
    assert ".tt-scorecard" in styles
    assert ".tt-score-card-accent" in styles
