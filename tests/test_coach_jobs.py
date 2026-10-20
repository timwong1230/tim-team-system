"""Background AI Tim jobs — leave the page while answering."""

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


def test_app_uses_background_jobs_not_blocking_spinner_reply():
    src = (_ROOT / "app.py").read_text(encoding="utf-8")
    page = src[src.index("def page_coach_tim") : src.index("def page_checkin")]
    assert "start_reply_job" in page
    assert "importlib.reload" not in page
    assert "sync_job_into_session" in page
    assert "背景諗緊" in page
    assert "_poll_aitim_job" in src


def test_gemini_chat_limits_model_cascade():
    src = (_ROOT / "tt_core" / "coach_tim.py").read_text(encoding="utf-8")
    fn = src[src.index("def gemini_chat") : src.index("def test_ai_connection")]
    assert "model_candidates = model_candidates[:3]" in fn
    assert "per_try_timeout" in fn
    assert "deadline" in fn
