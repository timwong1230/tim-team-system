"""Coach Tim AI — Phase 1: context from M+2 + chat (OpenAI or offline)."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from tt_core.constants import MDRT_TARGET, Q1_TARGET, WEEKLY_MIN_ACTS

COACH_MENU = "🧠 Coach Tim"
DEFAULT_MODEL = "gpt-4o-mini"


def _secret_openai_key() -> str:
    try:
        import streamlit as st

        if "openai" in st.secrets:
            block = st.secrets["openai"]
            if isinstance(block, dict) or hasattr(block, "get"):
                for k in ("api_key", "key", "OPENAI_API_KEY"):
                    v = block.get(k) if hasattr(block, "get") else None
                    if v:
                        return str(v).strip()
            elif block:
                return str(block).strip()
        if "coach_tim" in st.secrets:
            block = st.secrets["coach_tim"]
            for k in ("api_key", "openai_api_key", "key"):
                v = block.get(k) if hasattr(block, "get") else None
                if v:
                    return str(v).strip()
        for k in ("OPENAI_API_KEY", "openai_api_key"):
            if k in st.secrets and st.secrets[k]:
                return str(st.secrets[k]).strip()
    except Exception:
        pass
    return ""


def _secret_model() -> str:
    try:
        import streamlit as st

        if "coach_tim" in st.secrets and st.secrets["coach_tim"].get("model"):
            return str(st.secrets["coach_tim"]["model"]).strip()
        if "openai" in st.secrets and hasattr(st.secrets["openai"], "get"):
            m = st.secrets["openai"].get("model")
            if m:
                return str(m).strip()
    except Exception:
        pass
    return DEFAULT_MODEL


def llm_configured() -> bool:
    return bool(_secret_openai_key())


def build_coach_context(username: str, *, role: str = "Member") -> dict[str, Any]:
    """Pull live M+2 snapshot for Coach Tim system prompt."""
    from tt_core.data import (
        get_due_followups,
        get_member_snapshot,
        get_upcoming_followups,
        mdrt_card_metrics,
    )

    snap = get_member_snapshot(username) if role == "Member" else get_member_snapshot(username)
    # Leaders may not be in Member sheet — still try snapshot
    try:
        mdrt = mdrt_card_metrics(username)
    except Exception:
        mdrt = {
            "mdrt_progress": 0,
            "mdrt_pct": 0,
            "mdrt_remaining": MDRT_TARGET,
            "mdrt_met": False,
        }

    due = get_due_followups(username)
    upcoming = get_upcoming_followups(username, days=7)

    def _fu_rows(df, limit: int = 8) -> list[dict]:
        rows = []
        if df is None or getattr(df, "empty", True):
            return rows
        for _, r in df.head(limit).iterrows():
            rows.append(
                {
                    "person": str(r.get("person") or ""),
                    "track": str(r.get("track") or ""),
                    "stage": str(r.get("stage") or ""),
                    "next_action": str(r.get("next_action") or ""),
                    "next_date": str(r.get("next_date") or "")[:10],
                    "status": str(r.get("status") or ""),
                }
            )
        return rows

    ytd = float(snap.get("fyc") or 0)
    extra10_open = ytd >= float(Q1_TARGET)
    wk_count = int(snap.get("wk_count") or 0)
    wk_need = max(WEEKLY_MIN_ACTS - wk_count, 0)

    prospects_brief: list[dict] = []
    try:
        from tt_core import prospects as pr

        pdf = pr.get_prospects(username=username, year=pr.current_year())
        if pdf is not None and not pdf.empty:
            sales = pdf[pdf["list_type"] == pr.LIST_SALES].head(5)
            for _, r in sales.iterrows():
                prospects_brief.append(
                    {
                        "name": str(r.get("name") or ""),
                        "fyc": float(r.get("fyc") or 0),
                        "products": pr.display_products(r.get("selling_products"), ytd_fyc=ytd)[:120],
                    }
                )
    except Exception:
        pass

    return {
        "username": username,
        "role": role,
        "ytd_fyc": ytd,
        "extra10_open": extra10_open,
        "extra10_threshold": float(Q1_TARGET),
        "extra10_remaining": max(float(Q1_TARGET) - ytd, 0.0),
        "mdrt_progress": float(mdrt.get("mdrt_progress") or snap.get("mdrt_progress") or 0),
        "mdrt_pct": float(mdrt.get("mdrt_pct") or snap.get("mdrt_pct") or 0),
        "mdrt_remaining": float(mdrt.get("mdrt_remaining") or snap.get("mdrt_remaining") or 0),
        "mdrt_target": float(MDRT_TARGET),
        "wk_count": wk_count,
        "wk_score": int(snap.get("wk_score") or 0),
        "wk_min": int(WEEKLY_MIN_ACTS),
        "wk_need": wk_need,
        "recruit": int(snap.get("recruit") or 0),
        "due": _fu_rows(due),
        "upcoming": _fu_rows(upcoming),
        "prospects": prospects_brief,
    }


def format_context_markdown(ctx: dict[str, Any]) -> str:
    """Human-readable briefing shown in UI."""
    lines = [
        f"**{ctx.get('username')}**（{ctx.get('role')}）",
        f"- YTD FYC：${ctx.get('ytd_fyc', 0):,.0f}"
        + (
            " · **Extra 10 已開**"
            if ctx.get("extra10_open")
            else f" · Extra 10 尚欠 ${ctx.get('extra10_remaining', 0):,.0f}"
        ),
        f"- 2027 MDRT：${ctx.get('mdrt_progress', 0):,.0f}"
        f"（{ctx.get('mdrt_pct', 0):.0f}%）· 尚欠 ${ctx.get('mdrt_remaining', 0):,.0f}",
        f"- 本週活動：{ctx.get('wk_count', 0)}/{ctx.get('wk_min', WEEKLY_MIN_ACTS)}"
        + (f" · 仲欠 **{ctx.get('wk_need')}** 次" if ctx.get("wk_need") else " · 達標"),
        f"- 招募人數：{ctx.get('recruit', 0)}",
    ]
    due = ctx.get("due") or []
    if due:
        lines.append(f"- **今日要跟（{len(due)}）**：")
        for d in due[:6]:
            lines.append(
                f"  - {d['person']}（{d['track']}｜{d['stage']}）"
                f" → {d['next_action'] or '—'} · {d['next_date']}"
            )
    else:
        lines.append("- 今日要跟：冇逾期／今日案")
    ups = ctx.get("upcoming") or []
    if ups:
        lines.append(f"- 未來 7 日：{len(ups)} 宗")
    pros = ctx.get("prospects") or []
    if pros:
        lines.append("- 準客戶（最近）：")
        for p in pros[:4]:
            lines.append(f"  - {p['name']} · FYC ${p['fyc']:,.0f}")
    return "\n".join(lines)


def system_prompt(ctx: dict[str, Any]) -> str:
    briefing = format_context_markdown(ctx)
    return f"""你係 Coach Tim——TIM TEAM（M+2）嘅教練助手。用香港粵語為主、間中書面語，直接、務實、鼓勵但不吹水。

