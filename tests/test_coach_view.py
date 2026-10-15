"""Weekly challenge coach view — stuck cases + reasons."""

from __future__ import annotations

import datetime

import pandas as pd

from tt_core.data import get_stuck_cases, infer_stuck_reason


def test_infer_stuck_reason_overdue_closing():
    today = datetime.date(2026, 10, 15)
    reason = infer_stuck_reason(
        {
            "stage": "Closing",
            "track": "做數",
            "next_action": "約簽單",
            "next_date": "2026-10-10",
        },
        today=today,
    )
    assert "過期 5 日" in reason
    assert "收單" in reason or "Closing" in reason
    assert "做數" in reason


def test_infer_stuck_reason_due_today():
    today = datetime.date(2026, 10, 15)
    reason = infer_stuck_reason(
        {
            "stage": "見經理",
            "track": "招募",
            "next_action": "帶去見經理",
            "next_date": "2026-10-15",
        },
        today=today,
    )
    assert "今日到期" in reason
    assert "見經理" in reason


def test_get_stuck_cases_filters_and_reasons(monkeypatch):
    today = datetime.date(2026, 10, 15)
    rows = pd.DataFrame(
        [
            {
                "id": 1,
                "username": "Tim",
                "track": "做數",
                "person": "陳生",
                "stage": "Handling Rejection",
                "next_action": "拆抗拒",
                "next_date": "2026-10-12",
                "status": "open",
            },
            {
                "id": 2,
                "username": "Tim",
                "track": "做數",
                "person": "李太",
                "stage": "3Q",
                "next_action": "約見",
                "next_date": "2026-10-20",
                "status": "open",
            },
            {
                "id": 3,
                "username": "Oscar",
                "track": "招募",
                "person": "阿強",
                "stage": "報考試",
                "next_action": "催報名",
                "next_date": "2026-10-14",
                "status": "open",
            },
            {
                "id": 4,
                "username": "Tim",
                "track": "做數",
                "person": "舊客",
                "stage": "Closing",
                "next_action": "x",
                "next_date": "2026-10-01",
                "status": "done",
            },
        ]
    )
    monkeypatch.setattr("tt_core.data.read_data", lambda *_a, **_k: rows.copy())

    tim = get_stuck_cases("Tim", on_or_before=today)
    assert list(tim["person"]) == ["陳生"]
    assert "抗拒" in str(tim.iloc[0]["stuck_reason"])
    assert int(tim.iloc[0]["overdue_days"]) == 3

    all_stuck = get_stuck_cases(None, on_or_before=today)
    assert set(all_stuck["person"]) == {"陳生", "阿強"}
    # Most overdue first
    assert all_stuck.iloc[0]["person"] == "陳生"
