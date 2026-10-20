"""Product knowledge packs for AI Tim."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def test_crisis_allsupporter_pack_loads():
    from tt_core.product_knowledge import get_product_pack, list_product_packs

    packs = list_product_packs()
    assert any(p.get("id") == "crisis_allsupporter" for p in packs)
    pack = get_product_pack("crisis_allsupporter")
    assert pack is not None
    assert "危疾全應援" in pack["name_zh"]
    assert len(pack.get("plan_levels") or []) == 3
    names = [lv["name_zh"] for lv in pack["plan_levels"]]
    assert "所需全" in names and "更周全" in names and "摯齊全" in names


def test_match_and_brief_for_allsupporter():
    from tt_core.product_knowledge import format_matched_briefs, match_product_packs

    hits = match_product_packs("危疾全應援點賣俾夾心家庭？")
    assert hits and hits[0]["id"] == "crisis_allsupporter"
    brief = format_matched_briefs("AllSupporter 所需全同摯齊全有咩分別")
    assert "危疾全應援" in brief
    assert "所需全" in brief
    assert "家添守護" in brief or "樂齡無憂" in brief
    assert "非保證" in brief or "免責" in brief


def test_offline_product_reply():
    from tt_core.product_knowledge import offline_product_reply

    ans = offline_product_reply("危疾全應援有邊幾個級別？", username="Tim")
    assert ans
    assert "危疾全應援" in ans
    assert "所需全" in ans or "更周全" in ans


def test_brochure_pdf_is_bundled():
    pdf = _ROOT / "static" / "products" / "crisis-allsupporter-insurance-plan-series-tc.pdf"
    assert pdf.is_file()
    assert pdf.stat().st_size > 100_000


def test_telegram_knowledge_export():
    from tt_core.product_knowledge import export_telegram_knowledge, write_telegram_knowledge_file

    md = export_telegram_knowledge()
    assert "Telegram Coach Tim" in md
    assert "危疾全應援" in md
    path = write_telegram_knowledge_file()
    assert path.is_file()
    assert path.name == "telegram_coach_knowledge.md"


def test_coach_routes_product_tool_and_offline():
    from tt_core.coach_tim import (
        TOOL_PRODUCT_KB,
        choose_tools,
        offline_reply,
        run_tool,
        system_prompt,
    )

    tools = choose_tools("危疾全應援點講家添守護？")
    assert TOOL_PRODUCT_KB in tools

    res = run_tool(
        TOOL_PRODUCT_KB,
        username="Tim",
        role="Member",
        query="危疾全應援三個級別分別",
    )
    assert res.get("ok") is True
    assert "危疾全應援" in (res.get("brief") or "")

    ctx = {
        "username": "Tim",
        "role": "Member",
        "ytd_fyc": 0,
        "extra10_open": False,
        "extra10_remaining": 88000,
        "mdrt_progress": 0,
        "mdrt_pct": 0,
        "mdrt_remaining": 512800,
        "mdrt_target": 512800,
        "wk_count": 0,
        "wk_min": 3,
        "wk_need": 3,
        "recruit": 0,
        "due": [],
        "upcoming": [],
        "prospects": [],
        "tool_hits": {},
        "product_brief": res.get("brief") or "",
    }
    sp = system_prompt(ctx)
    assert "產品知識" in sp
    assert "危疾全應援" in sp

    ans = offline_reply("危疾全應援點賣？", ctx)
    assert "危疾全應援" in ans
