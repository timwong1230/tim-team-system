"""Product knowledge packs for AI Tim (brochures → structured coaching brief)."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_DATA_DIR = Path(__file__).resolve().parent / "data_files"

# Registry of onboarded knowledge packs (product + training)
_PACK_FILES = (
    "crisis_allsupporter.json",
    "mdrt_fundamentals.json",
)


@lru_cache(maxsize=8)
def _load_pack_file(name: str) -> dict[str, Any]:
    path = _DATA_DIR / name
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not data.get("id"):
        raise ValueError(f"Invalid product pack: {name}")
    return data


def list_product_packs() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for name in _PACK_FILES:
        try:
            out.append(_load_pack_file(name))
        except Exception:
            continue
    return out


def get_product_pack(pack_id: str) -> dict[str, Any] | None:
    pid = (pack_id or "").strip().lower()
    for pack in list_product_packs():
        if str(pack.get("id") or "").lower() == pid:
            return pack
    return None


def _pack_aliases(pack: dict[str, Any]) -> list[str]:
    aliases = [str(pack.get("name_zh") or ""), str(pack.get("name_en") or "")]
    aliases.extend(str(a) for a in (pack.get("aliases") or []))
    aliases.append(str(pack.get("category") or ""))
    for st in pack.get("stages") or []:
        aliases.append(str(st.get("problem") or ""))
        aliases.append(str(st.get("target") or ""))
    return [a for a in aliases if a]


def match_stage(pack: dict[str, Any], query: str) -> dict[str, Any] | None:
    """Best-matching MDRT stage for a question, if any."""
    if pack.get("pack_type") != "skills":
        return None
    q = (query or "").strip()
    low = q.lower()
    stages = list(pack.get("stages") or [])
    # Prefer explicit problem keywords (longer first)
    scored: list[tuple[int, dict[str, Any]]] = []
    for st in stages:
        problem = str(st.get("problem") or "")
        target = str(st.get("target") or "")
        score = 0
        for key in (problem, target):
            if key and (key in q or key.lower() in low):
                score += len(key)
        # Extra keyword hooks per stage id
        hooks = {
            1: ("人脈", "識人", "開發客"),
            2: ("約唔到", "約唔到人", "約唔到客", "見唔到面", "約見"),
            3: ("無客見", "冇客", "開口機會", "搵客"),
            4: ("唔敢開口", "唔識開口", "點開口", "開話題"),
            5: ("切入點", "招式太少", "隔篩"),
            6: ("異議", "反對", "已經買晒", "冇錢", "claim"),
            7: ("簽約", "成交", "申請", "未能簽"),
            8: ("轉介紹", "轉介", "referral", "介紹客"),
        }
        for h in hooks.get(int(st.get("id") or 0), ()):
            if h.lower() in low or h in q:
                score += len(h) + 2
        if score:
            scored.append((score, st))
    if not scored:
        return None
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[0][1]


def match_product_packs(query: str) -> list[dict[str, Any]]:
    """Return packs whose name/aliases/stages appear in the user question."""
    q = (query or "").strip().lower()
    raw = (query or "").strip()
    if not q:
        return []
    hits: list[dict[str, Any]] = []
    for pack in list_product_packs():
        if any(a and a.lower() in q for a in _pack_aliases(pack)):
            hits.append(pack)
            continue
        if pack.get("id") == "crisis_allsupporter" and any(
            k in q
            for k in (
                "危疾產品",
                "危疾計劃",
                "危疾點賣",
                "危疾點講",
                "ci plan",
                "critical illness",
            )
        ):
            hits.append(pack)
            continue
        if pack.get("id") == "mdrt_fundamentals" and (
            match_stage(pack, raw) is not None
            or any(
                k in raw or k in q
                for k in (
                    "基本功",
                    "難關",
                    "話術",
                    "script",
                    "新人培訓",
                    "點約",
                    "點開",
                    "轉介紹",
                    "異議",
                )
            )
        ):
            hits.append(pack)
    return hits


def product_query_intent(text: str) -> bool:
    """True when asking about products OR MDRT fundamentals / scripts."""
    t = (text or "").strip()
    low = t.lower()
    if match_product_packs(t):
        return True
    keys = (
        "產品",
        "計劃書",
        "brochure",
        "點賣",
        "點講",
        "selling point",
        "賣點",
        "危疾",
        "應援",
        "allsupporter",
        "所需全",
        "更周全",
        "摯齊全",
        "家添守護",
        "樂齡無憂",
        "mdrt",
        "基本功",
        "難關",
        "話術",
        "script",
        "無人脈",
        "約唔到",
        "無客見",
        "唔敢開口",
        "唔識開口",
        "切入點",
        "異議",
        "轉介紹",
        "簽約",
        "新人培訓",
    )
    return any(k in low or k in t for k in keys)


def format_skills_brief(pack: dict[str, Any], *, query: str = "", max_chars: int = 4500) -> str:
    """Compact brief for MDRT fundamentals / script packs."""
    lines: list[str] = [
        f"## 培訓知識：{pack.get('name_zh')}（{pack.get('name_en')}）",
        f"- 類型：{pack.get('category')}",
        f"- 定位：{pack.get('tagline')}",
        "### 8 難關（問題 → 目標）",
    ]
    for st in pack.get("stages") or []:
        lines.append(
            f"{st.get('id')}. **{st.get('problem')}** → {st.get('target')}"
            f"（{st.get('coach_focus')}）"
        )

    focus = match_stage(pack, query) if query else None
    stages_to_show = [focus] if focus else list(pack.get("stages") or [])[:3]
    if stages_to_show:
        lines.append("### 話術示範（每關 A/B/C）")
        for st in stages_to_show:
            if not st:
                continue
            lines.append(
                f"#### 難關 {st.get('id')}：{st.get('problem')} → {st.get('target')}"
            )
            for sc in st.get("scripts") or []:
                lines.append(f"- **{sc.get('label')}**：{sc.get('text')}")

    track = pack.get("coach_talk_track") or []
    if track:
        lines.append("### 教練用法")
        for t in track:
            lines.append(f"- {t}")

    discs = pack.get("disclaimers") or []
    if discs:
        lines.append("### 免責")
        for d in discs:
            lines.append(f"- {d}")

    source = pack.get("source_note") or ""
    if source:
        lines.append(f"_來源：{source}_")

    text = "\n".join(lines)
    if len(text) > max_chars:
        return text[: max_chars - 20] + "\n…（已截斷）"
    return text


def format_pack_brief(pack: dict[str, Any], *, max_chars: int = 3500, query: str = "") -> str:
    """Compact markdown brief for system prompt / offline coach."""
    if pack.get("pack_type") == "skills":
        return format_skills_brief(pack, query=query, max_chars=max(max_chars, 4500))

    lines: list[str] = [
        f"## 產品知識：{pack.get('name_zh')}（{pack.get('name_en')}）",
        f"- 公司：{pack.get('insurer')}",
        f"- 類型：{pack.get('category')}",
        f"- 定位：{pack.get('tagline')}",
    ]
    core = pack.get("core_facts") or {}
    if core:
        lines.append("### 基本資料")
        lines.append(f"- 貨幣：{core.get('currency')}")
        lines.append(f"- 保障期：{core.get('benefit_term')}")
        lines.append(f"- 供款年期：{'／'.join(str(x) for x in (core.get('premium_terms_years') or []))}")
        lines.append(
            f"- 投保額：最低 US${core.get('min_sum_assured_usd'):,}；"
            f"最高每被保人 US${core.get('max_sum_assured_usd_per_life'):,}"
        )
        lines.append(f"- 保費：{core.get('premium_structure')}")
        if core.get("entry_age_by_pay_term_note"):
            lines.append(f"- 投保年齡：{core.get('entry_age_by_pay_term_note')}")

    levels = pack.get("plan_levels") or []
    if levels:
        lines.append("### 三個計劃級別")
        for lv in levels:
            bits = "；".join((lv.get("highlights") or [])[:5])
            lines.append(
                f"- **{lv.get('name_zh')}**（{lv.get('positioning')}｜投保年齡 {lv.get('entry_age')}）：{bits}"
            )

    benefits = pack.get("key_benefits") or []
    if benefits:
        lines.append("### 主要權益")
        for b in benefits:
            lines.append(f"- **{b.get('name')}**：{b.get('summary')}")

    riders = pack.get("optional_riders") or []
    if riders:
        lines.append("### 自選／附約")
        for r in riders:
            lines.append(f"- **{r.get('name')}**：{r.get('summary')}")

    angles = pack.get("sales_angles") or []
    if angles:
        lines.append("### 銷售角度")
        for a in angles:
            lines.append(f"- {a}")

    track = pack.get("coach_talk_track") or []
    if track:
        lines.append("### 見客講稿提示")
        for t in track:
            lines.append(f"- {t}")

    discs = pack.get("disclaimers") or []
    if discs:
        lines.append("### 免責")
        for d in discs:
            lines.append(f"- {d}")

    source = pack.get("source_note") or ""
    if source:
        lines.append(f"_來源：{source}_")

    text = "\n".join(lines)
    if len(text) > max_chars:
        return text[: max_chars - 20] + "\n…（已截斷）"
    return text


def format_matched_briefs(query: str, *, max_packs: int = 2) -> str:
    packs = match_product_packs(query)[:max_packs]
    if not packs and product_query_intent(query):
        # Prefer skills when question looks like a gate; else product
        skills = get_product_pack("mdrt_fundamentals")
        if skills and match_stage(skills, query):
            packs = [skills]
        else:
            pack = get_product_pack("crisis_allsupporter")
            packs = [pack] if pack else []
    if not packs:
        return ""
    return "\n\n".join(format_pack_brief(p, query=query) for p in packs)


def offline_skills_reply(query: str, *, username: str = "你") -> str | None:
    pack = get_product_pack("mdrt_fundamentals")
    if not pack:
        return None
    stage = match_stage(pack, query)
    if not stage and not any(
        k in (query or "")
        for k in ("基本功", "難關", "話術", "MDRT", "mdrt", "新人培訓", "script", "Script")
    ):
        return None
    if not stage:
        # Overview of all 8 gates
        lines = [
            f"{username}，呢套係 **MDRT 基本功模型**（GOAHEAD）——8 個難關：",
            "",
        ]
        for st in pack.get("stages") or []:
            lines.append(f"{st.get('id')}. **{st.get('problem')}** → {st.get('target')}")
        lines.append("")
        lines.append("講俾我知你卡喺邊關（例如「約唔到人」「異議處理」），我即刻俾 3 段 Script。")
        return "\n".join(lines)

    scripts = stage.get("scripts") or []
    script_lines = "\n".join(
        f"- **{sc.get('label')}**：{sc.get('text')}" for sc in scripts[:3]
    )
    return (
        f"{username}，你而家似卡喺難關 **{stage.get('id')}：{stage.get('problem')}**"
        f"→ 目標係 **{stage.get('target')}**。\n\n"
        f"教練重點：{stage.get('coach_focus')}\n\n"
        f"今日試一段（示範，請按對方語氣改）：\n{script_lines}\n\n"
        "Script 只係示範——改埋名同語氣。想要下一關或者產品點接（例如危疾全應援），直接問。"
    )


def offline_product_reply(query: str, *, username: str = "你") -> str | None:
    """Short Cantonese coaching reply (product or MDRT skills) without LLM."""
    packs = match_product_packs(query)
    # Skills first when a stage matches
    skills = get_product_pack("mdrt_fundamentals")
    if skills and (match_stage(skills, query) or any(p.get("id") == "mdrt_fundamentals" for p in packs)):
        # If query is clearly product, skip skills
        productish = any(
            k in (query or "")
            for k in ("危疾", "全應援", "所需全", "更周全", "摯齊全", "家添守護", "樂齡無憂", "AllSupporter")
        )
        if not productish:
            ans = offline_skills_reply(query, username=username)
            if ans:
                return ans

    if not packs and product_query_intent(query):
        pack = get_product_pack("crisis_allsupporter")
        packs = [pack] if pack else []
    packs = [p for p in packs if p and p.get("pack_type") != "skills"]
    if not packs:
        # Fall back to skills overview
        return offline_skills_reply(query, username=username)
    pack = packs[0]
    levels = pack.get("plan_levels") or []
    level_line = "／".join(
        f"{lv.get('name_zh')}（{lv.get('positioning')}）" for lv in levels
    )
    angles = pack.get("sales_angles") or []
    track = pack.get("coach_talk_track") or []
    bullets = []
    if level_line:
        bullets.append(f"三級：**{level_line}**——先問預算同有冇小朋友再分級。")
    for a in angles[:2]:
        bullets.append(a)
    if track:
        bullets.append(track[0])
    bullet_txt = "\n".join(f"- {b}" for b in bullets[:4])
    return (
        f"{username}，關於 **{pack.get('name_zh')}**：\n\n"
        f"{pack.get('tagline')}\n\n"
        f"{bullet_txt}\n\n"
        "記住：紅利非保證；細節以計劃書／條款為準。想我比較「所需全 vs 更周全」"
        "或者點講家添守護／樂齡無憂，直接問就得。"
    )


def export_telegram_knowledge(*, max_chars: int = 16000) -> str:
    """Full knowledge document for Telegram Coach Tim / Custom GPT upload."""
    lines: list[str] = [
        "# TIM TEAM · Telegram Coach Tim 知識庫",
        "",
        "用途：俾 Telegram Coach Tim AI／Custom GPT 作為內部培訓知識。",
        "包含：產品（危疾全應援）＋ MDRT 基本功模型／8 難關 × 3 段 Script。",
        "細節以正式計劃書為準；話術請按合規同客戶情況調整。",
        "",
    ]
    for pack in list_product_packs():
        lines.append(format_pack_brief(pack, max_chars=max_chars, query=""))
        brochure = str(pack.get("brochure_file") or "").strip()
        if brochure:
            lines.append(f"- 參考檔：`{brochure}`")
        scripts = str(pack.get("scripts_file") or "").strip()
        if scripts:
            lines.append(f"- 話術圖：`{scripts}`")
        # Full scripts for skills packs in export
        if pack.get("pack_type") == "skills":
            lines.append("### 完整 8 關 Script")
            for st in pack.get("stages") or []:
                lines.append(
                    f"#### {st.get('id')}. {st.get('problem')} → {st.get('target')}"
                )
                for sc in st.get("scripts") or []:
                    lines.append(f"- **{sc.get('label')}**：{sc.get('text')}")
        lines.append("")
    text = "\n".join(lines).strip() + "\n"
    if len(text) > max_chars:
        return text[: max_chars - 20] + "\n…（已截斷）\n"
    return text


def telegram_knowledge_path() -> Path:
    return _DATA_DIR / "telegram_coach_knowledge.md"


def write_telegram_knowledge_file() -> Path:
    """Materialize export next to other data_files (for download / GPT upload)."""
    path = telegram_knowledge_path()
    path.write_text(export_telegram_knowledge(), encoding="utf-8")
    return path


def product_pack_labels() -> list[str]:
    return [str(p.get("name_zh") or p.get("id") or "") for p in list_product_packs()]
