"""AI Tim — live M+2 read tools + chat (Gemini free / OpenAI / offline).

Prefer free Google Gemini (AI Studio) so the team gets real AI answers
without OpenAI billing. Cursor subscription does not cover this app.
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from tt_core.constants import MDRT_TARGET, Q1_TARGET, WEEKLY_MIN_ACTS

COACH_MENU = "🧠 AI Tim"
DEFAULT_MODEL = "gpt-4o-mini"
# Google retired 2.x / 2.5 flash for many new keys — use current Flash GA
DEFAULT_GEMINI_MODEL = "gemini-3.8-flash"
# Ordered fallbacks when the preferred model is busy / missing
GEMINI_MODEL_FALLBACKS = (
    "gemini-3.8-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
)
# Map retired ids (saved settings / old defaults) onto current models
_GEMINI_MODEL_REWRITE = {
    "gemini-2.5-flash": "gemini-3.8-flash",
    "gemini-2.0-flash": "gemini-3.8-flash",
    "gemini-2.0-flash-001": "gemini-3.8-flash",
    "gemini-2.0-flash-lite": "gemini-3.5-flash-lite",
    "gemini-1.5-flash": "gemini-3.6-flash",
    "gemini-1.5-flash-latest": "gemini-3.6-flash",
    "gemini-flash-latest": "gemini-3.8-flash",
}
MAX_TOOLS_PER_TURN = 3
SETTING_API_KEY = "coach_tim_openai_api_key"
SETTING_MODEL = "coach_tim_openai_model"
SETTING_GEMINI_KEY = "coach_tim_gemini_api_key"
SETTING_GEMINI_MODEL = "coach_tim_gemini_model"
SETTING_TELEGRAM_URL = "coach_tim_telegram_url"
_SETTINGS_SHEET = "system_settings"

# Stable tool names (internal API — read only)
TOOL_MEMBER_SNAPSHOT = "get_member_snapshot"
TOOL_DUE_FOLLOWUPS = "get_due_followups"
TOOL_UPCOMING_FOLLOWUPS = "get_upcoming_followups"
TOOL_SEARCH_FOLLOWUP = "search_followup"
TOOL_SEARCH_PROSPECTS = "search_prospects"
TOOL_STUCK_CASES = "get_stuck_cases"
TOOL_TEAM_OVERVIEW = "get_team_overview"
TOOL_PRODUCT_KB = "get_product_knowledge"

TOOL_CATALOG: dict[str, str] = {
    TOOL_MEMBER_SNAPSHOT: "業績／本週活動／MDRT／Extra 10 快照",
    TOOL_DUE_FOLLOWUPS: "今日要跟／逾期跟進",
    TOOL_UPCOMING_FOLLOWUPS: "未來 7 日跟進",
    TOOL_SEARCH_FOLLOWUP: "按人名搜尋跟進案",
    TOOL_SEARCH_PROSPECTS: "按人名搜尋準客戶",
    TOOL_STUCK_CASES: "卡住／久未推進個案",
    TOOL_TEAM_OVERVIEW: "團隊教練總覽（Leader）",
    TOOL_PRODUCT_KB: "產品知識（危疾全應援等）",
}


def _settings_get(key: str, default: str = "") -> str:
    """Read system_settings / session — same pattern as Team SC (Cloud-safe)."""
    try:
        import streamlit as st

        ss = st.session_state.get(f"_setting_{key}")
        if ss is not None and str(ss).strip():
            return str(ss).strip()
    except Exception:
        pass
    try:
        from tt_core.db import read_data

        df = read_data(_SETTINGS_SHEET)
        if df is None or getattr(df, "empty", True) or "key" not in df.columns:
            return default
        hit = df[df["key"].astype(str) == key]
        if hit.empty:
            return default
        return str(hit.iloc[0].get("value", default) or default).strip() or default
    except Exception:
        return default


def _settings_set(key: str, value: str) -> bool:
    import datetime as _dt

    value = str(value or "").strip()
    try:
        import streamlit as st

        if value:
            st.session_state[f"_setting_{key}"] = value
        else:
            st.session_state.pop(f"_setting_{key}", None)
    except Exception:
        pass
    try:
        from tt_core.db import read_data, run_query_gs

        now = str(_dt.datetime.now())
        df = read_data(_SETTINGS_SHEET)
        if df is not None and not df.empty and "key" in df.columns:
            hit = df[df["key"].astype(str) == key]
            if (
                not hit.empty
                and "id" in df.columns
                and str(hit.iloc[0].get("id", "")).strip()
            ):
                return bool(
                    run_query_gs(
                        "UPDATE",
                        _SETTINGS_SHEET,
                        {"value": value, "updated_at": now},
                        row_id=hit.iloc[0]["id"],
                    )
                )
        if not value:
            return True
        return bool(
            run_query_gs(
                "INSERT",
                _SETTINGS_SHEET,
                {"key": key, "value": value, "updated_at": now},
            )
        )
    except Exception:
        return bool(value)  # session-only fallback still usable this run


def _secret_openai_key() -> str:
    """Streamlit secrets first (preferred), then Leader-saved system_settings."""
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
    return _settings_get(SETTING_API_KEY, "")


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
    saved = _settings_get(SETTING_MODEL, "")
    return saved or DEFAULT_MODEL


def _secret_gemini_key() -> str:
    """Free Google AI Studio key — secrets first, then Leader-saved setting."""
    try:
        import streamlit as st

        if "gemini" in st.secrets:
            block = st.secrets["gemini"]
            if isinstance(block, dict) or hasattr(block, "get"):
                for k in ("api_key", "key", "GEMINI_API_KEY"):
                    v = block.get(k) if hasattr(block, "get") else None
                    if v:
                        return str(v).strip()
            elif block:
                return str(block).strip()
        if "coach_tim" in st.secrets:
            block = st.secrets["coach_tim"]
            for k in ("gemini_api_key", "gemini_key"):
                v = block.get(k) if hasattr(block, "get") else None
                if v:
                    return str(v).strip()
        for k in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
            if k in st.secrets and st.secrets[k]:
                return str(st.secrets[k]).strip()
    except Exception:
        pass
    return _settings_get(SETTING_GEMINI_KEY, "")


def _secret_gemini_model() -> str:
    try:
        import streamlit as st

        if "coach_tim" in st.secrets and st.secrets["coach_tim"].get("gemini_model"):
            return str(st.secrets["coach_tim"]["gemini_model"]).strip()
        if "gemini" in st.secrets and hasattr(st.secrets["gemini"], "get"):
            m = st.secrets["gemini"].get("model")
            if m:
                return str(m).strip()
    except Exception:
        pass
    return _settings_get(SETTING_GEMINI_MODEL, "") or DEFAULT_GEMINI_MODEL


def llm_configured() -> bool:
    """True when any free/paid LLM key is available (Gemini preferred)."""
    return bool(_secret_gemini_key() or _secret_openai_key())


def llm_provider() -> str:
    """Active provider label: gemini | openai | offline."""
    if _secret_gemini_key():
        return "gemini"
    if _secret_openai_key():
        return "openai"
    return "offline"


def save_gemini_api_key(api_key: str) -> bool:
    """Leader saves free Gemini key for the whole team."""
    key = str(api_key or "").strip()
    if not key:
        return False
    return _settings_set(SETTING_GEMINI_KEY, key)


def clear_gemini_api_key() -> bool:
    return _settings_set(SETTING_GEMINI_KEY, "")


def save_openai_api_key(api_key: str) -> bool:
    """Optional paid OpenAI key (not required if Gemini is set)."""
    key = str(api_key or "").strip()
    if not key:
        return False
    return _settings_set(SETTING_API_KEY, key)


def clear_openai_api_key() -> bool:
    return _settings_set(SETTING_API_KEY, "")


def mask_api_key(api_key: str) -> str:
    k = str(api_key or "").strip()
    if len(k) < 12:
        return "••••" if k else ""
    return f"{k[:7]}…{k[-4:]}"


def get_telegram_coach_url() -> str:
    try:
        import streamlit as st

        if "coach_tim" in st.secrets and st.secrets["coach_tim"].get("telegram_url"):
            return str(st.secrets["coach_tim"]["telegram_url"]).strip()
    except Exception:
        pass
    return _settings_get(SETTING_TELEGRAM_URL, "")


def save_telegram_coach_url(url: str) -> bool:
    return _settings_set(SETTING_TELEGRAM_URL, str(url or "").strip())


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
    """Pull live M+2 snapshot for AI Tim (also used as get_member_snapshot tool)."""
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
    prospectish = any(k in text for k in ("準客戶", "prospect")) or (
        bool(hints) and any(k in low for k in ("fyc", "fact"))
    )
    productish = False
    try:
        from tt_core.product_knowledge import product_query_intent

        productish = product_query_intent(text)
    except Exception:
        productish = any(
            k in text or k in low
            for k in (
                "危疾",
                "全應援",
                "應援保",
                "allsupporter",
                "所需全",
                "更周全",
                "摯齊全",
                "產品",
                "計劃書",
                "賣點",
            )
        )

    # Metrics first so week/MDRT questions aren't crowded out by name guesses
    if metrics:
        add(TOOL_MEMBER_SNAPSHOT)
    if productish:
        add(TOOL_PRODUCT_KB)
    if dueish or (personish and not metrics and not productish):
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

        if name == TOOL_PRODUCT_KB:
            from tt_core.product_knowledge import format_matched_briefs, match_product_packs

            brief = format_matched_briefs(query or "")
            packs = match_product_packs(query or "")
            return {
                "ok": True,
                "tool": name,
                "count": len(packs) if packs else (1 if brief else 0),
                "brief": brief,
                "pack_ids": [str(p.get("id") or "") for p in packs],
            }

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
    hits: dict[str, list] = {
        "followups": [],
        "prospects": [],
        "team": [],
        "stuck": [],
        "products": [],
    }
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
        elif t == TOOL_PRODUCT_KB:
            brief = str(res.get("brief") or "").strip()
            if brief:
                ctx["product_brief"] = brief
                hits["products"] = list(res.get("pack_ids") or [])

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
    who = ctx.get("username") or "呢位同事"
    channel = str(ctx.get("channel") or "app").strip().lower()
    if channel == "telegram":
        place = "而家喺 **Telegram** 同 **{who}** 一對一傾偈（Coach Tim AI）。".format(
            who=who
        )
        write_rule = (
            "7. Telegram 頻道唔直接寫入 M+2；要打卡／改數引導同事去 M+2 App 確認。"
        )
    else:
        place = "而家喺 M+2 App 入面同 **{who}** 傾偈。".format(who=who)
        write_rule = (
            "7. 寫入系統必須經用戶確認（Phase 3）。未確認前唔好話已經改咗資料。"
        )
    base = f"""你係 AI Tim／Coach Tim——TIM TEAM 嘅私人教練（App 同 Telegram 同一個角色）。