你而家喺 M+2 管理系統入面，已經讀到呢位同事嘅即時數據（唔好估數，以下係真相）：

{briefing}

職責：
1. 幫佢決定「而家最緊要做邊一件」——優先清卡案／今日要跟，再補本週活動。
2. 跟進建議要具體：下一句點開、點約 next appointment、Fact find 邊條要補。
3. 業績／Extra 10／MDRT 只引用上面數字；唔好發明 FYC。
4. 回覆短：2–6 句＋最多 3 個 bullet action。
5. 如果問工具（醫療融資、準客戶、打卡），引導佢去 M+2 對應功能，並講點用。
6. 你而家係 Phase 1：只能讀數據、俾建議；唔好話自己已經改咗系統資料。
"""


def offline_reply(user_text: str, ctx: dict[str, Any]) -> str:
    """Useful coach without API key — grounded in injected context."""
    text = (user_text or "").strip()
    low = text.lower()
    due = ctx.get("due") or []
    wk_need = int(ctx.get("wk_need") or 0)
    name = ctx.get("username") or "你"

    # Priority coaching
    actions: list[str] = []
    if due:
        top = due[0]
        actions.append(
            f"今日優先跟 **{top['person']}**（{top['track']}｜{top['stage']}）："
            f"{top['next_action'] or '更新 Next action + 日期'}。"
        )
        if len(due) > 1:
            actions.append(f"其餘仲有 {len(due) - 1} 宗今日／逾期案，清完先再拓新客。")
    if wk_need > 0:
        actions.append(
            f"本週仲欠 **{wk_need}** 次活動（而家 {ctx.get('wk_count')}/{ctx.get('wk_min')}）——"
            "見面／傾保險／傾招募隨手打卡，避免罰款。"
        )
    if not ctx.get("extra10_open"):
        actions.append(
            f"Extra 10 尚欠 ${ctx.get('extra10_remaining', 0):,.0f} YTD；"
            "危疾／5年供 Saving／扣稅年金過咗門檻先有 ×1.1。"
        )
    else:
        actions.append("Extra 10 已開——賣危疾／盈聚 5pay／扣稅年金記得用準客戶名單自動計 FYC。")

    if any(k in text for k in ("跟", "卡案", "今日", "follow", "next")) and due:
        d = due[0]
        return (
            f"{name}，而家最緊要係清卡案，唔好散彈打鳥。\n\n"
            f"**第一單：{d['person']}**\n"
            f"- Track：{d['track']}｜階段：{d['stage']}\n"
            f"- Next：{d['next_action'] or '（未填）'} · 日期 {d['next_date']}\n"
            f"- 建議：今日聯絡，確認 next appointment；打卡時填好 Fact find。\n\n"
            f"清完再補本週活動"
            + (f"（仲欠 {wk_need} 次）。" if wk_need else "（本週已達標，做得好）。")
        )

    if any(k in low for k in ("mdrt", "業績", "fyc", "extra")):
        return (
            f"你嘅即時數字：\n"
            f"- YTD FYC **${ctx.get('ytd_fyc', 0):,.0f}**"
            + (
                "（Extra 10 已開）\n"
                if ctx.get("extra10_open")
                else f"（Extra 10 尚欠 ${ctx.get('extra10_remaining', 0):,.0f}）\n"
            )
            + f"- 2027 MDRT **${ctx.get('mdrt_progress', 0):,.0f}**"
            f"（{ctx.get('mdrt_pct', 0):.0f}%），尚欠 ${ctx.get('mdrt_remaining', 0):,.0f}\n\n"
            "下一步：用準客戶名單計實每單 FYC；大單優先危疾／5年供／扣稅年金。"
        )

    if any(k in text for k in ("週", "活動", "打卡", "罰款", "挑戰")):
        return (
            f"本週活動 **{ctx.get('wk_count')}/{ctx.get('wk_min')}**"
            + (
                f"——仲欠 {wk_need} 次，建議今日約見面或傾保險並即刻打卡。"
                if wk_need
                else "——已達標，保持節奏，用時間清卡案同準客戶。"
            )
        )

    if any(k in text for k in ("招募", "出code", "IRP", "新人")):
        return (
            f"你而家招募人數 **{ctx.get('recruit', 0)}**（年度目標通常 2 人）。\n"
            "建議：準客戶名單→招募 List 加名；打卡選「傾招募／報考試／出code」；"
            "Dashboard 睇招募進度 bar。"
        )

    # Default: briefing + top actions
    head = f"{name}，我睇過你 M+2 即時數據，建議今日咁排："
    bullets = "\n".join(f"{i+1}. {a}" for i, a in enumerate(actions[:3])) or "1. 去打卡／準客戶名單推進下一單。"
    return f"{head}\n\n{bullets}\n\n有具體個案名，話我知，我幫你拆下一步。"


def openai_chat(
    messages: list[dict[str, str]],
    *,
    system: str,
    api_key: str,
    model: str = DEFAULT_MODEL,
    timeout: int = 60,
) -> str:
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system}] + messages,
        "temperature": 0.6,
    }
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return str(data["choices"][0]["message"]["content"]).strip()
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"OpenAI HTTP {e.code}: {body}") from e


def reply(user_text: str, history: list[dict[str, str]], ctx: dict[str, Any]) -> tuple[str, str]:
    """
    Returns (assistant_text, mode) where mode is 'openai' | 'offline'.
    history: prior turns [{role, content}, ...] excluding the new user_text.
    """
    system = system_prompt(ctx)
    messages = list(history or []) + [{"role": "user", "content": user_text}]
    # Keep last N turns for token safety
    if len(messages) > 16:
        messages = messages[-16:]

    key = _secret_openai_key()
    if key:
        try:
            text = openai_chat(messages, system=system, api_key=key, model=_secret_model())
            return text, "openai"
        except Exception as e:
            fallback = offline_reply(user_text, ctx)
            return (
                f"（AI 連線暫時失敗：{e}）\n\n改用本地教練建議：\n\n{fallback}",
                "offline",
            )
    return offline_reply(user_text, ctx), "offline"


def welcome_message(ctx: dict[str, Any]) -> str:
    due_n = len(ctx.get("due") or [])
    name = ctx.get("username") or ""
    bit = f"今日有 **{due_n}** 宗要跟。" if due_n else "今日冇逾期案——保持！"
    return (
        f"你好 {name}，我係 **Coach Tim**（嵌喺 M+2）。"
        f"我已經讀咗你嘅業績、本週活動同跟進清單。{bit}\n\n"
        "可以問我：而家先做邊單、點開下一句、點補本週活動、Extra 10／MDRT 進度。"
    )
