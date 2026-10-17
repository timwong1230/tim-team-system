"""Coach Tim Phase 1 — context formatting + offline coach."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tt_core.coach_tim import (  # noqa: E402
    COACH_MENU,
    format_context_markdown,
    offline_reply,
    system_prompt,
    welcome_message,
)


def _sample_ctx(**over):
    base = {
        "username": "Tim",
        "role": "Member",
        "ytd_fyc": 100_000,
        "extra10_open": True,
        "extra10_threshold": 88_000,
        "extra10_remaining": 0,
        "mdrt_progress": 200_000,
        "mdrt_pct": 39.0,
        "mdrt_remaining": 312_800,
        "mdrt_target": 512_800,
        "wk_count": 1,
        "wk_score": 3,
        "wk_min": 3,
        "wk_need": 2,
        "recruit": 1,
        "due": [
            {
                "person": "Sam",
                "track": "做數",
                "stage": "Fact finding",
                "next_action": "約聽concept",
                "next_date": "2026-10-17",
                "status": "open",
            }
        ],
        "upcoming": [],
        "prospects": [{"name": "Sam", "fyc": 10000, "products": "醫家保"}],
    }
    base.update(over)
    return base


def test_menu_constant():
    assert "Coach Tim" in COACH_MENU


def test_context_markdown_includes_extra10_and_due():
    md = format_context_markdown(_sample_ctx())
    assert "Extra 10 已開" in md
    assert "Sam" in md
    assert "本週活動：1/3" in md


def test_system_prompt_grounded():
    sp = system_prompt(_sample_ctx())
    assert "Coach Tim" in sp
    assert "100,000" in sp or "100000" in sp.replace(",", "")
    assert "唔好估數" in sp or "唔好發明" in sp


def test_offline_reply_followup():
    r = offline_reply("幫我跟今日卡案", _sample_ctx())
    assert "Sam" in r
    assert "Fact finding" in r


def test_offline_reply_week():
    r = offline_reply("本週活動仲欠幾多", _sample_ctx())
    assert "1/3" in r or "欠" in r


def test_welcome():
    w = welcome_message(_sample_ctx())
    assert "Coach Tim" in w
    assert "1" in w  # due count
    assert "嵌喺" not in w
    assert "嵌入" not in w
    assert "Phase 1" not in w


def test_system_prompt_no_phase_label():
    sp = system_prompt(_sample_ctx())
    assert "Phase 1" not in sp


def test_app_wired():
    src = (_ROOT / "app.py").read_text(encoding="utf-8")
    assert "🧠 Coach Tim" in src
    assert "page_coach_tim" in src
    assert "coach_tim_pending" in src
    assert "問 Coach Tim" in src
    assert "嵌喺 M+2" not in src
    assert "嵌入 M+2" not in src
    assert "Phase 1 只俾建議" not in src


if __name__ == "__main__":
    test_menu_constant()
    test_context_markdown_includes_extra10_and_due()
    test_system_prompt_grounded()
    test_offline_reply_followup()
    test_offline_reply_week()
    test_welcome()
    test_app_wired()
    print("coach tim phase1 ok")
