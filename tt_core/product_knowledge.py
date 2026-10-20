"""Product knowledge packs for AI Tim (brochures → structured coaching brief)."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_DATA_DIR = Path(__file__).resolve().parent / "data_files"

# Registry of onboarded product packs (filename stem → id)
_PACK_FILES = (
    "crisis_allsupporter.json",
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


def match_product_packs(query: str) -> list[dict[str, Any]]:
    """Return packs whose name/aliases appear in the user question."""
    q = (query or "").strip().lower()
    if not q:
        return []
    hits: list[dict[str, Any]] = []
    for pack in list_product_packs():
        aliases = [str(pack.get("name_zh") or ""), str(pack.get("name_en") or "")]
        aliases.extend(str(a) for a in (pack.get("aliases") or []))
        aliases.append(str(pack.get("category") or ""))
        if any(a and a.lower() in q for a in aliases if a):
            hits.append(pack)
            continue
        # Broader CI product intent → AllSupporter when asking 危疾產品
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
    return hits


def product_query_intent(text: str) -> bool:
    """True when the user is asking about FWD products / 危疾全應援."""
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
    )
    return any(k in low or k in t for k in keys)


def format_pack_brief(pack: dict[str, Any], *, max_chars: int = 3500) -> str:
    """Compact markdown brief for system prompt / offline coach."""
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
        # Default to AllSupporter when asking generic 危疾產品
        pack = get_product_pack("crisis_allsupporter")
        packs = [pack] if pack else []
    if not packs:
        return ""
    return "\n\n".join(format_pack_brief(p) for p in packs)


def offline_product_reply(query: str, *, username: str = "你") -> str | None:
    """Short Cantonese product coaching reply without LLM."""
    packs = match_product_packs(query)
    if not packs and product_query_intent(query):
        pack = get_product_pack("crisis_allsupporter")
        packs = [pack] if pack else []
    if not packs:
        return None
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
