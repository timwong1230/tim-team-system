"""Coach Tim — live read tools + offline coach."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tt_core.coach_tim import (  # noqa: E402
    COACH_MENU,
    MAX_TOOLS_PER_TURN,
    TOOL_DUE_FOLLOWUPS,
    TOOL_MEMBER_SNAPSHOT,
    TOOL_SEARCH_FOLLOWUP,
    TOOL_SEARCH_PROSPECTS,
    choose_tools,
    format_context_markdown,
    gather_live_context,
    mask_api_key,
    offline_reply,
    reply,
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
        "tool_hits": {},
    }
    base.update(over)
    return base


def test_menu_constant():
    assert "AI Tim" in COACH_MENU


def test_context_markdown_includes_extra10_and_due():
    md = format_context_markdown(_sample_ctx())
    assert "Extra 10 已開" in md
    assert "Sam" in md
    assert "本週活動：1/3" in md


def test_system_prompt_grounded():
    sp = system_prompt(_sample_ctx())
    assert "AI Tim" in sp
    assert "100,000" in sp or "100000" in sp.replace(",", "")
    assert "唔好估數" in sp or "唔好發明" in sp
    assert "Phase 1" not in sp
    assert "Phase 2" not in sp


def test_offline_reply_followup():
    r = offline_reply("幫我跟今日卡案", _sample_ctx())
    assert "Sam" in r
    assert "Fact finding" in r


def test_offline_reply_week():
    r = offline_reply("本週活動仲欠幾多", _sample_ctx())
    assert "1/3" in r or "欠" in r


def test_offline_meta_not_same_extra10_canned():
    """Complaints about identical answers must not dump Extra 10 priority again."""
    ctx = _sample_ctx(due=[], wk_count=3, wk_need=0, extra10_open=True)
    r = offline_reply("即係我同你講咩，你都答一樣嘅答案？", ctx)
    assert "分流" in r or "可以試" in r
    assert "盈聚 5pay" not in r


def test_offline_clarify_not_priority_template():
    ctx = _sample_ctx(due=[], wk_need=0, extra10_open=True)
    r = offline_reply("嗯", ctx)
    assert "具體" in r or "例如" in r
    assert "建議今日咁排" not in r


def test_offline_priority_only_when_asked():
    ctx = _sample_ctx(due=[], wk_need=0, extra10_open=True, prospects=[])
    r = offline_reply("今日最應該做咩？", ctx)
    assert "建議" in r or "排" in r
    assert "Extra 10" in r or "準客戶" in r or "冇逾期" in r


def test_welcome():
    w = welcome_message(_sample_ctx())
    assert "AI Tim" in w
    assert "1" in w  # due count
    assert "嵌喺" not in w
    assert "嵌入" not in w
    assert "Phase 1" not in w
    assert "打卡" in w or "跟進" in w


def test_choose_tools_limits_and_routes():
    week = choose_tools("本週活動仲欠幾多？")
    assert TOOL_MEMBER_SNAPSHOT in week
    assert len(week) <= MAX_TOOLS_PER_TURN

    due = choose_tools("今日最應該跟邊單？")
    assert TOOL_DUE_FOLLOWUPS in due or TOOL_SEARCH_FOLLOWUP in due

    prospect = choose_tools("準客戶 Ave 進度點？")
    assert TOOL_SEARCH_PROSPECTS in prospect

    default = choose_tools("你好")
    assert TOOL_MEMBER_SNAPSHOT in default
    assert TOOL_DUE_FOLLOWUPS in default
    assert len(default) <= MAX_TOOLS_PER_TURN


def test_gather_live_context_merges_tools():
    base = _sample_ctx()

    def fake_run(name, *, username, role="Member", query=""):
        if name == TOOL_MEMBER_SNAPSHOT:
            return {
                "ok": True,
                "tool": name,
                "context": {**base, "wk_count": 2, "wk_need": 1},
            }
        if name == TOOL_DUE_FOLLOWUPS:
            return {
                "ok": True,
                "tool": name,
                "count": 1,
                "rows": base["due"],
            }
        return {"ok": True, "tool": name, "count": 0, "rows": []}

    with patch("tt_core.coach_tim.run_tool", side_effect=fake_run):
        with patch(
            "tt_core.coach_tim.choose_tools",
            return_value=[TOOL_MEMBER_SNAPSHOT, TOOL_DUE_FOLLOWUPS],
        ):
            ctx, tools = gather_live_context(
                "Tim", "今日優先做咩", role="Member", base_ctx=base
            )
    assert tools == [TOOL_MEMBER_SNAPSHOT, TOOL_DUE_FOLLOWUPS]
    assert ctx["wk_count"] == 2
    assert ctx["due"][0]["person"] == "Sam"
    assert ctx["_tools_used"] == tools


def test_reply_returns_meta_and_refreshes():
    base = _sample_ctx()

    def fake_gather(username, user_text, *, role="Member", base_ctx=None):
        live = dict(base_ctx or base)
        live["wk_count"] = 3
        live["wk_need"] = 0
        live["_tools_used"] = [TOOL_MEMBER_SNAPSHOT]
        return live, [TOOL_MEMBER_SNAPSHOT]

    with patch("tt_core.coach_tim.gather_live_context", side_effect=fake_gather):
        with patch("tt_core.coach_tim._secret_openai_key", return_value=""):
            text, mode, meta = reply("本週活動仲欠幾多", [], base)
    assert mode == "offline"
    assert meta["tools_used"] == [TOOL_MEMBER_SNAPSHOT]
    assert "3/3" in text or "達標" in text


def test_offline_uses_tool_hits_for_named_case():
    ctx = _sample_ctx(
        tool_hits={
            "followups": [
                {
                    "person": "Ave",
                    "track": "做數",
                    "stage": "Concept",
                    "next_action": "約簽單",
                    "next_date": "2026-10-18",
                    "status": "open",
                }
            ],
            "prospects": [],
            "team": [],
            "stuck": [],
        }
    )
    r = offline_reply("幫我拆 Ave 呢單點跟", ctx)
    assert "Ave" in r
    assert "Concept" in r or "約簽單" in r


def test_mask_api_key():
    assert "sk-proj" in mask_api_key("sk-proj-abcdefghijklmnop")
    assert "…" in mask_api_key("sk-proj-abcdefghijklmnop")


def test_system_prompt_telegram_style():
    sp = system_prompt(_sample_ctx())
    assert "Telegram" in sp or "私人教練" in sp
    assert "Tim" in sp


def test_llm_provider_prefers_gemini():
    from tt_core import coach_tim as ct

    with patch.object(ct, "_secret_gemini_key", return_value="AIza-test"):
        with patch.object(ct, "_secret_openai_key", return_value="sk-test"):
            assert ct.llm_provider() == "gemini"
            assert ct.llm_configured() is True
    with patch.object(ct, "_secret_gemini_key", return_value=""):
        with patch.object(ct, "_secret_openai_key", return_value=""):
            assert ct.llm_provider() == "offline"


def test_reply_uses_gemini_when_configured():
    from tt_core import coach_tim as ct

    base = _sample_ctx()

    def fake_gather(username, user_text, *, role="Member", base_ctx=None):
        live = dict(base_ctx or base)
        live["_tools_used"] = [TOOL_MEMBER_SNAPSHOT]
        return live, [TOOL_MEMBER_SNAPSHOT]

    with patch.object(ct, "gather_live_context", side_effect=fake_gather):
        with patch.object(ct, "_secret_gemini_key", return_value="AIza-free"):
            with patch.object(ct, "_secret_openai_key", return_value=""):
                with patch.object(
                    ct, "gemini_chat", return_value="今日先跟 Sam，下一句約聽 concept。"
                ):
                    text, mode, meta = ct.reply("今日點做", [], base)
    assert mode == "gemini"
    assert "Sam" in text
    assert meta.get("provider") == "gemini"


def test_gemini_contents_alternates_roles():
    from tt_core.coach_tim import _gemini_contents

    contents = _gemini_contents(
        [
            {"role": "assistant", "content": "你好"},
            {"role": "assistant", "content": "第二句"},
            {"role": "user", "content": "今日點做"},
        ]
    )
    roles = [c["role"] for c in contents]
    assert roles[0] == "user"
    assert roles[-1] == "user"
    # no consecutive duplicates
    for a, b in zip(roles, roles[1:]):
        assert a != b


def test_app_wired():
    src = (_ROOT / "app.py").read_text(encoding="utf-8")
    assert "🧠 AI Tim" in src
    assert "page_coach_tim" in src
    assert "coach_tim_pending" in src
    assert "問 AI Tim" in src
    assert "嵌喺 M+2" not in src
    assert "嵌入 M+2" not in src
    assert "Phase 1 只俾建議" not in src
    assert "save_gemini_api_key" in src
    assert "接通 AI 教練" in src
    assert "免費 AI（Gemini）" not in src
    assert "通常 `AIza…`" not in src  # AQ auth keys are valid now
    assert "TOOL_CATALOG" in src
    assert "x-goog-api-key" in (_ROOT / "tt_core" / "coach_tim.py").read_text(
        encoding="utf-8"
    )


if __name__ == "__main__":
    test_menu_constant()
    test_context_markdown_includes_extra10_and_due()
    test_system_prompt_grounded()
    test_offline_reply_followup()
    test_offline_reply_week()
    test_welcome()
    test_choose_tools_limits_and_routes()
    test_gather_live_context_merges_tools()
    test_reply_returns_meta_and_refreshes()
    test_offline_uses_tool_hits_for_named_case()
    test_app_wired()
    print("coach tim phase2 ok")
