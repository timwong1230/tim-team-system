"""AI Tim Phase 3 — confirm-gated write-backs into M+2.

Assumptions (product rules):
1. Only Leader/Admin may change FYC / recruit metrics.
2. Pipeline check-in requires: person name, meeting date, next action,
   follow-up date, stage, and all 15 Fact find answers before confirm.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import date, datetime
from typing import Any

from tt_core.constants import (
    RECRUIT_ACTIVITY_TYPES,
    RECRUIT_STAGES,
    SALES_ACTIVITY_TYPES,
    SALES_STAGES,
    TEMPLATE_FACTFIND,
    TRACK_RECRUIT,
    TRACK_SALES,
)

ACTION_CHECKIN = "pipeline_checkin"
ACTION_UPD_FYC = "admin_upd_fyc"
ACTION_UPD_RECRUIT = "admin_upd_recruit"
ACTION_MARK_DONE = "mark_followup_done"

# 15 Fact find question anchors (order matters)
FACTFIND_MARKERS = [
    (1, "1. 性格"),
    (2, "2. 工作情況"),
    (3, "3. 家庭現況"),
    (4, "4. 興趣"),
    (5, "5. 人生最大經歷"),
    (6, "6. 未來目標"),
    (7, "7. 未來關心"),
    (8, "8."),
    (9, "9. 已買保險"),
    (10, "10. 邊間公司"),
    (11, "11. 同 agent"),
    (12, "12. 落咗咩"),
    (13, "13. 點跟進"),
    (14, "14. 經過今日"),
    (15, "15."),
]

_ACTION_FENCE_RE = re.compile(
    r"```(?:aitim-action|json)?\s*(\{.*?\})\s*```",
    re.DOTALL | re.IGNORECASE,
)


def is_admin(role: str | None, username: str | None = None) -> bool:
    """Admin for metrics writes = Leader role (includes Admin user)."""
    if str(role or "") == "Leader":
        return True
    return str(username or "").strip().lower() == "admin"


def factfind_template() -> str:
    return TEMPLATE_FACTFIND


def _slice_answers(text: str) -> dict[int, str]:
    """Split factfind text into {qnum: answer_body}."""
    raw = text or ""
    positions: list[tuple[int, int]] = []
    for num, marker in FACTFIND_MARKERS:
        idx = raw.find(marker)
        if idx < 0:
            # softer match: "1." at line start
            m = re.search(rf"(?m)^\s*{num}[\.、]", raw)
            idx = m.start() if m else -1
        if idx >= 0:
            positions.append((num, idx))
    positions.sort(key=lambda x: x[1])
    out: dict[int, str] = {}
    for i, (num, start) in enumerate(positions):
        end = positions[i + 1][1] if i + 1 < len(positions) else len(raw)
        chunk = raw[start:end]
        # drop the question label line
        lines = chunk.splitlines()
        body = "\n".join(lines[1:] if lines else []).strip()
        # also strip trailing "：" leftovers on same line after marker
        if not body and "：" in chunk:
            body = chunk.split("：", 1)[-1].strip()
        elif not body and ":" in chunk:
            body = chunk.split(":", 1)[-1].strip()
        out[num] = body
    return out


def factfind_missing(text: str) -> list[int]:
    """Return question numbers (1–15) that still lack an answer."""
    answers = _slice_answers(text)
    missing = []
    for num, _ in FACTFIND_MARKERS:
        ans = (answers.get(num) or "").strip()
        # treat placeholder-only / empty as missing
        if not ans or ans in ("日子：", "日子:", "—", "-"):
            missing.append(num)
    # If template structure missing entirely, all 15 missing
    if len(answers) < 8:
        return list(range(1, 16))
    return missing


def _parse_date(val: Any) -> str | None:
    if val is None or val == "":
        return None
    if isinstance(val, (date, datetime)):
        return val.date().isoformat() if isinstance(val, datetime) else val.isoformat()
    s = str(val).strip()[:10]
    try:
        return date.fromisoformat(s).isoformat()
    except Exception:
        return None


def validate_checkin_payload(payload: dict[str, Any]) -> tuple[bool, list[str]]:
    """Enforce Phase 3 check-in completeness rules."""
    missing: list[str] = []
    person = str(payload.get("person") or "").strip()
    if not person:
        missing.append("名字（客戶／準增員）")

    act_date = _parse_date(payload.get("act_date") or payload.get("meeting_date"))
    if not act_date:
        missing.append("見面日期")

    next_action = str(payload.get("next_action") or "").strip()
    if not next_action:
        missing.append("Next action")

    next_date = _parse_date(payload.get("next_date"))
    if not next_date:
        missing.append("跟進日期")

    stage = str(payload.get("stage") or "").strip()
    if not stage:
        missing.append("階段")
    else:
        track = str(payload.get("track") or TRACK_SALES).strip()
        allowed = SALES_STAGES if track == TRACK_SALES else RECRUIT_STAGES
        if stage not in allowed:
            missing.append(f"階段（要係：{'／'.join(allowed)}）")

    ff = str(payload.get("factfind") or "")
    ff_miss = factfind_missing(ff)
    if ff_miss:
        missing.append("Fact find 第 " + "、".join(str(n) for n in ff_miss) + " 條")

    track = str(payload.get("track") or TRACK_SALES).strip()
    if track not in (TRACK_SALES, TRACK_RECRUIT):
        missing.append("軌道（做數／招募）")

    act_type = str(payload.get("act_type") or "").strip()
    types = SALES_ACTIVITY_TYPES if track == TRACK_SALES else RECRUIT_ACTIVITY_TYPES
    if not act_type:
        # default later if ready; still flag if types empty
        pass
    elif act_type not in types:
        missing.append(f"活動種類（要係：{'／'.join(types)}）")

    return (len(missing) == 0), missing


def normalize_checkin_payload(payload: dict[str, Any]) -> dict[str, Any]:
    p = dict(payload or {})
    track = str(p.get("track") or TRACK_SALES).strip()
    if track not in (TRACK_SALES, TRACK_RECRUIT):
        track = TRACK_SALES
    p["track"] = track
    types = SALES_ACTIVITY_TYPES if track == TRACK_SALES else RECRUIT_ACTIVITY_TYPES
    if not str(p.get("act_type") or "").strip():
        p["act_type"] = types[0]
    p["act_date"] = _parse_date(p.get("act_date") or p.get("meeting_date")) or ""
    p["next_date"] = _parse_date(p.get("next_date")) or ""
    p["person"] = str(p.get("person") or "").strip()
    p["stage"] = str(p.get("stage") or "").strip()
    p["next_action"] = str(p.get("next_action") or "").strip()
    ff = str(p.get("factfind") or "").strip()
    p["factfind"] = ff if ff else factfind_template()
    return p


def build_pending(
    action_type: str,
    payload: dict[str, Any],
    *,
    username: str,
    role: str,
) -> dict[str, Any]:
    """Create a pending confirm card (not executed yet)."""
    if action_type == ACTION_CHECKIN:
        payload = normalize_checkin_payload(payload)
        ready, missing = validate_checkin_payload(payload)
    elif action_type in (ACTION_UPD_FYC, ACTION_UPD_RECRUIT):
        if not is_admin(role, username):
            return {
                "id": str(uuid.uuid4())[:8],
                "type": action_type,
                "payload": payload,
                "ready": False,
                "missing": ["只有 Admin／Leader 可以改業績／招募數字"],
                "username": username,
                "role": role,
            }
        missing = []
        if action_type == ACTION_UPD_FYC:
            if not str(payload.get("target_user") or "").strip():
                missing.append("對象同事")
            if not str(payload.get("month") or "").strip():
                missing.append("月份（YYYY-MM）")
            try:
                float(payload.get("amount"))
            except Exception:
                missing.append("FYC 金額")
        else:
            if not str(payload.get("target_user") or "").strip():
                missing.append("對象同事")
            try:
                int(float(payload.get("amount")))
            except Exception:
                missing.append("招募人數")
        ready = len(missing) == 0
    elif action_type == ACTION_MARK_DONE:
        ready = bool(str(payload.get("followup_id") or "").strip())
        missing = [] if ready else ["跟進個案 id"]
    else:
        ready, missing = False, [f"未知動作：{action_type}"]

    return {
        "id": str(uuid.uuid4())[:8],
        "type": action_type,
        "payload": payload,
        "ready": ready,
        "missing": missing,
        "username": username,
        "role": role,
    }


def execute_pending(pending: dict[str, Any]) -> dict[str, Any]:
    """Execute a ready pending action. Raises / returns ok=False on failure."""
    if not pending or not pending.get("ready"):
        return {
            "ok": False,
            "error": "未齊資料，唔可以執行："
            + "、".join(pending.get("missing") or ["未完成"]),
        }

    action = pending.get("type")
    payload = pending.get("payload") or {}
    username = str(pending.get("username") or "")
    role = str(pending.get("role") or "")

    try:
        if action == ACTION_CHECKIN:
            from tt_core.data import add_pipeline_checkin

            add_pipeline_checkin(
                username,
                act_date=payload["act_date"],
                act_type=payload["act_type"],
                track=payload["track"],
                person=payload["person"],
                stage=payload["stage"],
                next_action=payload["next_action"],
                next_date=payload["next_date"],
                factfind=payload["factfind"],
            )
            return {
                "ok": True,
                "message": (
                    f"已打卡：{payload['person']}（{payload['track']}｜{payload['stage']}）"
                    f" · 跟進 {payload['next_date']}"
                ),
            }

        if action == ACTION_UPD_FYC:
            if not is_admin(role, username):
                return {"ok": False, "error": "只有 Admin／Leader 可以改業績"}
            from tt_core.data import upd_fyc

            target = str(payload["target_user"]).strip()
            month = str(payload["month"]).strip()
            amount = float(payload["amount"])
            upd_fyc(target, month, amount, source="ai_tim")
            return {
                "ok": True,
                "message": f"已更新 {target} {month} FYC = ${amount:,.0f}",
            }

        if action == ACTION_UPD_RECRUIT:
            if not is_admin(role, username):
                return {"ok": False, "error": "只有 Admin／Leader 可以改招募數字"}
            from tt_core.data import upd_rec

            target = str(payload["target_user"]).strip()
            amount = int(float(payload["amount"]))
            upd_rec(target, amount)
            return {
                "ok": True,
                "message": f"已更新 {target} 招募人數 = {amount}",
            }

        if action == ACTION_MARK_DONE:
            from tt_core.data import mark_followup_done

            ok = mark_followup_done(payload.get("followup_id"))
            return {
                "ok": bool(ok),
                "message": "已標示跟進完成" if ok else "更新失敗",
            }

        return {"ok": False, "error": f"未知動作：{action}"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}


def parse_action_from_reply(text: str) -> dict[str, Any] | None:
    """Extract ```aitim-action {json}``` block from model output."""
    if not text:
        return None
    m = _ACTION_FENCE_RE.search(text)
    raw = None
    if m:
        raw = m.group(1)
    else:
        # bare JSON with "type": "pipeline_checkin"
        m2 = re.search(
            r"\{[^{}]*\"type\"\s*:\s*\"(?:pipeline_checkin|admin_upd_fyc|admin_upd_recruit|mark_followup_done)\"[^{}]*\}",
            text,
            re.DOTALL,
        )
        if m2:
            raw = m2.group(0)
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except Exception:
        return None
    if not isinstance(data, dict) or not data.get("type"):
        return None
    return data


def strip_action_fence(text: str) -> str:
    """Remove action JSON fence from user-visible reply."""
    if not text:
        return text
    return _ACTION_FENCE_RE.sub("", text).strip()


def write_rules_for_prompt(*, role: str, username: str) -> str:
    admin = is_admin(role, username)
    admin_line = (
        "你可以提議改同事 FYC／招募數字（type=admin_upd_fyc / admin_upd_recruit），但仍要用戶確認。"
        if admin
        else "你唔可以改業績／招募數字；若有人要求，說明只有 Admin／Leader 可以。"
    )
    return f"""
