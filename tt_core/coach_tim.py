"""Coach Tim AI — live M+2 read tools + chat (OpenAI or offline).

Phase 2: each reply can call a small set of read-only tools so answers
use fresh data (not only the page-load snapshot). No write-back.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any

from tt_core.constants import MDRT_TARGET, Q1_TARGET, WEEKLY_MIN_ACTS

COACH_MENU = "🧠 Coach Tim"
DEFAULT_MODEL = "gpt-4o-mini"
MAX_TOOLS_PER_TURN = 3

# Stable tool names (internal API — read only)
TOOL_MEMBER_SNAPSHOT = "get_member_snapshot"
TOOL_DUE_FOLLOWUPS = "get_due_followups"
TOOL_UPCOMING_FOLLOWUPS = "get_upcoming_followups"
TOOL_SEARCH_FOLLOWUP = "search_followup"
TOOL_SEARCH_PROSPECTS = "search_prospects"
TOOL_STUCK_CASES = "get_stuck_cases"
TOOL_TEAM_OVERVIEW = "get_team_overview"

TOOL_CATALOG: dict[str, str] = {
    TOOL_MEMBER_SNAPSHOT: "業績／本週活動／MDRT／Extra 10 快照",
    TOOL_DUE_FOLLOWUPS: "今日要跟／逾期跟進",
    TOOL_UPCOMING_FOLLOWUPS: "未來 7 日跟進",
    TOOL_SEARCH_FOLLOWUP: "按人名搜尋跟進案",
    TOOL_SEARCH_PROSPECTS: "按人名搜尋準客戶",
    TOOL_STUCK_CASES: "卡住／久未推進個案",
    TOOL_TEAM_OVERVIEW: "團隊教練總覽（Leader）",
}


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


def _fu_rows(df, limit: int = 8) -> list[dict]:
    rows = []
    if df is None or getattr(df, "empty", True):
        return rows
    for _, r in df.head(limit).iterrows():
        nd = r.get("next_date")
        try:
            nd_s = str(nd)[:10] if nd is not None and str(nd) not in ("", "NaT", "nan") else ""
            if hasattr(nd, "strftime"):
                nd_s = nd.strftime("%Y-%m-%d")
        except Exception:
            nd_s = str(nd or "")[:10]
        rows.append(
            {
                "person": str(r.get("person") or ""),
                "track": str(r.get("track") or ""),
                "stage": str(r.get("stage") or ""),
                "next_action": str(r.get("next_action") or ""),
                "next_date": nd_s,
                "status": str(r.get("status") or ""),
            }
        )
    return rows


def build_coach_context(username: str, *, role: str = "Member") -> dict[str, Any]:
    """Pull live M+2 snapshot for Coach Tim (also used as get_member_snapshot tool)."""
    from tt_core.data import (
        get_due_followups,
        get_member_snapshot,
        get_upcoming_followups,
        mdrt_card_metrics,
    )

    snap = get_member_snapshot(username)
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
        "tool_hits": {},
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
    hits = ctx.get("tool_hits") or {}
    if hits.get("followups"):
        lines.append("- **剛剛查到嘅跟進**：")
        for d in hits["followups"][:4]:
            lines.append(
                f"  - {d['person']}（{d['track']}｜{d['stage']}）"
                f" → {d['next_action'] or '—'} · {d['next_date']}"
            )
    if hits.get("prospects"):
        lines.append("- **剛剛查到嘅準客戶**：")
        for p in hits["prospects"][:4]:
            lines.append(f"  - {p.get('name')} · FYC ${float(p.get('fyc') or 0):,.0f}")
    return "\n".join(lines)


# ─── Phase 2 read tools ──────────────────────────────────────────────────────


_NAME_STOP = {
    "今日",
    "本週",
    "活動",
    "打卡",
    "跟進",
    "優先",
    "應該",
    "做咩",
    "點樣",
    "幫我",
    "根據",
    "數據",
    "進度",
    "下一步",
    "最應該",
    "卡案",
    "準客戶",
    "名單",
    "招募",
    "業績",
    "罰款",
    "挑戰",
    "仲欠",
    "幾多",
    "欠唔",
    "最快",
    "點補",
    "點衝",
    "點開",
    "而家",
    "建議",
    "排優",
    "次序",
    "回覆",
    "today",
    "follow",
    "next",
    "mdrt",
    "fyc",
    "extra",
    "coach",
    "tim",
    "m+2",
    "m2",
}


def _name_hints(text: str) -> list[str]:
    """Extract likely person-name fragments from a user question."""
    t = (text or "").strip()
    if not t:
        return []
    hints: list[str] = []
    for m in re.finditer(r"[「『\"']([^」』\"']{1,40})[」』\"']", t):
        hints.append(m.group(1).strip())
    # Prefer Latin names (Ave, Elaine) — CJK only if quoted or clearly not stop words
    for tok in re.findall(r"[A-Za-z][A-Za-z\-']{1,30}", t):
        low = tok.lower()
        if low in _NAME_STOP:
            continue
        if tok not in hints:
            hints.append(tok)
    for tok in re.findall(r"[\u4e00-\u9fff]{2,4}", t):
        if tok in _NAME_STOP:
            continue
        # Skip if this CJK token is part of a longer stop phrase already covered
        if any(tok in s or s in tok for s in _NAME_STOP if len(s) >= 2):
            # still allow real names that aren't stop words themselves
            if tok in _NAME_STOP:
                continue
        if tok not in hints and tok not in _NAME_STOP:
            # Only keep CJK hints when user also signals a case lookup
            if any(k in t for k in ("呢單", "呢個案", "個案", "跟進", "準客戶", "點跟", "拆")):
                hints.append(tok)
    return hints[:6]


def choose_tools(user_text: str, *, role: str = "Member") -> list[str]:
    """Pick up to MAX_TOOLS_PER_TURN read tools for this question."""
    text = (user_text or "").strip()
    low = text.lower()
    picked: list[str] = []

    def add(name: str) -> None:
        if name not in picked and len(picked) < MAX_TOOLS_PER_TURN:
            picked.append(name)

    hints = _name_hints(text)
    metrics = any(
        k in low for k in ("mdrt", "業績", "fyc", "extra", "活動", "週", "打卡", "罰款", "招募")
    )
    dueish = any(k in text for k in ("今日", "卡案", "要跟", "優先", "跟邊", "邊單"))
    personish = bool(hints) or any(
        k in text for k in ("呢單", "呢個案", "個案", "點跟", "拆")
    )
    prospectish = any(k in text for k in ("準客戶", "prospect", "產品")) or (
        bool(hints) and any(k in low for k in ("fyc", "fact"))
    )

    # Metrics first so week/MDRT questions aren't crowded out by name guesses
    if metrics:
        add(TOOL_MEMBER_SNAPSHOT)
    if dueish or (personish and not metrics):
        add(TOOL_DUE_FOLLOWUPS)
    if personish or hints:
        add(TOOL_SEARCH_FOLLOWUP)
    if prospectish or (hints and "準客戶" in text):
        add(TOOL_SEARCH_PROSPECTS)
    if any(k in text for k in ("卡住", "stuck", "唔郁", "逾期好耐", "無跟")):
        add(TOOL_STUCK_CASES)
    if any(k in text for k in ("未來", "七日", "7 日", "7日", "下週")):
        add(TOOL_UPCOMING_FOLLOWUPS)
    if role == "Leader" and any(k in text for k in ("團隊", "全隊", "邊個欠", "同事", "overview")):
        add(TOOL_TEAM_OVERVIEW)

    if not picked:
        add(TOOL_MEMBER_SNAPSHOT)
        add(TOOL_DUE_FOLLOWUPS)

    return picked[:MAX_TOOLS_PER_TURN]


def run_tool(
    name: str,
    *,
    username: str,
    role: str = "Member",
    query: str = "",
) -> dict[str, Any]:
    """Execute one read-only tool. Always returns a plain JSON-safe dict."""
    try:
        if name == TOOL_MEMBER_SNAPSHOT:
            ctx = build_coach_context(username, role=role)
            return {"ok": True, "tool": name, "context": ctx}

        if name == TOOL_DUE_FOLLOWUPS:
            from tt_core.data import get_due_followups

            rows = _fu_rows(get_due_followups(username), limit=12)
            return {"ok": True, "tool": name, "count": len(rows), "rows": rows}

        if name == TOOL_UPCOMING_FOLLOWUPS:
            from tt_core.data import get_upcoming_followups

            rows = _fu_rows(get_upcoming_followups(username, days=7), limit=12)
            return {"ok": True, "tool": name, "count": len(rows), "rows": rows}

        if name == TOOL_SEARCH_FOLLOWUP:
            import pandas as pd

            from tt_core.data import get_followups

            df = get_followups(username)
            hints = _name_hints(query)
            rows = []
            if df is not None and not getattr(df, "empty", True):
                open_df = df[df["status"].astype(str).str.lower() == "open"]
                if hints and not open_df.empty:
                    mask = pd.Series(False, index=open_df.index)
                    for h in hints:
                        mask = mask | open_df["person"].astype(str).str.contains(
                            re.escape(h), case=False, na=False
                        )
                    hit = open_df[mask]
                else:
                    hit = open_df
                rows = _fu_rows(hit, limit=8)
            return {
                "ok": True,
                "tool": name,
                "hints": hints,
                "count": len(rows),
                "rows": rows,
            }

        if name == TOOL_SEARCH_PROSPECTS:
            import pandas as pd

            from tt_core import prospects as pr

            pdf = pr.get_prospects(username=username, year=pr.current_year())
            hints = _name_hints(query)
            out = []
            if pdf is not None and not pdf.empty:
                work = pdf
                if hints:
                    mask = pd.Series(False, index=work.index)
                    for h in hints:
                        mask = mask | work["name"].astype(str).str.contains(
                            re.escape(h), case=False, na=False
                        )
                    work = work[mask]
                ytd = 0.0
                try:
                    ytd = float(pr.member_ytd_fyc(username) or 0)
                except Exception:
                    pass
                for _, r in work.head(8).iterrows():
                    out.append(
                        {
                            "name": str(r.get("name") or ""),
                            "list_type": str(r.get("list_type") or ""),
                            "fyc": float(r.get("fyc") or 0),
                            "products": pr.display_products(
                                r.get("selling_products"), ytd_fyc=ytd
                            )[:160],
                            "factfind": str(r.get("factfind") or "")[:200],
                            "quarter": int(r.get("quarter") or 0),
                        }
                    )
            return {
                "ok": True,
                "tool": name,
                "hints": hints,
                "count": len(out),
                "rows": out,
            }

        if name == TOOL_STUCK_CASES:
            from tt_core.data import get_stuck_cases

            stuck = get_stuck_cases(username)
            rows = _fu_rows(stuck, limit=8)
            if stuck is not None and not getattr(stuck, "empty", True):
                # attach overdue if present
                enriched = []
                for i, (_, r) in enumerate(stuck.head(8).iterrows()):
                    item = rows[i] if i < len(rows) else {}
                    item = dict(item)
                    item["overdue_days"] = int(r.get("overdue_days") or 0)
                    item["stuck_reason"] = str(r.get("stuck_reason") or "")
                    enriched.append(item)
                rows = enriched
            return {"ok": True, "tool": name, "count": len(rows), "rows": rows}

        if name == TOOL_TEAM_OVERVIEW:
            if role != "Leader":
                return {"ok": False, "tool": name, "error": "只限 Leader"}
            from tt_core.data import get_team_coach_overview

            overview = get_team_coach_overview()
            rows = []
            if overview is not None and not overview.empty:
                for _, r in overview.head(20).iterrows():
                    rows.append(
                        {
                            "username": str(r.get("username") or ""),
                            "wk_count": int(r.get("wk_count") or 0),
                            "mtd_fyc": float(r.get("mtd_fyc") or 0),
                            "stuck_count": int(r.get("stuck_count") or 0),
                            "needs_acts": bool(r.get("needs_acts")),
                            "max_overdue": int(r.get("max_overdue") or 0),
                        }
                    )
            return {"ok": True, "tool": name, "count": len(rows), "rows": rows}

        return {"ok": False, "tool": name, "error": "unknown tool"}
    except Exception as e:
        return {"ok": False, "tool": name, "error": str(e)[:200]}


def gather_live_context(
    username: str,
    user_text: str,
    *,
    role: str = "Member",
    base_ctx: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """Run chosen tools and merge into a coaching context for this turn."""
    tools = choose_tools(user_text, role=role)
    results = [run_tool(t, username=username, role=role, query=user_text) for t in tools]

    ctx = dict(base_ctx or {})
    if not ctx.get("username"):
        ctx["username"] = username
    ctx["role"] = role
    hits: dict[str, list] = {"followups": [], "prospects": [], "team": [], "stuck": []}

    for res in results:
        if not res.get("ok"):
            continue
        t = res.get("tool")
        if t == TOOL_MEMBER_SNAPSHOT and isinstance(res.get("context"), dict):
            fresh = res["context"]
            fresh["tool_hits"] = ctx.get("tool_hits") or {}
            ctx = fresh
        elif t == TOOL_DUE_FOLLOWUPS:
            ctx["due"] = list(res.get("rows") or [])
        elif t == TOOL_UPCOMING_FOLLOWUPS:
            ctx["upcoming"] = list(res.get("rows") or [])
        elif t == TOOL_SEARCH_FOLLOWUP:
            hits["followups"] = list(res.get("rows") or [])
            # If searching without exact hit, due list still useful
            if hits["followups"] and not ctx.get("due"):
                ctx["due"] = hits["followups"][:6]
        elif t == TOOL_SEARCH_PROSPECTS:
            hits["prospects"] = list(res.get("rows") or [])
            if hits["prospects"]:
                ctx["prospects"] = [
                    {
                        "name": p.get("name"),
                        "fyc": p.get("fyc"),
                        "products": p.get("products"),
                    }
                    for p in hits["prospects"][:5]
                ]
        elif t == TOOL_STUCK_CASES:
            hits["stuck"] = list(res.get("rows") or [])
            if hits["stuck"]:
                ctx["due"] = hits["stuck"][:6]
        elif t == TOOL_TEAM_OVERVIEW:
            hits["team"] = list(res.get("rows") or [])

    ctx["tool_hits"] = hits
    ctx["_tools_used"] = tools
    return ctx, tools


def system_prompt(ctx: dict[str, Any]) -> str:
    briefing = format_context_markdown(ctx)
    tools_used = ctx.get("_tools_used") or []
    tool_note = ""
    if tools_used:
        labels = [TOOL_CATALOG.get(t, t) for t in tools_used]
        tool_note = "\n本回合已即時查過：" + "、".join(labels) + "。\n"
    return f"""你係 Coach Tim——TIM TEAM（M+2）嘅教練助手。用香港粵語為主、間中書面語，直接、務實、鼓勵但不吹水。

