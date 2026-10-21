"""Professional PDF renderer for client proposals (not a clone of template design)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from tt_core.client_pdf import resolve_cjk_font
from tt_core.proposal import format_hkd, format_usd

_NAVY = (15, 27, 45)
_INK = (26, 43, 76)
_TEXT = (33, 37, 41)
_MUTED = (100, 110, 120)
_GOLD = (197, 160, 40)
_SOFT = (247, 244, 238)
_LINE = (228, 223, 212)
_WHITE = (255, 255, 255)
_WARN = (180, 83, 9)


def build_proposal_pdf(proposal: dict[str, Any], *, agent: str = "") -> bytes:
    from fpdf import FPDF

    font = resolve_cjk_font()
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_font("TT", "", font)
    pdf.add_font("TT", "B", font)

    client = proposal.get("client") or {}
    _cover_page(pdf, proposal, client, agent=agent)
    for section in proposal.get("sections") or []:
        _section_page(pdf, section, client_name=str(client.get("name") or ""))
    skip_summary = bool(proposal.get("skip_summary")) or not (
        proposal.get("summary_rows") or []
    )
    if not skip_summary:
        _summary_page(pdf, proposal)

    out = pdf.output()
    if isinstance(out, (bytes, bytearray)):
        return bytes(out)
    return bytes(out or b"")


def _cover_page(pdf, proposal: dict[str, Any], client: dict[str, Any], *, agent: str) -> None:
    pdf.add_page()
    # Full-bleed navy band
    pdf.set_fill_color(*_NAVY)
    pdf.rect(0, 0, 210, 297, "F")
    pdf.set_fill_color(*_GOLD)
    pdf.rect(0, 0, 210, 4, "F")

    pdf.set_xy(20, 48)
    pdf.set_text_color(*_GOLD)
    pdf.set_font("TT", "B", 11)
    pdf.cell(0, 8, "TIM TEAM  ·  PROPOSAL", ln=1)

    pdf.set_xy(20, 70)
    pdf.set_text_color(*_WHITE)
    pdf.set_font("TT", "B", 36)
    name = str(client.get("name") or "客戶")
    pdf.multi_cell(170, 14, name)

    pdf.set_xy(20, 100)
    pdf.set_font("TT", "", 16)
    pdf.set_text_color(230, 220, 200)
    pdf.cell(0, 10, str(proposal.get("title") or "計劃書"), ln=1)

    tagline = ""
    for sec in proposal.get("sections") or []:
        if sec.get("angle_tagline"):
            tagline = str(sec.get("angle_tagline"))
            break
    if tagline:
        pdf.set_xy(20, 114)
        pdf.set_font("TT", "", 12)
        pdf.set_text_color(*_GOLD)
        pdf.multi_cell(170, 7, tagline)

    pdf.set_xy(20, 132 if tagline else 120)
    pdf.set_font("TT", "", 12)
    pdf.set_text_color(230, 220, 200)
    bits = [
        f"{client.get('age')} 歲",
        str(client.get("gender") or ""),
    ]
    if client.get("occupation"):
        bits.append(str(client.get("occupation")))
    pdf.cell(0, 8, "  ·  ".join(b for b in bits if b), ln=1)

    pdf.set_xy(20, 250)
    pdf.set_font("TT", "", 10)
    pdf.set_text_color(180, 190, 200)
    stamp = datetime.now().strftime("%Y-%m-%d")
    agent_bit = f"  ·  顧問 {agent}" if agent else ""
    pdf.cell(0, 6, f"製表日期 {stamp}{agent_bit}", ln=1)
    pdf.set_x(20)
    pdf.cell(0, 6, "保障及保費以保險公司正式計劃書為準", ln=1)


def _section_page(pdf, section: dict[str, Any], *, client_name: str) -> None:
    pdf.add_page()
    pdf.set_fill_color(*_SOFT)
    pdf.rect(0, 0, 210, 297, "F")

    # Header bar
    pdf.set_fill_color(*_INK)
    pdf.rect(0, 0, 210, 28, "F")
    pdf.set_text_color(*_GOLD)
    pdf.set_font("TT", "B", 10)
    pdf.set_xy(16, 8)
    pdf.cell(100, 6, str(section.get("category") or ""))
    pdf.set_text_color(200, 210, 220)
    pdf.set_font("TT", "", 9)
    pdf.set_xy(120, 8)
    pdf.cell(70, 6, client_name, align="R")

    pdf.set_text_color(*_TEXT)
    pdf.set_xy(16, 40)
    pdf.set_font("TT", "B", 20)
    pdf.multi_cell(178, 9, str(section.get("product_name") or ""))

    # Premium hero
    y = pdf.get_y() + 4
    pdf.set_fill_color(*_WHITE)
    pdf.set_draw_color(*_LINE)
    pdf.rect(16, y, 178, 22, "FD")
    pdf.set_xy(20, y + 5)
    pdf.set_font("TT", "", 10)
    pdf.set_text_color(*_MUTED)
    pdf.cell(40, 5, "保費")
    pdf.set_xy(20, y + 11)
    pdf.set_font("TT", "B", 14)
    color = _INK if section.get("premium_ok") else _WARN
    pdf.set_text_color(*color)
    pdf.cell(160, 7, str(section.get("premium_display") or "待輸入"))

    y = y + 28
    # Meta grid — skip premium/product (already shown in hero / title)
    rows = [
        (k, v)
        for k, v in (section.get("meta_rows") or [])
        if str(k) not in ("保費", "產品", "年供", "參考來源", "報價")
    ]
    cell_h = 18
    for i, (k, v) in enumerate(rows):
        col = i % 2
        row = i // 2
        x = 16 + col * 90
        yy = y + row * cell_h
        pdf.set_fill_color(*_WHITE)
        pdf.rect(x, yy, 86, cell_h - 2, "FD")
        pdf.set_xy(x + 3, yy + 2)
        pdf.set_font("TT", "", 8)
        pdf.set_text_color(*_MUTED)
        pdf.cell(80, 4, str(k))
        pdf.set_xy(x + 3, yy + 7)
        pdf.set_font("TT", "B", 9)
        pdf.set_text_color(*_TEXT)
        pdf.multi_cell(80, 4, str(v))

    y = y + ((len(rows) + 1) // 2) * cell_h + 4
    promo = section.get("promo") or {}
    if promo.get("detail"):
        detail = str(promo.get("detail") or "")
        fy = str(promo.get("first_year_display") or "")
        note = str(promo.get("note") or "")
        pdf.set_font("TT", "", 9)
        detail_h = float(
            pdf.multi_cell(170, 5, detail, dry_run=True, output="HEIGHT") or 5
        )
        fy_h = 6 if fy else 0
        note_h = 5 if note else 0
        box_h = 10 + detail_h + fy_h + note_h + 4
        if y + box_h > 270:
            pdf.add_page()
            pdf.set_fill_color(*_SOFT)
            pdf.rect(0, 0, 210, 297, "F")
            y = 40
        pdf.set_fill_color(255, 248, 232)
        pdf.set_draw_color(230, 211, 161)
        pdf.rect(16, y, 178, box_h, "FD")
        pdf.set_xy(20, y + 3)
        pdf.set_font("TT", "B", 10)
        pdf.set_text_color(*_INK)
        q = str(promo.get("quarter") or "")
        label = str(promo.get("label") or "保費折扣")
        pdf.cell(170, 5, f"{label}" + (f"  ·  {q}" if q else ""))
        pdf.set_xy(20, y + 9)
        pdf.set_font("TT", "", 9)
        pdf.set_text_color(*_TEXT)
        pdf.multi_cell(170, 5, detail)
        yy = pdf.get_y()
        if fy:
            pdf.set_xy(20, yy + 1)
            pdf.set_font("TT", "B", 10)
            pdf.set_text_color(*_INK)
            pdf.multi_cell(170, 5, fy)
            yy = pdf.get_y()
        if note:
            pdf.set_xy(20, yy + 0.5)
            pdf.set_font("TT", "", 8)
            pdf.set_text_color(*_MUTED)
            pdf.multi_cell(170, 4, note)
        y = y + box_h + 4

    tagline = str(section.get("angle_tagline") or "")
    if tagline:
        pdf.set_xy(16, y)
        pdf.set_font("TT", "B", 11)
        pdf.set_text_color(*_GOLD)
        pdf.multi_cell(178, 6, tagline)
        y = pdf.get_y() + 2

    visual = section.get("visual") or {}
    if visual.get("steps") or visual.get("cards"):
        y = _draw_visual_timeline(pdf, visual, y)

    if section.get("goals"):
        if y > 250:
            pdf.add_page()
            pdf.set_fill_color(*_SOFT)
            pdf.rect(0, 0, 210, 297, "F")
            y = 40
        pdf.set_xy(16, y)
        pdf.set_font("TT", "B", 11)
        pdf.set_text_color(*_INK)
        pdf.cell(0, 7, "目標", ln=1)
        y = pdf.get_y() + 1
        for g in section.get("goals") or []:
            pdf.set_xy(16, y)
            pdf.set_font("TT", "", 10)
            pdf.set_text_color(*_TEXT)
            pdf.multi_cell(178, 5.5, f"•  {g}")
            y = pdf.get_y() + 1

    pdf.set_xy(16, y + 2)
    pdf.set_font("TT", "B", 11)
    pdf.set_text_color(*_INK)
    pdf.cell(0, 7, "計劃重點", ln=1)
    for h in section.get("highlights") or []:
        if pdf.get_y() > 270:
            pdf.add_page()
            pdf.set_fill_color(*_SOFT)
            pdf.rect(0, 0, 210, 297, "F")
        pdf.set_x(16)
        pdf.set_font("TT", "", 10)
        pdf.set_text_color(*_TEXT)
        pdf.multi_cell(178, 5.5, f"•  {h}")

    disc = str(section.get("angle_disclaimer") or "")
    if disc:
        pdf.ln(3)
        pdf.set_x(16)
        pdf.set_font("TT", "", 8)
        pdf.set_text_color(*_MUTED)
        pdf.multi_cell(178, 4, disc)


def _draw_visual_timeline(pdf, visual: dict[str, Any], y: float) -> float:
    """Draw metric cards + 4-step timeline as graphic blocks."""
    cards = list(visual.get("cards") or [])
    steps = list(visual.get("steps") or [])
    if y > 200:
        pdf.add_page()
        pdf.set_fill_color(*_SOFT)
        pdf.rect(0, 0, 210, 297, "F")
        y = 40

    pdf.set_xy(16, y)
    pdf.set_font("TT", "B", 11)
    pdf.set_text_color(*_INK)
    pdf.cell(0, 6, str(visual.get("caption") or "圖像時間線"), ln=1)
    y = pdf.get_y() + 2

    # 2x2 metric cards
    if cards:
        card_h = 22
        for i, c in enumerate(cards[:4]):
            col = i % 2
            row = i // 2
            x = 16 + col * 90
            yy = y + row * (card_h + 3)
            pdf.set_fill_color(238, 242, 247)
            pdf.set_draw_color(*_LINE)
            pdf.rect(x, yy, 86, card_h, "FD")
            pdf.set_xy(x + 3, yy + 3)
            pdf.set_font("TT", "", 8)
            pdf.set_text_color(*_MUTED)
            pdf.cell(80, 4, str(c.get("label") or ""))
            pdf.set_xy(x + 3, yy + 8)
            pdf.set_font("TT", "B", 12)
            pdf.set_text_color(*_INK)
            pdf.cell(80, 5, str(c.get("value") or ""))
            pdf.set_xy(x + 3, yy + 14)
            pdf.set_font("TT", "", 8)
            pdf.set_text_color(*_GOLD)
            pdf.cell(80, 4, str(c.get("sub") or ""))
        y = y + ((min(len(cards), 4) + 1) // 2) * (card_h + 3) + 4

    # 4 timeline steps
    if steps:
        if y > 220:
            pdf.add_page()
            pdf.set_fill_color(*_SOFT)
            pdf.rect(0, 0, 210, 297, "F")
            y = 40
        fills = {
            "pay": (232, 238, 247),
            "pot": (255, 244, 214),
            "enjoy": (231, 246, 238),
            "roll": (243, 238, 248),
        }
        n = min(len(steps), 4)
        gap = 4
        w = (178 - gap * (n - 1)) / n
        step_h = 42
        for i, st in enumerate(steps[:n]):
            x = 16 + i * (w + gap)
            tone = str(st.get("tone") or "pay")
            pdf.set_fill_color(*fills.get(tone, fills["pay"]))
            pdf.set_draw_color(*_LINE)
            pdf.rect(x, y, w, step_h, "FD")
            # arrow connector
            if i < n - 1:
                pdf.set_fill_color(*_GOLD)
                ax = x + w + 0.8
                pdf.rect(ax, y + step_h / 2 - 0.6, gap - 1.6, 1.2, "F")
            pdf.set_xy(x + 2, y + 3)
            pdf.set_font("TT", "", 7)
            pdf.set_text_color(*_MUTED)
            pdf.cell(w - 4, 3.5, str(st.get("phase") or ""))
            pdf.set_xy(x + 2, y + 8)
            pdf.set_font("TT", "B", 9)
            pdf.set_text_color(*_INK)
            pdf.cell(w - 4, 4.5, str(st.get("title") or ""))
            pdf.set_xy(x + 2, y + 14)
            pdf.set_font("TT", "", 7.5)
            pdf.set_text_color(*_TEXT)
            pdf.multi_cell(w - 4, 3.5, str(st.get("body") or ""))
        y = y + step_h + 6

    # Focus-year value table
    vtable = list(visual.get("value_table") or [])
    if vtable:
        if y > 230:
            pdf.add_page()
            pdf.set_fill_color(*_SOFT)
            pdf.rect(0, 0, 210, 297, "F")
            y = 40
        pdf.set_xy(16, y)
        pdf.set_font("TT", "B", 10)
        pdf.set_text_color(*_INK)
        pdf.cell(0, 6, str(visual.get("value_table_caption") or "重點年份戶口（示意）"), ln=1)
        y = pdf.get_y() + 1
        cols = [22, 22, 40, 50, 44]
        headers = ["年度", "年齡", "提款", "期末戶口", "備註"]
        x0 = 16
        pdf.set_fill_color(26, 43, 76)
        pdf.rect(x0, y, 178, 8, "F")
        pdf.set_text_color(*_WHITE)
        pdf.set_font("TT", "B", 8)
        x = x0
        for h, cw in zip(headers, cols):
            pdf.set_xy(x + 1, y + 1.5)
            pdf.cell(cw - 2, 5, h)
            x += cw
        y += 8
        pdf.set_font("TT", "", 8)
        for i, r in enumerate(vtable):
            if y > 275:
                pdf.add_page()
                pdf.set_fill_color(*_SOFT)
                pdf.rect(0, 0, 210, 297, "F")
                y = 40
            bg = (255, 255, 255) if i % 2 == 0 else (238, 242, 247)
            pdf.set_fill_color(*bg)
            pdf.rect(x0, y, 178, 8, "F")
            wd = float(r.get("withdraw_usd") or 0)
            vals = [
                f"第 {r.get('policy_year')} 年",
                f"{r.get('age')} 歲",
                format_usd(wd) if wd else "—",
                format_usd(float(r.get("av_end_usd") or 0)),
                str(r.get("note") or ""),
            ]
            pdf.set_text_color(*_TEXT)
            x = x0
            for v, cw in zip(vals, cols):
                pdf.set_xy(x + 1, y + 1.5)
                pdf.cell(cw - 2, 5, v)
                x += cw
            y += 8
        y += 4
    return y


def _summary_kv_height(pdf, value: str, *, value_w: float, line_h: float) -> float:
    pdf.set_font("TT", "", 10)
    return float(pdf.multi_cell(value_w, line_h, value, dry_run=True, output="HEIGHT") or line_h)


def _draw_summary_kv(
    pdf, x: float, y: float, label: str, value: str, *, label_w: float, value_w: float, line_h: float
) -> float:
    """Draw a label/value row; return height used."""
    pdf.set_xy(x, y)
    pdf.set_font("TT", "", 9)
    pdf.set_text_color(*_MUTED)
    pdf.cell(label_w, line_h, label)
    pdf.set_xy(x + label_w, y)
    pdf.set_font("TT", "", 10)
    pdf.set_text_color(*_TEXT)
    pdf.multi_cell(value_w, line_h, value)
    return max(line_h, float(pdf.get_y() - y))


def _summary_page(pdf, proposal: dict[str, Any]) -> None:
    pdf.add_page()
    pdf.set_fill_color(*_SOFT)
    pdf.rect(0, 0, 210, 297, "F")
    pdf.set_fill_color(*_INK)
    pdf.rect(0, 0, 210, 28, "F")
    pdf.set_text_color(*_GOLD)
    pdf.set_font("TT", "B", 12)
    pdf.set_xy(16, 9)
    pdf.cell(0, 8, "SUMMARY")

    # Card rows with fixed label column — avoids old table cell jump.
    y = 40.0
    line_h = 5.2
    pad = 5.0
    label_w = 28.0
    value_w = 140.0
    for i, row in enumerate(proposal.get("summary_rows") or []):
        category = str(row.get("保險類別") or "")
        product = str(row.get("產品名稱") or "")
        premium = str(row.get("年供保費") or "")
        cover = str(row.get("保障摘要") or "")
        # Keep term short on Summary so cards stay tidy
        term_raw = str(row.get("供款／年期") or "").strip()
        term = term_raw.split("；")[0].strip() if term_raw else ""

        pdf.set_font("TT", "B", 11)
        title_h = float(
            pdf.multi_cell(170, 6, f"{category}  ·  {product}", dry_run=True, output="HEIGHT")
            or 6
        )
        prem_h = _summary_kv_height(pdf, premium, value_w=value_w, line_h=line_h)
        cover_h = _summary_kv_height(pdf, cover, value_w=value_w, line_h=line_h)
        term_h = _summary_kv_height(pdf, term, value_w=value_w, line_h=line_h) if term else 0.0
        card_h = pad + title_h + 3 + prem_h + 1.5 + cover_h + (1.5 + term_h if term else 0) + pad

        if y + card_h > 255:
            pdf.add_page()
            pdf.set_fill_color(*_SOFT)
            pdf.rect(0, 0, 210, 297, "F")
            pdf.set_fill_color(*_INK)
            pdf.rect(0, 0, 210, 28, "F")
            pdf.set_text_color(*_GOLD)
            pdf.set_font("TT", "B", 12)
            pdf.set_xy(16, 9)
            pdf.cell(0, 8, "SUMMARY")
            y = 40.0

        bg = _WHITE if i % 2 == 0 else (242, 239, 232)
        pdf.set_fill_color(*bg)
        pdf.set_draw_color(*_LINE)
        pdf.rect(16, y, 178, card_h, "FD")

        cy = y + pad
        pdf.set_xy(20, cy)
        pdf.set_font("TT", "B", 11)
        pdf.set_text_color(*_INK)
        pdf.multi_cell(170, 6, f"{category}  ·  {product}")
        cy = pdf.get_y() + 3

        cy += _draw_summary_kv(
            pdf, 20, cy, "年供保費", premium, label_w=label_w, value_w=value_w, line_h=line_h
        )
        cy += 1.5
        cy += _draw_summary_kv(
            pdf, 20, cy, "保障摘要", cover, label_w=label_w, value_w=value_w, line_h=line_h
        )
        if term:
            cy += 1.5
            _draw_summary_kv(
                pdf, 20, cy, "年期", term, label_w=label_w, value_w=value_w, line_h=line_h
            )

        y += card_h + 6

    total = float(proposal.get("total_annual_hkd") or 0)
    if y > 250:
        pdf.add_page()
        pdf.set_fill_color(*_SOFT)
        pdf.rect(0, 0, 210, 297, "F")
        y = 40.0
    pdf.set_xy(16, y + 4)
    pdf.set_font("TT", "B", 14)
    pdf.set_text_color(*_INK)
    pdf.cell(0, 8, f"合計年供約 {format_hkd(total)}", ln=1)

    gaps = proposal.get("gaps") or []
    if gaps:
        pdf.ln(4)
        pdf.set_font("TT", "B", 10)
        pdf.set_text_color(*_WARN)
        pdf.cell(0, 6, "待補資料", ln=1)
        pdf.set_font("TT", "", 9)
        for g in gaps:
            pdf.set_x(16)
            pdf.multi_cell(178, 5, f"•  {g}")

    pdf.set_y(270)
    pdf.set_font("TT", "", 8)
    pdf.set_text_color(*_MUTED)
    pdf.set_x(16)
    pdf.multi_cell(
        178,
        4,
        "本文件由 TIM TEAM M+2 產生，只供內部見客參考。"
        "保障、保費、折扣、分紅及特別紅利均以保險公司正式計劃書及條款為準；非保證利益並非承諾。",
    )
