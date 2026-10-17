"""Weekly settlement report — Tim excluded from rewards/penalties."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tt_core.weekly_report import (  # noqa: E402
    build_weekly_settlement_report,
    pick_losers,
    pick_mvp_winners,
)


def _df(rows):
    return pd.DataFrame(rows)


def test_tim_never_on_penalty_list():
    wk = _df(
        [
            {"username": "Tim", "wk_score": 0, "wk_count": 0},
            {"username": "Oscar", "wk_score": 0, "wk_count": 0},
            {"username": "Hanes", "wk_score": 7, "wk_count": 3},
        ]
    )
    losers = pick_losers(wk)
    names = set(losers["username"].astype(str))
    assert "Tim" not in names
    assert "Oscar" in names


def test_tim_highest_score_mvp_goes_to_second():
    wk = _df(
        [
            {"username": "Tim", "wk_score": 10, "wk_count": 3},
            {"username": "Hanes", "wk_score": 7, "wk_count": 3},
            {"username": "Oscar", "wk_score": 3, "wk_count": 3},
        ]
    )
    winners = pick_mvp_winners(wk)
    assert list(winners["username"]) == ["Hanes"]


def test_no_penalty_tim_sponsors_top_non_tim():
    wk = _df(
        [
            {"username": "Tim", "wk_score": 3, "wk_count": 3},
            {"username": "Hanes", "wk_score": 7, "wk_count": 3},
            {"username": "Oscar", "wk_score": 3, "wk_count": 3},
        ]
    )
    report = build_weekly_settlement_report(wk, "2026-10-05", "2026-10-11")
    assert "Hanes" in report and "MVP" in report
    assert "Tim 獎 $100" in report
    assert "❌ Tim" not in report
    assert "Tim: 3分" in report
    assert "Oscar: 3分" in report


def test_with_penalties_exclude_tim_from_fine_list():
    wk = _df(
        [
            {"username": "Tim", "wk_score": 3, "wk_count": 3},
            {"username": "Hanes", "wk_score": 7, "wk_count": 3},
            {"username": "Oscar", "wk_score": 0, "wk_count": 0},
        ]
    )
    report = build_weekly_settlement_report(wk, "2026-10-05", "2026-10-11")
    assert "❌ Oscar" in report
    assert "❌ Tim" not in report
    assert "Hanes" in report
    assert "多謝 1 位同事贊助" in report
    assert "Tim: 3分" in report


def test_app_uses_weekly_report_helper():
    src = (_ROOT / "app.py").read_text(encoding="utf-8")
    assert "build_weekly_settlement_report" in src
    assert "獎罰唔包 Tim" in src