你而家喺 M+2 管理系統入面，已經用內部 tools 讀到呢位同事嘅即時數據（唔好估數，以下係真相）：
{tool_note}
{briefing}

職責：
1. 幫佢決定「而家最緊要做邊一件」——優先清卡案／今日要跟，再補本週活動。
2. 跟進建議要具體：下一句點開、點約 next appointment、Fact find 邊條要補。
3. 業績／Extra 10／MDRT 只引用上面數字；唔好發明 FYC。
4. 回覆短：2–6 句＋最多 3 個 bullet action。
5. 如果問工具（醫療融資、準客戶、打卡），引導佢去 M+2 對應功能，並講點用。
6. 你只讀數據同俾建議；唔好話自己已經改咗系統資料。
"""


def offline_reply(user_text: str, ctx: dict[str, Any]) -> str:
    """Useful coach without API key — grounded in live tool context."""
    text = (user_text or "").strip()
    low = text.lower()
    due = ctx.get("due") or []
    wk_need = int(ctx.get("wk_need") or 0)
    name = ctx.get("username") or "你"
    hits = ctx.get("tool_hits") or {}

    # Specific follow-up hit from search tool
    fu_hits = hits.get("followups") or []
    if fu_hits and any(k in text for k in ("跟", "案", "點", "拆", "next", "邊")):
        d = fu_hits[0]
        return (
            f"{name}，我即時查過跟進名單，而家睇 **{d['person']}**：\n\n"
            f"- Track：{d['track']}｜階段：{d['stage']}\n"
            f"- Next：{d['next_action'] or '（未填）'} · 日期 {d['next_date']}\n"
            f"- 建議：今日聯絡，確認 next appointment；打卡時更新 Fact find。\n"
        )

    # Specific prospect hit
    pr_hits = hits.get("prospects") or []
    if pr_hits and any(k in text for k in ("準客戶", "prospect", "FYC", "fyc", "產品", "fact")):
        p = pr_hits[0]
        return (
            f"{name}，準客戶 **{p.get('name')}**：\n"
            f"- 預估 FYC：**${float(p.get('fyc') or 0):,.0f}**\n"
            f"- 產品：{p.get('products') or '—'}\n"
            f"- Fact find：{(p.get('factfind') or '（未填）')[:120]}\n\n"
            "下一步：補齊 Fact find → 約聽 concept → 打卡更新階段。"
        )

    team = hits.get("team") or []
    if team and ctx.get("role") == "Leader":
        lines = [f"{name}，團隊即時總覽（最需要關注先）："]
        for r in team[:5]:
            flag = []
            if r.get("needs_acts"):
                flag.append("欠活動")
            if int(r.get("stuck_count") or 0) > 0:
                flag.append(f"卡住{r['stuck_count']}單")
            lines.append(
                f"- **{r['username']}**：週活動 {r['wk_count']}｜"
                f"MTD ${r['mtd_fyc']:,.0f}"
                + (f"｜{'、'.join(flag)}" if flag else "")
            )
        return "\n".join(lines)

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
            f"{name}，我即時查過今日要跟，而家最緊要係清卡案。\n\n"
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

    head = f"{name}，我即時查過你 M+2 數據，建議今日咁排："
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


def reply(
    user_text: str,
    history: list[dict[str, str]],
    ctx: dict[str, Any],
) -> tuple[str, str, dict[str, Any]]:
    """
    Returns (assistant_text, mode, meta).
    mode: 'openai' | 'offline'
    meta: {tools_used: [...]}
    Each turn refreshes live data via read-only tools (max 3).
    """
    username = str((ctx or {}).get("username") or "")
    role = str((ctx or {}).get("role") or "Member")
    live_ctx, tools_used = gather_live_context(
        username, user_text, role=role, base_ctx=ctx
    )
    meta = {"tools_used": tools_used}

    system = system_prompt(live_ctx)
    messages = list(history or []) + [{"role": "user", "content": user_text}]
    if len(messages) > 16:
        messages = messages[-16:]

    key = _secret_openai_key()
    if key:
        try:
            text = openai_chat(
                messages, system=system, api_key=key, model=_secret_model()
            )
            return text, "openai", meta
        except Exception as e:
            fallback = offline_reply(user_text, live_ctx)
            return (
                f"（AI 連線暫時失敗：{e}）\n\n改用本地教練建議：\n\n{fallback}",
                "offline",
                meta,
            )
    return offline_reply(user_text, live_ctx), "offline", meta


def welcome_message(ctx: dict[str, Any]) -> str:
    due_n = len(ctx.get("due") or [])
    name = ctx.get("username") or ""
    bit = f"今日有 **{due_n}** 宗要跟。" if due_n else "今日冇逾期案——保持！"
    return (
        f"你好 {name}，我係 **Coach Tim**。"
        f"我已經讀咗你嘅業績、本週活動同跟進清單。{bit}\n\n"
        "可以問我：而家先做邊單、點開下一句、點補本週活動、Extra 10／MDRT 進度。"
        "講個案名我會即時幫你查最新跟進／準客戶資料。"
    )