用香港粵語為主、間中書面語。直接、務實、鼓勵但不吹水。好似喺 Telegram 一對一傾偈。

{place}以下係系統即時讀到嘅佢嘅業績／跟進／準客戶（真相，唔好估數、唔好發明 FYC）：
{tool_note}
{briefing}

職責：
1. 按佢問嘅問題答——唔好每次都背同一套 Extra 10 講稿。
2. 幫佢決定「而家最緊要做邊一件」：優先清卡案／今日要跟，再補本週活動，再衝準客戶／MDRT。
3. 跟進建議要具體：下一句點開、點約 next appointment、Fact find 邊條要補。
4. 數字只引用上面 briefing；冇嘅就話未讀到，叫佢去對應頁更新（或喺 Telegram 用 /link 綁定 M+2 帳號）。
5. 回覆短：2–8 句＋最多 3 個 bullet action；可以追問個案名。
6. 如果問醫療融資／保障缺口／打卡／準客戶名單，引導去 M+2 對應功能。
{write_rule}
8. 如果 briefing 有「產品知識」（例如危疾全應援），可以教銷售角度／三個級別差異／自選附約；但條款細節以正式計劃書為準，唔好發明保費或保證回報。
"""
    product_brief = str(ctx.get("product_brief") or "").strip()
    if product_brief:
        base = (
            base
            + "\n以下係系統載入嘅產品知識（內部培訓用，唔係報價）：\n"
            + product_brief
            + "\n"
        )
    try:
        from tt_core.coach_writes import write_rules_for_prompt

        rules = write_rules_for_prompt(
            role=str(ctx.get("role") or "Member"),
            username=str(ctx.get("username") or ""),
        )
        return base + "\n" + rules
    except Exception:
        return base


def _offline_intent(text: str) -> str:
    """Route offline replies by question type — avoid one canned answer for all."""
    t = (text or "").strip()
    low = t.lower()
    if any(
        k in t
        for k in (
            "一樣",
            "同一個",
            "每次都",
            "都係答",
            "重複",
            "冇反應",
            "聽唔明",
            "答非所問",
        )
    ):
        return "meta"
    if any(k in t for k in ("你係邊", "你係誰", "你做咩", "點用你", "可以問咩", "點問")):
        return "help"
    if any(k in t for k in ("你好", "早晨", "晚安", "嗨", "hi ", "hello")) and len(t) < 12:
        return "greet"
    if any(k in low for k in ("mdrt", "業績", "extra 10", "extra10")) or (
        "fyc" in low and "準客戶" not in t
    ):
        return "metrics"
    if any(k in t for k in ("週", "活動", "罰款", "挑戰")) or (
        "打卡" in t and "跟" not in t and "案" not in t
    ):
        return "week"
    if any(k in t for k in ("招募", "出code", "IRP", "新人")):
        return "recruit"
    if any(k in t for k in ("準客戶", "prospect", "名單")):
        return "prospect"
    if any(k in t for k in ("未來", "七日", "7 日", "7日", "下週")):
        return "upcoming"
    if any(k in t for k in ("卡住", "stuck", "唔郁", "逾期好耐")):
        return "stuck"
    if any(
        k in t
        for k in (
            "幫我打卡",
            "代打卡",
            "寫入打卡",
            "確認打卡",
            "改 FYC",
            "改業績",
            "改招募",
        )
    ):
        return "checkin_write"
    # Explicit priority / what should I do today
    if any(k in t for k in ("優先", "最應該", "做咩", "今日做", "排程", "安排")):
        return "priority"
    if any(k in t for k in ("跟", "卡案", "要跟", "拆", "呢單", "個案", "follow", "next")):
        return "followup"
    if any(k in t for k in ("醫療融資", "保障缺口", "T-Account", "核保")):
        return "tools"
    try:
        from tt_core.product_knowledge import product_query_intent

        if product_query_intent(t):
            return "product"
    except Exception:
        if any(k in t for k in ("危疾", "全應援", "應援保", "所需全", "更周全", "摯齊全", "賣點")):
            return "product"
    return "clarify"


def _priority_actions(ctx: dict[str, Any]) -> list[str]:
    """Build priority bullets only when user asks what to do."""
    due = ctx.get("due") or []
    wk_need = int(ctx.get("wk_need") or 0)
    actions: list[str] = []
    if due:
        top = due[0]
        actions.append(
            f"今日優先跟 **{top['person']}**（{top['track']}｜{top['stage']}）："
            f"{top['next_action'] or '更新 Next action + 日期'}。"
        )
        if len(due) > 1:
            actions.append(f"其餘仲有 {len(due) - 1} 宗今日／逾期案，清完先再拓新客。")
    else:
        actions.append("今日冇逾期／到期跟進——可以推準客戶或衝業績。")
    if wk_need > 0:
        actions.append(
            f"本週仲欠 **{wk_need}** 次活動（而家 {ctx.get('wk_count')}/{ctx.get('wk_min')}）——"
            "見面／傾保險／傾招募隨手打卡。"
        )
    pros = ctx.get("prospects") or []
    if pros:
        p = pros[0]
        actions.append(
            f"準客戶推進：**{p.get('name')}**（預估 FYC ${float(p.get('fyc') or 0):,.0f}）——"
            "補 Fact find／約 next appointment。"
        )
    elif ctx.get("extra10_open"):
        actions.append(
            "Extra 10 已開——危疾／盈聚 5pay／扣稅年金用準客戶名單計 FYC。"
        )
    elif not ctx.get("extra10_open"):
        actions.append(
            f"Extra 10 尚欠 ${ctx.get('extra10_remaining', 0):,.0f} YTD 先有 ×1.1。"
        )
    return actions


def offline_reply(user_text: str, ctx: dict[str, Any]) -> str:
    """Useful coach without API key — intent-routed, not one canned template."""
    text = (user_text or "").strip()
    due = ctx.get("due") or []
    wk_need = int(ctx.get("wk_need") or 0)
    name = ctx.get("username") or "你"
    hits = ctx.get("tool_hits") or {}
    intent = _offline_intent(text)

    fu_hits = hits.get("followups") or []
    pr_hits = hits.get("prospects") or []

    if intent == "meta":
        return (
            f"{name}，唔好意思——未設 AI key 時我係按「你問咩類型」分流答，"
            "唔係逐句自由傾偈。\n\n"
            "你可以試呢啲，答案會唔同：\n"
            "- **今日優先／最應該做咩** → 排優先次序\n"
            "- **本週活動** → 欠幾多次\n"
            "- **MDRT／Extra 10** → 業績數字\n"
            "- **準客戶 + 人名**（如 Ave）→ 查嗰單 FYC／Fact find\n"
            "- **幫我拆某某點跟** → 查跟進階段同 Next action\n"
        )

    if intent == "help":
        return (
            f"我係 **AI Tim**，讀你 M+2 即時數據幫你排跟進同活動。\n"
            "直接問：今日優先、本週活動、MDRT、招募，講個案名（例如「拆 Ave 點跟」），"
            "或者問產品（例如「危疾全應援點賣」「所需全同更周全分別」）。"
        )

    if intent == "greet":
        due_n = len(due)
        bit = f"今日有 **{due_n}** 宗要跟。" if due_n else "今日冇逾期案。"
        return f"你好 {name}！{bit}想我幫你排優先、睇活動，定係拆某一單？"

    # Named follow-up from live search
    if fu_hits and intent in ("followup", "priority", "clarify"):
        d = fu_hits[0]
        return (
            f"{name}，我即時查過跟進名單，而家睇 **{d['person']}**：\n\n"
            f"- Track：{d['track']}｜階段：{d['stage']}\n"
            f"- Next：{d['next_action'] or '（未填）'} · 日期 {d['next_date']}\n"
            f"- 建議：今日聯絡，確認 next appointment；打卡時更新 Fact find。\n"
        )

    # Named prospect
    if pr_hits and intent in ("prospect", "metrics", "clarify"):
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

    if intent == "followup":
        # Prefer the named person in the question (e.g. Elaine) over the first due row
        hints = [h.lower() for h in _name_hints(text)]
        pool = list(fu_hits) + list(due) + list(ctx.get("upcoming") or [])
        named = None
        for h in hints:
            for row in pool:
                person = str(row.get("person") or row.get("name") or "")
                if h and h in person.lower():
                    named = row
                    break
            if named:
                break
        if named:
            d = named
            return (
                f"{name}，關於 **{d.get('person') or d.get('name')}**：\n\n"
                f"- Track：{d.get('track') or '—'}｜階段：{d.get('stage') or '—'}\n"
                f"- Next：{d.get('next_action') or '（未填）'} · 日期 {d.get('next_date') or '—'}\n"
                f"- 建議：今日聯絡確認 next appointment；打卡時更新 Fact find 同階段。\n"
            )
        if due:
            d = due[0]
            return (
                f"{name}，今日要跟 **{len(due)}** 宗，第一單：**{d['person']}**\n"
                f"- {d['track']}｜{d['stage']}\n"
                f"- Next：{d['next_action'] or '（未填）'} · {d['next_date']}\n"
                f"- 建議：今日聯絡並打卡更新。\n"
                + (f"\n本週仲欠 {wk_need} 次活動。" if wk_need else "\n本週活動已達標。")
            )
        ups = ctx.get("upcoming") or []
        if ups:
            u = ups[0]
            return (
                f"{name}，今日冇逾期案。最近一單係 **{u['person']}**"
                f"（{u['next_date']}）：{u['next_action'] or '未填 Next action'}。"
            )
        if hints:
            return (
                f"{name}，名單入面暫時搵唔到 **{hints[0]}**。"
                "可以核對打卡個名，或者喺準客戶名單睇下有冇呢位。"
            )
        return (
            f"{name}，今日冇逾期／到期跟進。可以去準客戶名單推下一單，"
            "或者話我知個案名，我幫你查。"
        )

    if intent == "upcoming":
        ups = ctx.get("upcoming") or []
        if not ups:
            return f"{name}，未來 7 日未有跟進日期——打卡時記得填 Next action + 日期。"
        lines = [f"{name}，未來 7 日有 **{len(ups)}** 宗："]
        for u in ups[:5]:
            lines.append(
                f"- **{u['person']}**（{u['track']}）· {u['next_date']} · "
                f"{u['next_action'] or '—'}"
            )
        return "\n".join(lines)

    if intent == "stuck":
        stuck = hits.get("stuck") or due
        if not stuck:
            return f"{name}，而家未見明顯卡住個案。做得好，保持節奏。"
        lines = [f"{name}，需要關注嘅卡住／逾期："]
        for d in stuck[:5]:
            extra = ""
            if d.get("overdue_days"):
                extra = f" · 逾期 {d['overdue_days']} 日"
            lines.append(
                f"- **{d['person']}**（{d['stage']}）→ {d['next_action'] or '—'}"
                f"{extra}"
            )
        return "\n".join(lines)

    if intent == "prospect":
        pros = pr_hits or (ctx.get("prospects") or [])
        if not pros:
            return (
                f"{name}，準客戶名單暫時未有資料。"
                "去「準客戶名單」加名，之後問我「拆某某」我就可以查。"
            )
        lines = [f"{name}，你最近準客戶："]
        for p in pros[:5]:
            lines.append(
                f"- **{p.get('name')}** · FYC ${float(p.get('fyc') or 0):,.0f}"
                + (f" · {p.get('products')}" if p.get("products") else "")
            )
        lines.append("\n想拆邊單？回覆人名就得。")
        return "\n".join(lines)

    if intent == "metrics":
        return (
            f"{name}，即時數字：\n"
            f"- YTD FYC **${ctx.get('ytd_fyc', 0):,.0f}**"
            + (
                "（Extra 10 已開）\n"
                if ctx.get("extra10_open")
                else f"（Extra 10 尚欠 ${ctx.get('extra10_remaining', 0):,.0f}）\n"
            )
            + f"- 2027 MDRT **${ctx.get('mdrt_progress', 0):,.0f}**"
            f"（{ctx.get('mdrt_pct', 0):.0f}%），尚欠 ${ctx.get('mdrt_remaining', 0):,.0f}\n\n"
            "下一步：大單用準客戶名單計實 FYC；危疾／5年供／扣稅年金優先。"
        )

    if intent == "week":
        return (
            f"{name}，本週活動 **{ctx.get('wk_count')}/{ctx.get('wk_min')}**"
            + (
                f"——仲欠 **{wk_need}** 次，今日約見面或傾保險並即刻打卡。"
                if wk_need
                else "——已達標。可以專心清卡案／推準客戶。"
            )
        )

    if intent == "recruit":
        return (
            f"{name}，招募人數 **{ctx.get('recruit', 0)}**（年度目標通常 2 人）。\n"
            "準客戶名單→招募 List 加名；打卡選「傾招募／報考試／出code」。"
        )

    if intent == "tools":
        return (
            f"{name}，呢啲喺 M+2 側欄／選單：\n"
            "- 醫療融資計算機、保障缺口、收入／支出 T-Account、常見疾病核保\n"
            "用完可以返嚟問我點解釋俾客戶聽。"
        )

    if intent == "product":
        try:
            from tt_core.product_knowledge import offline_product_reply

            ans = offline_product_reply(text, username=str(name))
            if ans:
                return ans
        except Exception:
            pass
        return (
            f"{name}，你可以問我 **危疾全應援**（所需全／更周全／摯齊全）、"
            "家添守護、樂齡無憂點賣。細節以計劃書為準。"
        )

    if intent == "checkin_write":
        return (
            f"{name}，我可以幫你**提議打卡**，但要你確認先會寫入。\n"
            "打卡一定要齊：\n"
            "1. 名字　2. 見面日期　3. Next action　4. 跟進日期　5. 階段　"
            "6. Fact find 15 條全部有答\n\n"
            "請一次過俾齊（或者喺下面「待確認打卡」表格填），填完先可以撳確認執行。\n"
            "（改業績／招募數字只有 Admin／Leader 可以提議。）"
        )

    if intent == "priority":
        actions = _priority_actions(ctx)
        bullets = "\n".join(f"{i+1}. {a}" for i, a in enumerate(actions[:3]))
        return (
            f"{name}，按而家 M+2 數據，今日建議咁排：\n\n{bullets}\n\n"
            "想拆某一單，直接講人名。"
        )

    # clarify — do NOT dump the same Extra 10 priority template
    return (
        f"{name}，我未完全捉到你想問邊方面。你可以問得再具體啲，例如：\n"
        "- 「今日最應該做咩」\n"
        "- 「本週活動仲欠幾多」\n"
        "- 「MDRT 進度」\n"
        "- 「準客戶有邊幾個」\n"
        "- 「幫我拆 Ave 點跟」\n"
    )


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


def _gemini_contents(messages: list[dict[str, str]]) -> list[dict[str, Any]]:
    """Build Gemini contents with strictly alternating user/model roles."""
    contents: list[dict[str, Any]] = []
    for m in messages:
        role = "user" if m.get("role") == "user" else "model"
        text = str(m.get("content") or "").strip()
        if not text:
            continue
        if contents and contents[-1]["role"] == role:
            # Merge consecutive same-role turns (Gemini rejects duplicates)
            prev = contents[-1]["parts"][0].get("text") or ""
            contents[-1]["parts"][0]["text"] = f"{prev}\n\n{text}"
        else:
            contents.append({"role": role, "parts": [{"text": text}]})
    if contents and contents[0]["role"] == "model":
        contents.insert(0, {"role": "user", "parts": [{"text": "開始。"}]})
    if not contents:
        contents = [{"role": "user", "parts": [{"text": "你好"}]}]
    if contents[-1]["role"] != "user":
        contents.append({"role": "user", "parts": [{"text": "請繼續。"}]})
    return contents


def _gemini_model_candidates(preferred: str) -> list[str]:
    """Current GA Flash models — rewrite retired 2.x / 2.5 ids."""
    out: list[str] = []
    pref = (preferred or DEFAULT_GEMINI_MODEL).strip()
    pref = _GEMINI_MODEL_REWRITE.get(pref, pref)
    if pref and "latest" not in pref.lower():
        out.append(pref)
    for mid in GEMINI_MODEL_FALLBACKS:
        mid = _GEMINI_MODEL_REWRITE.get(mid, mid)
        if mid and mid not in out:
            out.append(mid)
    return out[:4]


def _friendly_gemini_error(raw: str) -> str:
    t = (raw or "").strip()
    low = t.lower()
    if "503" in t or "high demand" in low or "unavailable" in low:
        return (
            "Google 模型而家好忙（503）。系統已自動試其他穩定模型仍失敗——"
            "請隔一兩分鐘再撳「測試連線」。\n\n"
            f"技術詳情：{t[:220]}"
        )
    if "429" in t or "resource_exhausted" in low or "quota" in low:
        return (
            "AI 配額／限流（429）。請稍後再試，或去 AI Studio 檢查免費額度。\n\n"
            f"技術詳情：{t[:220]}"
        )
    if "timed out" in low or "timeout" in low:
        return (
            "連線逾時（網絡慢或 Google 回應慢）。請再試一次；"
            "若多次失敗，稍後再測。\n\n"
            f"技術詳情：{t[:220]}"
        )
    if "401" in t or "403" in t or "api key" in low:
        return (
            "AI key 無效或未開權限。請確認係 AI Studio 嘅 Gemini API key "
            "（AQ… 或 AIza…），再儲存後測試。\n\n"
            f"技術詳情：{t[:220]}"
        )
    if "404" in t or "no longer available" in low or "not_found" in low:
        return (
            "Google 已停用舊模型名稱（例如 gemini-2.5-flash）。"
            "App 已改用 gemini-3.8-flash——請再撳「測試連線」。\n\n"
            f"技術詳情：{t[:220]}"
        )
    return t[:400] or "AI 連線失敗"


def gemini_chat(
    messages: list[dict[str, str]],
    *,
    system: str,
    api_key: str,
    model: str = DEFAULT_GEMINI_MODEL,
    timeout: int = 60,
) -> str:
    """Google AI Studio generateContent.

    New AI Studio keys are auth keys (``AQ.…``). Prefer ``x-goog-api-key``
    header; also try ``?key=`` for older ``AIza…`` traffic keys.

    On HTTP 503/429 (model busy), skip straight to the next stable model —
    do not burn the whole timeout on ``gemini-flash-latest``.
    """
    key = str(api_key or "").strip()
    if not key:
        raise RuntimeError("未設定 AI key")

    contents = _gemini_contents(messages)
    model_candidates = _gemini_model_candidates(model)

    # Prefer systemInstruction; one fallback merges system into first user turn.
    # Gemini 3.x deprecates sampling knobs (temperature/top_p) — omit them.
    payload_variants: list[dict[str, Any]] = [
        {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": contents,
        },
    ]
    merged = [dict(c) for c in contents]
    first_text = merged[0]["parts"][0]["text"]
    merged[0] = {
        "role": "user",
        "parts": [{"text": f"{system}\n\n---\n\n{first_text}"}],
    }
    payload_variants.append({"contents": merged})

    # AQ… auth keys → header first; legacy AIza… → query first
    if key.startswith("AQ"):
        auth_styles: tuple[str, ...] = ("header", "query")
    elif key.startswith("AIza"):
        auth_styles = ("query", "header")
    else:
        auth_styles = ("header", "query")

    per_try_timeout = max(8, min(int(timeout or 20), 20))
    deadline = time.time() + max(28.0, float(timeout or 20) + 8)

    last_err = ""
    for mid in model_candidates:
        if time.time() > deadline:
            break
        model_overloaded = False
        model_missing = False
        for payload in payload_variants:
            if time.time() > deadline or model_overloaded or model_missing:
                break
            for auth in auth_styles:
                if time.time() > deadline or model_overloaded or model_missing:
                    break
                if auth == "header":
                    url = (
                        "https://generativelanguage.googleapis.com/v1beta/models/"
                        f"{urllib.parse.quote(mid, safe='')}:generateContent"
                    )
                    headers = {
                        "Content-Type": "application/json",
                        "x-goog-api-key": key,
                    }
                else:
                    qs = urllib.parse.urlencode({"key": key})
                    url = (
                        "https://generativelanguage.googleapis.com/v1beta/models/"
                        f"{urllib.parse.quote(mid, safe='')}:generateContent?{qs}"
                    )
                    headers = {"Content-Type": "application/json"}
                req = urllib.request.Request(
                    url,
                    data=json.dumps(payload).encode("utf-8"),
                    headers=headers,
                    method="POST",
                )
                try:
                    with urllib.request.urlopen(req, timeout=per_try_timeout) as resp:
                        data = json.loads(resp.read().decode("utf-8"))
                    cands = data.get("candidates") or []
                    if not cands:
                        pf = data.get("promptFeedback") or {}
                        last_err = f"無回覆（{mid}/{auth}）：{pf or data}"[:300]
                        continue
                    parts = cands[0].get("content", {}).get("parts", [])
                    text = "".join(str(p.get("text") or "") for p in parts).strip()
                    if not text:
                        last_err = f"回覆空白（{mid}/{auth}）"
                        continue
                    return text
                except urllib.error.HTTPError as e:
                    body = e.read().decode("utf-8", errors="replace")[:400]
                    last_err = f"HTTP {e.code}（{mid}/{auth}）：{body}"
                    if e.code in (401, 403):
                        # Try the other auth style once; if both fail, raise friendly
                        if auth == auth_styles[-1]:
                            raise RuntimeError(_friendly_gemini_error(last_err)) from e
                        continue
                    # Busy / rate-limited → next model immediately
                    if e.code in (429, 503):
                        model_overloaded = True
                        break
                    # Unknown model id → next model
                    if e.code == 404:
                        model_missing = True
                        break
                    continue
                except Exception as e:
                    # Socket timeout / network — try next auth, then next model
                    last_err = str(e)[:300]
                    if "timed out" in last_err.lower() or "timeout" in last_err.lower():
                        # Don't burn remaining payload variants on a dead link
                        model_overloaded = True
                        break
                    continue
        # brief pause before next model when Google is saturated
        if model_overloaded and time.time() + 0.4 < deadline:
            time.sleep(0.35)
    raise RuntimeError(_friendly_gemini_error(last_err or "AI 連線失敗"))


def test_ai_connection() -> tuple[bool, str]:
    """Leader smoke-test: one short round-trip. Returns (ok, message)."""
    gemini_key = _secret_gemini_key()
    if gemini_key:
        try:
            text = gemini_chat(
                [{"role": "user", "content": "用一句粵語講：已接通。"}],
                system="你係 AI Tim。只回一句短確認。",
                api_key=gemini_key,
                model=_secret_gemini_model() or DEFAULT_GEMINI_MODEL,
                timeout=25,
            )
            return True, f"連線成功：{text[:120]}"
        except Exception as e:
            return False, _friendly_gemini_error(str(e))[:400]
    openai_key = _secret_openai_key()
    if openai_key:
        try:
            text = openai_chat(
                [{"role": "user", "content": "用一句粵語講：已接通。"}],
                system="你係 AI Tim。只回一句短確認。",
                api_key=openai_key,
                model=_secret_model(),
                timeout=25,
            )
            return True, f"連線成功：{text[:120]}"
        except Exception as e:
            return False, str(e)[:400]
    return False, "未設定 AI key"


def reply(
    user_text: str,
    history: list[dict[str, str]],
    ctx: dict[str, Any],
) -> tuple[str, str, dict[str, Any]]:
    """
    Returns (assistant_text, mode, meta).
    mode: 'gemini' | 'openai' | 'offline'
    Prefer free Gemini, then OpenAI, then offline templates.
    """
    username = str((ctx or {}).get("username") or "")
    role = str((ctx or {}).get("role") or "Member")
    live_ctx, tools_used = gather_live_context(
        username, user_text, role=role, base_ctx=ctx
    )
    meta = {"tools_used": tools_used, "provider": llm_provider()}

    system = system_prompt(live_ctx)
    messages = list(history or []) + [{"role": "user", "content": user_text}]
    if len(messages) > 16:
        messages = messages[-16:]

    def _remember_err(msg: str) -> None:
        # Only put errors on meta — safe for background threads (no session_state).
        meta["ai_error"] = msg

    gemini_key = _secret_gemini_key()
    gemini_err = ""
    if gemini_key:
        try:
            text = gemini_chat(
                messages,
                system=system,
                api_key=gemini_key,
                model=_secret_gemini_model(),
                timeout=25,
            )
            meta["provider"] = "gemini"
            meta.pop("ai_error", None)
            return _finalize_reply(text, "gemini", meta, live_ctx)
        except Exception as e:
            gemini_err = str(e)[:400]
            _remember_err(gemini_err)

    openai_key = _secret_openai_key()
    if openai_key:
        try:
            text = openai_chat(
                messages,
                system=system,
                api_key=openai_key,
                model=_secret_model(),
                timeout=25,
            )
            meta["provider"] = "openai"
            meta.pop("ai_error", None)
            return _finalize_reply(text, "openai", meta, live_ctx)
        except Exception as e:
            _remember_err(str(e)[:400])
            fallback = offline_reply(user_text, live_ctx)
            return _finalize_reply(
                f"（AI 暫時連線唔到，已改用即時教練資料）\n\n{fallback}",
                "offline",
                meta,
                live_ctx,
            )

    if gemini_err:
        fallback = offline_reply(user_text, live_ctx)
        return _finalize_reply(
            f"（AI 暫時連線唔到，已改用即時教練資料）\n\n{fallback}",
            "offline",
            meta,
            live_ctx,
        )
    return _finalize_reply(
        offline_reply(user_text, live_ctx), "offline", meta, live_ctx
    )


def _finalize_reply(
    text: str,
    mode: str,
    meta: dict[str, Any],
    live_ctx: dict[str, Any],
) -> tuple[str, str, dict[str, Any]]:
    """Parse optional write-action proposal from model text into meta.pending."""
    try:
        from tt_core.coach_writes import (
            build_pending,
            parse_action_from_reply,
            strip_action_fence,
            summarize_pending,
        )

        raw_action = parse_action_from_reply(text)
        visible = strip_action_fence(text) if raw_action else text
        if raw_action:
            pending = build_pending(
                str(raw_action.get("type") or ""),
                {k: v for k, v in raw_action.items() if k != "type"},
                username=str(live_ctx.get("username") or ""),
                role=str(live_ctx.get("role") or "Member"),
            )
            meta["pending"] = pending
            summary = summarize_pending(pending)
            if summary and summary not in visible:
                visible = f"{visible}\n\n{summary}"
        return visible, mode, meta
    except Exception:
        return text, mode, meta


def welcome_message(ctx: dict[str, Any]) -> str:
    due_n = len(ctx.get("due") or [])
    name = ctx.get("username") or ""
    bit = f"今日有 **{due_n}** 宗要跟。" if due_n else "今日冇逾期案——保持！"
    mode = "AI 教練" if llm_configured() else "教練"
    channel = str(ctx.get("channel") or "app").strip().lower()
    if channel == "telegram":
        return (
            f"你好 {name}，我係 **Coach Tim／AI Tim**（Telegram · {mode}）。"
            f"{bit}\n\n"
            "可以問產品（例如危疾全應援點賣）、下一步點做、拆邊單；"
            "綁定 M+2 用 `/link 你的帳號`。"
        )
    return (
        f"你好 {name}，我係 **AI Tim**（{mode}）。"
        f"已讀你嘅業績、本週活動、跟進同準客戶。{bit}\n\n"
        "可以直接問下一步點做、拆邊單、本週活動、MDRT／Extra 10、危疾全應援點賣；"
        "要打卡可以講「幫我打卡」——齊料後你確認先會寫入。"
    )