【寫入規則 Phase 3 — 必須遵守】
1. 你唔會直接改系統。只可以提議寫入，用以下 JSON 圍欄（唔好省略欄位）：
```aitim-action
{{"type":"pipeline_checkin","track":"做數","act_type":"見面 (1分)","person":"名","act_date":"YYYY-MM-DD","stage":"Fact finding","next_action":"...","next_date":"YYYY-MM-DD","factfind":"完整 15 條答覆"}}
```
2. 打卡（pipeline_checkin）必須齊：名字、見面日期 act_date、Next action、跟進日期 next_date、階段 stage、Fact find 15 條全部有答。未齊就繼續問用戶補料，唔好話已經打咗卡。
3. {admin_line}
4. 階段只可以用：做數 {SALES_STAGES}；招募 {RECRUIT_STAGES}。
5. 用戶確認前，回覆用「提議／待確認」字眼，唔好講「已寫入」。
"""


def summarize_pending(pending: dict[str, Any]) -> str:
    if not pending:
        return ""
    t = pending.get("type")
    p = pending.get("payload") or {}
    if t == ACTION_CHECKIN:
        lines = [
            f"**待確認打卡**（{'✅ 可執行' if pending.get('ready') else '❌ 未齊料'}）",
            f"- 軌道：{p.get('track')}｜活動：{p.get('act_type')}",
            f"- 名字：{p.get('person') or '（欠）'}",
            f"- 見面日期：{p.get('act_date') or '（欠）'}",
            f"- 階段：{p.get('stage') or '（欠）'}",
            f"- Next action：{p.get('next_action') or '（欠）'}",
            f"- 跟進日期：{p.get('next_date') or '（欠）'}",
        ]
        if pending.get("missing"):
            lines.append("- 仲欠：" + "、".join(pending["missing"]))
        return "\n".join(lines)
    if t == ACTION_UPD_FYC:
        return (
            f"**待確認改 FYC**（Admin）：{p.get('target_user')} "
            f"{p.get('month')} → ${p.get('amount')}"
        )
    if t == ACTION_UPD_RECRUIT:
        return (
            f"**待確認改招募**（Admin）：{p.get('target_user')} → {p.get('amount')} 人"
        )
    return f"待確認動作：{t}"
