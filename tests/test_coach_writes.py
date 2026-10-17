"""AI Tim Phase 3 — confirm-gated writes."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tt_core.coach_writes import (  # noqa: E402
    ACTION_CHECKIN,
    ACTION_UPD_FYC,
    build_pending,
    execute_pending,
    factfind_missing,
    factfind_template,
    is_admin,
    parse_action_from_reply,
    validate_checkin_payload,
)
from tt_core.constants import TEMPLATE_FACTFIND  # noqa: E402


def _filled_factfind() -> str:
    text = TEMPLATE_FACTFIND
    for n in range(1, 16):
        # put an answer after each numbered line
        text = text.replace(f"{n}.", f"{n}.", 1)
    # Replace empty answer slots: after each question marker insert answer
    lines = []
    for line in text.splitlines():
        lines.append(line)
        if line.strip()[:2].rstrip(".").isdigit() or line.strip().startswith(
            tuple(f"{i}." for i in range(1, 16))
        ):
            if not line.strip().endswith(("：", ":")) or True:
                pass
    # Simpler: rebuild with answers
    parts = ["【Fact find background】", "Name: Chan"]
    labels = [
        "1. 性格",
        "2. 工作情況（職業／人工／年資）",
        "3. 家庭現況（家庭人物關係圖）",
        "4. 興趣",
        "5. 人生最大經歷／轉捩點",
        "6. 未來目標／想做的事情",
        "7. 未來關心／擔心的事情",
        "8. ⚠️ prepare 切入主題角度 — 用咩切入？",
        "9. 已買保險？（病歷紀錄）",
        "10. 邊間公司",
        "11. 同 agent 關係",
        "12. 落咗咩 sales concept",
        "13. 點跟進客人 follow up",
        "14. 經過今日之後嘅了解，你哋彼此嘅熟悉程度",
        "15. ⚠️ 約 next appointment／活動：日子",
    ]
    for lab in labels:
        parts.append(lab + "：")
        parts.append(f"答{lab[:2]}")
    return "\n\n".join(parts)


def test_is_admin_leader_only():
    assert is_admin("Leader") is True
    assert is_admin("Member") is False
    assert is_admin("Member", "Admin") is True


def test_factfind_template_incomplete():
    miss = factfind_missing(factfind_template())
    assert len(miss) == 15


def test_factfind_complete():
    miss = factfind_missing(_filled_factfind())
    assert miss == []


def test_checkin_requires_all_fields():
    ok, missing = validate_checkin_payload(
        {
            "track": "做數",
            "person": "",
            "act_date": "",
            "stage": "",
            "next_action": "",
            "next_date": "",
            "factfind": factfind_template(),
        }
    )
    assert ok is False
    assert any("名字" in m for m in missing)
    assert any("見面日期" in m for m in missing)
    assert any("Fact find" in m for m in missing)


def test_checkin_ready_when_complete():
    payload = {
        "track": "做數",
        "act_type": "見面 (1分)",
        "person": "Ave",
        "act_date": "2026-10-17",
        "stage": "Fact finding",
        "next_action": "約聽 concept",
        "next_date": "2026-10-20",
        "factfind": _filled_factfind(),
    }
    ok, missing = validate_checkin_payload(payload)
    assert ok is True, missing
    assert missing == []


def test_member_cannot_propose_fyc_ready():
    pending = build_pending(
        ACTION_UPD_FYC,
        {"target_user": "Tim", "month": "2026-10", "amount": 1000},
        username="Tim",
        role="Member",
    )
    assert pending["ready"] is False
    assert any("Admin" in m or "Leader" in m for m in pending["missing"])


def test_leader_can_propose_fyc():
    pending = build_pending(
        ACTION_UPD_FYC,
        {"target_user": "Tim", "month": "2026-10", "amount": 1000},
        username="Admin",
        role="Leader",
    )
    assert pending["ready"] is True


def test_execute_checkin_blocked_when_not_ready():
    pending = build_pending(
        ACTION_CHECKIN,
        {"person": "Ave"},
        username="Tim",
        role="Member",
    )
    result = execute_pending(pending)
    assert result["ok"] is False


def test_execute_checkin_calls_add_pipeline():
    payload = {
        "track": "做數",
        "act_type": "見面 (1分)",
        "person": "Ave",
        "act_date": "2026-10-17",
        "stage": "Fact finding",
        "next_action": "約聽 concept",
        "next_date": "2026-10-20",
        "factfind": _filled_factfind(),
    }
    pending = build_pending(
        ACTION_CHECKIN, payload, username="Tim", role="Member"
    )
    assert pending["ready"] is True
    with patch("tt_core.data.add_pipeline_checkin") as mock_add:
        result = execute_pending(pending)
    assert result["ok"] is True
    mock_add.assert_called_once()


def test_parse_action_fence():
    text = (
        "我提議咁打卡：\n"
        "```aitim-action\n"
        '{"type":"pipeline_checkin","person":"Ave","track":"做數",'
        '"act_date":"2026-10-17","stage":"Fact finding",'
        '"next_action":"約","next_date":"2026-10-20","factfind":"x"}\n'
        "```\n"
    )
    data = parse_action_from_reply(text)
    assert data is not None
    assert data["type"] == "pipeline_checkin"
    assert data["person"] == "Ave"


def test_app_has_phase3_ui():
    src = (_ROOT / "app.py").read_text(encoding="utf-8")
    assert "coach_tim_write_pending" in src
    assert "確認執行寫入" in src
    assert "開打卡待確認稿" in src
