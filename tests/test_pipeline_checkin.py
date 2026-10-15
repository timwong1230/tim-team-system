"""Pipeline check-in + due follow-ups."""

from __future__ import annotations

import datetime

import pandas as pd

from tt_core.constants import (
    RECRUIT_STAGES,
    SALES_STAGES,
    TEMPLATE_FACTFIND,
    TEMPLATE_RECRUIT,
    TEMPLATE_SALES,
    TRACK_RECRUIT,
    TRACK_SALES,
)
from tt_core.data import (
    compose_pipeline_note,
    get_due_followups,
    get_note_template,
    get_upcoming_followups,
    track_for_activity,
)


def test_templates_shared_factfind():
    assert "1. 性格" in TEMPLATE_FACTFIND
    assert TEMPLATE_SALES == TEMPLATE_FACTFIND
    assert TEMPLATE_RECRUIT == TEMPLATE_FACTFIND
    assert "1. 性格" in get_note_template("傾招募 (2分)")
    assert "講左3Q" not in get_note_template("見面 (1分)")


def test_stages():
    assert "Closing" in SALES_STAGES
    assert "落 Sales Kit" in SALES_STAGES
    assert "出 Code" in RECRUIT_STAGES
    assert "見經理" in RECRUIT_STAGES


def test_track_for_activity():
    assert track_for_activity("見面 (1分)") == TRACK_SALES
    assert track_for_activity("簽單 (5分)") == TRACK_SALES
    assert track_for_activity("傾招募 (2分)") == TRACK_RECRUIT
    assert track_for_activity("新人出code (8分)") == TRACK_RECRUIT


def test_compose_pipeline_note():
    note = compose_pipeline_note(
        track=TRACK_SALES,
        person="陳生",
        stage="Closing",
        next_action="約簽單",
        next_date="2026-10-20",
        factfind="1. 性格：外向",
    )
    assert "【做數｜Closing】陳生" in note
    assert "Next action: 約簽單" in note
    assert "跟進日期: 2026-10-20" in note
    assert "外向" in note


def test_due_and_upcoming_followups(monkeypatch):
    today = datetime.date(2026, 10, 15)
    rows = pd.DataFrame(
        [
            {
                "id": 1,
                "username": "Tim",
                "track": TRACK_SALES,
                "person": "A",
                "stage": "3Q",
                "next_action": "call",
                "next_date": "2026-10-14",
                "status": "open",
            },
            {
                "id": 2,
                "username": "Tim",
                "track": TRACK_RECRUIT,
                "person": "B",
                "stage": "見經理",
                "next_action": "Bring",
                "next_date": "2026-10-15",
                "status": "open",
            },
            {
                "id": 3,
                "username": "Tim",
                "track": TRACK_SALES,
                "person": "C",
                "stage": "Closing",
                "next_action": "sign",
                "next_date": "2026-10-18",
                "status": "open",
            },
            {
                "id": 4,
                "username": "Tim",
                "track": TRACK_SALES,
                "person": "D",
                "stage": "3Q",
                "next_action": "x",
                "next_date": "2026-10-10",
                "status": "done",
            },
            {
                "id": 5,
                "username": "Oscar",
                "track": TRACK_SALES,
                "person": "E",
                "stage": "3Q",
                "next_action": "y",
                "next_date": "2026-10-14",
                "status": "open",
            },
        ]
    )
    monkeypatch.setattr("tt_core.data.read_data", lambda *_a, **_k: rows.copy())

    due = get_due_followups("Tim", on_or_before=today)
    assert set(due["person"]) == {"A", "B"}

    upcoming = get_upcoming_followups("Tim", days=7, after=today)
    assert list(upcoming["person"]) == ["C"]
