"""Background AI Tim jobs — leave the page while answering; never lock forever."""

from __future__ import annotations

import sys
import time
from pathlib import Path
from unittest.mock import patch

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def test_start_reply_job_runs_in_background():
    from tt_core import coach_jobs as cj

    cj.clear_job("Tim")

    def fake_reply(user_text, history, ctx):
        time.sleep(0.12)
        return ("背景答案：" + user_text, "offline", {"tools_used": []})

    with patch("tt_core.coach_tim.reply", side_effect=fake_reply):
        job = cj.start_reply_job(
            username="Tim",
            role="Member",
            user_text="今日點做",
            history=[],
            ctx={"username": "Tim", "role": "Member"},
        )
        assert job["status"] == "running"
        again = cj.start_reply_job(
            username="Tim",
            role="Member",
            user_text="另一條",
            history=[],
            ctx={"username": "Tim"},
        )
        assert again["id"] == job["id"]

        deadline = time.time() + 3
        while time.time() < deadline:
            snap = cj.get_job("Tim")
            if snap and snap.get("status") == "done":
                break
            time.sleep(0.05)
        snap = cj.get_job("Tim")
        assert snap is not None
        assert snap["status"] == "done"
        assert "背景答案" in snap["answer"]
    cj.clear_job("Tim")


def test_stale_running_job_auto_expires():
    from tt_core import coach_jobs as cj

    cj.clear_job("Stuck")
    with cj._LOCK:
        cj._JOBS["Stuck"] = {
            "id": "stuck1",
            "username": "Stuck",
            "role": "Member",
            "question": "點樣跟 Elaine",
            "status": "running",
            "answer": "",
            "mode": "",
            "meta": {},
            "error": "",
            "started_at": time.time() - (cj.STALE_RUNNING_SEC + 5),
            "finished_at": None,
            "synced": False,
            "_ctx": {"username": "Stuck", "due": []},
        }
    snap = cj.get_job("Stuck")
    assert snap is not None
    assert snap["status"] == "done"
    assert "逾時" in snap["answer"] or "教練" in snap["answer"]
    cj.clear_job("Stuck")


def test_cancel_job_unlocks():
    from tt_core import coach_jobs as cj

    cj.clear_job("CancelMe")
    with cj._LOCK:
        cj._JOBS["CancelMe"] = {
            "id": "c1",
            "username": "CancelMe",
            "status": "running",
            "question": "hi",
            "started_at": time.time(),
            "synced": False,
            "_ctx": {"username": "CancelMe"},
            "answer": "",
            "mode": "",
            "meta": {},
            "error": "",
            "finished_at": None,
            "role": "Member",
        }
    assert cj.cancel_job("CancelMe") is True
    snap = cj.get_job("CancelMe")
    assert snap["status"] == "done"
    assert "取消" in snap["answer"] or "教練" in snap["answer"]
    cj.clear_job("CancelMe")


def test_hard_timeout_on_hung_reply():
    from tt_core import coach_jobs as cj

    cj.clear_job("Hang")
    # Force a tiny timeout for the test
    with patch.object(cj, "JOB_TIMEOUT_SEC", 0.2):
        with patch.object(cj, "STALE_RUNNING_SEC", 30):

            def hang_reply(user_text, history, ctx):
                time.sleep(2.0)
                return ("should not see", "gemini", {})

            with patch("tt_core.coach_tim.reply", side_effect=hang_reply):
                cj.start_reply_job(
                    username="Hang",
                    role="Member",
                    user_text="點樣跟 Elaine",
                    history=[],
                    ctx={"username": "Hang", "due": []},
                )
                deadline = time.time() + 3
                while time.time() < deadline:
                    snap = cj.get_job("Hang")
                    if snap and snap.get("status") == "done":
                        break
                    time.sleep(0.05)
                snap = cj.get_job("Hang")
                assert snap is not None
                assert snap["status"] == "done"
                assert "should not see" not in snap["answer"]
                assert "逾時" in snap["answer"] or "教練" in snap["answer"]
    cj.clear_job("Hang")


def test_sync_job_into_session_appends_assistant():
    import streamlit as st

    from tt_core import coach_jobs as cj

    cj.clear_job("Oscar")
    with cj._LOCK:
        cj._JOBS["Oscar"] = {
            "id": "abc123",
            "username": "Oscar",
            "status": "done",
            "answer": "建議先跟 Sam",
            "mode": "gemini",
            "meta": {},
            "synced": False,
            "question": "今日點做",
        }

    state = {"coach_tim_messages": [{"role": "user", "content": "今日點做"}]}
    with patch.object(st, "session_state", state):
        ok = cj.sync_job_into_session("Oscar")
    assert ok is True
    assert state["coach_tim_messages"][-1]["role"] == "assistant"
    assert "Sam" in state["coach_tim_messages"][-1]["content"]
    with patch.object(st, "session_state", state):
        assert cj.sync_job_into_session("Oscar") is False
    cj.clear_job("Oscar")


def test_app_has_cancel_and_no_disabled_lock():
    src = (_ROOT / "app.py").read_text(encoding="utf-8")
    page = src[src.index("def page_coach_tim") : src.index("def page_checkin")]
    assert "cancel_job" in page
    assert "取消等待" in page
    assert "disabled=job_running" not in page
    assert "start_reply_job" in page


def test_offline_followup_prefers_named_case():
    from tt_core.coach_tim import offline_reply

    ctx = {
        "username": "Tim",
        "role": "Member",
        "due": [
            {
                "person": "Sam",
                "track": "做數",
                "stage": "Fact finding",
                "next_action": "約聽concept",
                "next_date": "2026-10-17",
            },
            {
                "person": "Elaine",
                "track": "做數",
                "stage": "Concept",
                "next_action": "約簽單",
                "next_date": "2026-10-20",
            },
        ],
        "upcoming": [],
        "prospects": [],
        "tool_hits": {},
        "wk_need": 0,
        "wk_count": 3,
        "wk_min": 3,
    }
    r = offline_reply("點樣跟Elaine個case?", ctx)
    assert "Elaine" in r
    assert "約簽單" in r or "Concept" in r
