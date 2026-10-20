"""One-click client-facing PDF reports for 客戶工具 (alongside WhatsApp)."""

from __future__ import annotations

import hashlib
import os
import re
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen

# Prefer system CJK with Latin coverage (headers need "TIM TEAM" + digits).
# DroidSansFallback often lacks ASCII; WenQuanYi / Noto are safer for mixed text.
_FONT_CANDIDATES = [
    os.environ.get("TIM_TEAM_CJK_FONT") or "",
    str(Path(__file__).resolve().parents[1] / "static" / "fonts" / "NotoSansCJKtc-Regular.otf"),
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    # Last resort: Chinese-only fallback (Latin glyphs may be missing)
    str(Path(__file__).resolve().parents[1] / "static" / "fonts" / "DroidSansFallbackFull.ttf"),
    "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
]

_FALLBACK_FONT_URL = (
    "https://github.com/StellarCN/scp_zh/raw/master/fonts/SimHei.ttf"
)

# Brand palette (align with tt_core/styles.py)
_INK = (28, 36, 48)
_GOLD = (197, 160, 40)
_GOLD_DEEP = (154, 123, 26)
_GOLD_SOFT = (247, 241, 222)
_CREAM = (250, 248, 243)
_MUTED = (107, 114, 128)
_LINE = (230, 226, 216)

_MD_BOLD = re.compile(r"\*(.+?)\*")
_MD_EMPH = re.compile(r"_(.+?)_")
_EMOJIish = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U00002700-\U000027BF"
    "\U0001F1E0-\U0001F1FF"
    "\U00002600-\U000026FF"  # misc symbols (⚠ etc.)
    "\uFE0E\uFE0F"  # variation selectors left after emoji strip
    "\u200D"  # ZWJ
    "]+",
    flags=re.UNICODE,
)
_SECTION_ONLY = re.compile(r"^\*[^*]+\*$")
_BULLET_START = re.compile(r"^[\u2022\u00b7\-\u2013\u2014]\s*")
_KV_SPLIT = re.compile(r"[：:]")
# Hero KPIs only — avoid boxing every total
_HERO_RE = re.compile(
    r"(保障缺口|每月\s*Cashflow\s*[：:]|^最少年供)",
)
_STRONG_KEYS = (
    "總收入",
    "總支出",
    "已有保障總額",
    "現有每月保費",
    "期間最高",
    "提款年度合計",
)


def _cache_font_dir() -> Path:
    base = Path(os.environ.get("TIM_TEAM_FONT_CACHE") or (Path.home() / ".cache" / "tim-team"))
    base.mkdir(parents=True, exist_ok=True)
    return base


def resolve_cjk_font() -> str:
    """Return a filesystem path to a CJK-capable TrueType/OpenType font."""
    for path in _FONT_CANDIDATES:
        if path and Path(path).is_file():
            return path
    cached = _cache_font_dir() / "SimHei.ttf"
    if cached.is_file() and cached.stat().st_size > 100_000:
        return str(cached)
    try:
        req = Request(_FALLBACK_FONT_URL, headers={"User-Agent": "TIM-TEAM-PDF/1.0"})
        with urlopen(req, timeout=30) as resp:
            data = resp.read()
        if len(data) > 100_000:
            cached.write_bytes(data)
            return str(cached)
    except Exception:
        pass
    raise RuntimeError(
        "搵唔到中文字體。請喺環境安裝 fonts-wqy-microhei，"
        "或設定 TIM_TEAM_CJK_FONT 指向 .ttf/.otf。"
    )


def strip_whatsapp_markup(text: str) -> str:
    """Turn WhatsApp markdown (*bold*, _italic_, emoji) into plain report text."""
    t = str(text or "")
    t = _MD_BOLD.sub(r"\1", t)
    t = _MD_EMPH.sub(r"\1", t)
    t = _EMOJIish.sub("", t)
    t = re.sub(r"[ \t]+\n", "\n", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def _plain_line(text: str) -> str:
    t = _MD_BOLD.sub(r"\1", str(text or ""))
    t = _MD_EMPH.sub(r"\1", t)
    t = _EMOJIish.sub("", t)
    return t.strip()


def _is_hero(plain: str) -> bool:
    return bool(_HERO_RE.search(plain))


def _is_strong(plain: str) -> bool:
    return any(k in plain for k in _STRONG_KEYS)


def _is_summary_title(plain: str) -> bool:
    """WhatsApp first-line titles like「保障分析摘要 — 陳生」— redundant with PDF title."""
    if "摘要" in plain and len(plain) <= 28:
        return True
    if plain.endswith("試算") and len(plain) <= 24:
        return True
    if "Package 對比" in plain and len(plain) <= 28:
        return True
    return False


def parse_report_blocks(body: str) -> list[tuple[str, str]]:
    """Classify WhatsApp-style lines into typed blocks for layout."""
    blocks: list[tuple[str, str]] = []
    raw = str(body or "").replace("\r\n", "\n").replace("\r", "\n")
    for raw_line in raw.split("\n"):
        stripped = raw_line.strip()
        if not stripped:
            if blocks and blocks[-1][0] != "blank":
                blocks.append(("blank", ""))
            continue

        # Whole-line bold → section heading (e.g. *收入*)
        if _SECTION_ONLY.match(stripped):
            blocks.append(("section", _plain_line(stripped)))
            continue

        # Leading italic disclaimer
        if stripped.startswith("_") and stripped.endswith("_") and stripped.count("_") == 2:
            blocks.append(("note", _plain_line(stripped)))
            continue

        bullet_m = _BULLET_START.match(stripped)
        if bullet_m:
            rest = stripped[bullet_m.end() :]
            blocks.append(("bullet", _plain_line(rest)))
            continue

        # Indented detail under a bullet
        if raw_line.startswith("  ") or raw_line.startswith("\t"):
            blocks.append(("detail", _plain_line(stripped)))
            continue

        plain = _plain_line(stripped)
        if not plain:
            continue

        # Drop WA opener titles — PDF already has a proper title
        if _is_summary_title(plain):
            continue

        if _is_hero(plain):
            blocks.append(("hero", plain))
            continue

        if _is_strong(plain):
            blocks.append(("strong", plain))
            continue

        if re.match(r"^四大保障達標", plain) or re.match(r"^達標\s*[：:]", plain):
            blocks.append(("score", plain))
            continue

        if "：" in plain or (":" in plain and not plain.startswith("http")):
            blocks.append(("kv", plain))
            continue

        # Short label without colon → section
        if len(plain) <= 16 and not any(ch in plain for ch in "。！？$"):
            blocks.append(("section", plain))
            continue

        blocks.append(("body", plain))

    # Drop leading/trailing blanks
    while blocks and blocks[0][0] == "blank":
        blocks.pop(0)
    while blocks and blocks[-1][0] == "blank":
        blocks.pop()
    return blocks


def build_client_pdf(
    *,
    title: str,
    body: str,
    client: str = "",
    tool_name: str = "",
    agent: str = "",
    footer: str = "",
) -> bytes:
    """Render a branded multi-page client PDF (Traditional Chinese OK)."""
    from fpdf import FPDF

    font_path = resolve_cjk_font()
    blocks = parse_report_blocks(body)
    if not blocks:
        blocks = [("body", "（未有內容）")]

    disclaimer = footer or "本報告只供參考，並非正式報價／核保決定；詳情以保險公司條款為準。"
    band_h = 18.0

    class _Report(FPDF):
        def header(self) -> None:
            # Soft cream wash for the whole page (drawn first)
            self.set_fill_color(*_CREAM)
            self.rect(0, 0, self.w, self.h, style="F")
            # Full-bleed ink brand band
            self.set_fill_color(*_INK)
            self.rect(0, 0, self.w, band_h, style="F")
            # Gold accent hairline under band
            self.set_fill_color(*_GOLD)
            self.rect(0, band_h, self.w, 0.7, style="F")

            self.set_xy(self.l_margin, 5.5)
            self.set_font("ttcjk", size=11)
            self.set_text_color(*_GOLD)
            self.cell(self.epw * 0.55, 7, "TIM TEAM", align="L")
            self.set_font("ttcjk", size=9)
            self.set_text_color(220, 210, 180)
            self.cell(self.epw * 0.45, 7, "客戶報告", align="R")
            self.set_y(band_h + 8)

        def footer(self) -> None:
            self.set_y(-20)
            self.set_draw_color(*_LINE)
            self.set_line_width(0.25)
            self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
            self.ln(2.5)
            self.set_x(self.l_margin)
            self.set_font("ttcjk", size=7.5)
            self.set_text_color(*_MUTED)
            self.multi_cell(self.epw, 3.6, disclaimer, align="C")
            self.set_y(-8)
            self.set_x(self.l_margin)
            self.set_text_color(*_GOLD_DEEP)
            self.cell(self.epw, 4, f"{self.page_no()}", align="C")

    pdf = _Report(format="A4")
    pdf.set_margins(18, band_h + 10, 18)
    pdf.set_auto_page_break(auto=True, margin=24)
    pdf.add_font("ttcjk", fname=font_path)
    pdf.add_page()

    # Title
    pdf.set_x(pdf.l_margin)
    pdf.set_text_color(*_INK)
    pdf.set_font("ttcjk", size=20)
    pdf.multi_cell(pdf.epw, 9, str(title or "客戶報告").strip())
    # Hairline + short gold accent under title
    ty = pdf.get_y() + 2
    pdf.set_draw_color(*_LINE)
    pdf.set_line_width(0.25)
    pdf.line(pdf.l_margin, ty, pdf.w - pdf.r_margin, ty)
    pdf.set_fill_color(*_GOLD)
    pdf.rect(pdf.l_margin, ty - 0.35, 28, 1.2, style="F")
    pdf.set_y(ty + 5)

    # Meta cards row
    _draw_meta_row(
        pdf,
        client=client,
        tool_name=tool_name,
        agent=agent,
        when=datetime.now().strftime("%Y-%m-%d %H:%M"),
    )
    pdf.ln(1.5)

    # Pull hero KPIs up into a compact strip (then skip them inline)
    heroes = [(k, t) for k, t in blocks if k == "hero"]
    hero_texts = {t for _, t in heroes}
    if heroes:
        _draw_hero_strip(pdf, [t for _, t in heroes[:3]])
        pdf.ln(1.5)

    # Coalesce bullet+detail pairs into table rows when clustered
    render_blocks = _coalesce_for_layout(blocks)

    for item in render_blocks:
        kind = item[0]
        if kind == "hero" and item[1] in hero_texts:
            continue
        if kind == "blank":
            pdf.ln(1.8)
            continue
        if kind == "section":
            _draw_section(pdf, item[1])
            continue
        if kind == "strong":
            _draw_strong(pdf, item[1])
            continue
        if kind == "table":
            _draw_pair_table(pdf, item[1])
            continue
        if kind == "bullet":
            _draw_bullet(pdf, item[1])
            continue
        if kind == "detail":
            _draw_detail(pdf, item[1])
            continue
        if kind == "note":
            _draw_note(pdf, item[1])
            continue
        if kind == "kv":
            _draw_kv(pdf, item[1])
            continue
        if kind == "score":
            _draw_score(pdf, item[1])
            continue
        _draw_body(pdf, item[1])

    out = pdf.output()
    if isinstance(out, (bytes, bytearray)):
        return bytes(out)
    return str(out).encode("latin-1")


def _coalesce_for_layout(blocks: list[tuple]) -> list[tuple]:
    """Group consecutive bullet+detail pairs into one table block."""
    out: list[tuple] = []
    i = 0
    n = len(blocks)
    while i < n:
        kind = blocks[i][0]
        if kind == "bullet":
            pairs: list[tuple[str, str]] = []
            j = i
            while j < n:
                if blocks[j][0] == "blank":
                    # allow blank inside cluster only if next is still bullet
                    if j + 1 < n and blocks[j + 1][0] == "bullet":
                        j += 1
                        continue
                    break
                if blocks[j][0] != "bullet":
                    break
                title = blocks[j][1]
                detail = ""
                if j + 1 < n and blocks[j + 1][0] == "detail":
                    detail = blocks[j + 1][1]
                    j += 2
                else:
                    j += 1
                pairs.append((title, detail))
            # Only use comparison table when details look like 已有／建議 rows
            detailed = sum(1 for _, d in pairs if d and ("已有" in d or "建議" in d or "$" in d))
            if len(pairs) >= 2 and detailed >= max(2, len(pairs) // 2):
                out.append(("table", pairs))
                i = j
                continue
            # Otherwise keep as normal bullets (核保結果、問答等)
            for title, detail in pairs:
                out.append(("bullet", title))
                if detail:
                    out.append(("detail", detail))
            i = j
            continue
        out.append(blocks[i])
        i += 1
    return out


def _draw_meta_row(
    pdf,
    *,
    client: str,
    tool_name: str,
    agent: str,
    when: str,
) -> None:
    items: list[tuple[str, str]] = []
    if client:
        items.append(("客戶", client))
    if tool_name:
        items.append(("工具", tool_name))
    if agent:
        items.append(("顧問", agent))
    items.append(("日期", when))

    # Soft panel behind meta
    y0 = pdf.get_y()
    row_h = 14
    pdf.set_fill_color(*_GOLD_SOFT)
    pdf.set_draw_color(*_LINE)
    pdf.set_line_width(0.2)
    pdf.rect(pdf.l_margin, y0, pdf.epw, row_h, style="FD")

    n = max(len(items), 1)
    col_w = pdf.epw / n
    x = pdf.l_margin
    for label, value in items:
        pdf.set_xy(x + 2.5, y0 + 2)
        pdf.set_font("ttcjk", size=7)
        pdf.set_text_color(*_GOLD_DEEP)
        pdf.cell(col_w - 4, 4, label, align="L")
        pdf.set_xy(x + 2.5, y0 + 6.5)
        pdf.set_font("ttcjk", size=9.5)
        pdf.set_text_color(*_INK)
        # Truncate long values to fit column
        shown = value
        while pdf.get_string_width(shown) > col_w - 5 and len(shown) > 3:
            shown = shown[:-2] + "…"
        pdf.cell(col_w - 4, 5, shown, align="L")
        x += col_w
    pdf.set_y(y0 + row_h + 2)


def _draw_section(pdf, text: str) -> None:
    pdf.ln(1.5)
    y = pdf.get_y()
    # Gold left rail + soft fill
    pdf.set_fill_color(*_GOLD_SOFT)
    pdf.rect(pdf.l_margin, y, pdf.epw, 8.5, style="F")
    pdf.set_fill_color(*_GOLD)
    pdf.rect(pdf.l_margin, y, 1.4, 8.5, style="F")
    pdf.set_xy(pdf.l_margin + 4, y + 1.5)
    pdf.set_font("ttcjk", size=11)
    pdf.set_text_color(*_INK)
    pdf.cell(pdf.epw - 6, 5.5, text, align="L")
    pdf.set_y(y + 10)


def _split_label_value(text: str) -> tuple[str, str]:
    parts = _KV_SPLIT.split(text, maxsplit=1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return text.strip(), ""


def _draw_hero_strip(pdf, items: list[str]) -> None:
    """One ink band with 1–3 hero KPIs (label above, value below)."""
    if not items:
        return
    n = len(items)
    y = pdf.get_y()
    h = 18
    pdf.set_fill_color(*_INK)
    pdf.rect(pdf.l_margin, y, pdf.epw, h, style="F")
    # Gold top hairline
    pdf.set_fill_color(*_GOLD)
    pdf.rect(pdf.l_margin, y, pdf.epw, 0.6, style="F")

    col_w = pdf.epw / n
    for i, text in enumerate(items):
        label, value = _split_label_value(text)
        if not value:
            label, value = "重點", label
        x = pdf.l_margin + i * col_w
        pdf.set_xy(x + 3, y + 3)
        pdf.set_font("ttcjk", size=7.5)
        pdf.set_text_color(*_GOLD)
        pdf.cell(col_w - 6, 4, label, align="L")
        pdf.set_xy(x + 3, y + 8.5)
        pdf.set_font("ttcjk", size=12)
        pdf.set_text_color(250, 248, 243)
        shown = value
        while pdf.get_string_width(shown) > col_w - 7 and len(shown) > 4:
            shown = shown[:-2] + "…"
        pdf.cell(col_w - 6, 6, shown, align="L")
        # Divider between columns
        if i < n - 1:
            pdf.set_draw_color(60, 70, 85)
            pdf.set_line_width(0.2)
            dx = x + col_w
            pdf.line(dx, y + 3.5, dx, y + h - 3.5)
    pdf.set_y(y + h + 3)


def _draw_strong(pdf, text: str) -> None:
    """Secondary totals — clean row, gold value, no heavy box."""
    label, value = _split_label_value(text)
    y = pdf.get_y()
    pdf.set_draw_color(*_LINE)
    pdf.set_line_width(0.2)
    pdf.line(pdf.l_margin, y, pdf.w - pdf.r_margin, y)
    pdf.set_xy(pdf.l_margin, y + 1.5)
    pdf.set_font("ttcjk", size=10)
    pdf.set_text_color(*_MUTED)
    if value:
        pdf.cell(pdf.epw * 0.45, 6, label, align="L")
        pdf.set_font("ttcjk", size=11)
        pdf.set_text_color(*_GOLD_DEEP)
        pdf.cell(pdf.epw * 0.55, 6, value, align="R")
        pdf.set_y(y + 8.5)
    else:
        pdf.set_text_color(*_INK)
        pdf.multi_cell(pdf.epw, 6, text)
        pdf.ln(0.5)


def _draw_bullet(pdf, text: str) -> None:
    pdf.set_x(pdf.l_margin)
    y = pdf.get_y()
    # Gold disc
    pdf.set_fill_color(*_GOLD)
    pdf.ellipse(pdf.l_margin + 1.2, y + 2.2, 2.0, 2.0, style="F")
    pdf.set_xy(pdf.l_margin + 6, y)
    pdf.set_font("ttcjk", size=10.5)
    pdf.set_text_color(*_INK)
    pdf.multi_cell(pdf.epw - 6, 5.8, text)
    pdf.ln(0.6)


def _draw_detail(pdf, text: str) -> None:
    pdf.set_x(pdf.l_margin + 6)
    pdf.set_font("ttcjk", size=9.5)
    pdf.set_text_color(*_MUTED)
    pdf.multi_cell(pdf.epw - 6, 5.2, text)
    pdf.ln(0.4)


def _draw_kv(pdf, text: str) -> None:
    parts = _KV_SPLIT.split(text, maxsplit=1)
    pdf.set_x(pdf.l_margin)
    if len(parts) == 2:
        label, value = parts[0].strip(), parts[1].strip()
        y = pdf.get_y()
        # Soft row for key facts (疾病 / 對應情況 etc.)
        pdf.set_fill_color(255, 255, 255)
        pdf.set_draw_color(*_LINE)
        pdf.set_line_width(0.2)
        pdf.rect(pdf.l_margin, y, pdf.epw, 9, style="FD")
        pdf.set_xy(pdf.l_margin + 3, y + 2)
        pdf.set_font("ttcjk", size=8)
        pdf.set_text_color(*_GOLD_DEEP)
        pdf.cell(28, 5, label, align="L")
        pdf.set_font("ttcjk", size=10.5)
        pdf.set_text_color(*_INK)
        pdf.cell(pdf.epw - 34, 5, value, align="L")
        pdf.set_y(y + 10.5)
    else:
        _draw_body(pdf, text)


def _draw_score(pdf, text: str) -> None:
    label, value = _split_label_value(text)
    if not value:
        label, value = "達標", text
    y = pdf.get_y()
    pdf.set_fill_color(*_INK)
    # Pill-like score chip
    chip_w = min(72, pdf.epw)
    pdf.rect(pdf.l_margin, y, chip_w, 9, style="F")
    pdf.set_xy(pdf.l_margin + 3, y + 2)
    pdf.set_font("ttcjk", size=9)
    pdf.set_text_color(*_GOLD)
    pdf.cell(chip_w * 0.55, 5, label, align="L")
    pdf.set_text_color(250, 248, 243)
    pdf.set_font("ttcjk", size=11)
    pdf.cell(chip_w * 0.45 - 3, 5, value, align="R")
    pdf.set_y(y + 11)


def _draw_pair_table(pdf, pairs: list[tuple[str, str]]) -> None:
    """Clean comparison table: 項目／狀態 | 明細."""
    pdf.ln(0.5)
    y = pdf.get_y()
    # Header
    pdf.set_fill_color(*_GOLD_SOFT)
    pdf.rect(pdf.l_margin, y, pdf.epw, 7, style="F")
    pdf.set_xy(pdf.l_margin + 3, y + 1.5)
    pdf.set_font("ttcjk", size=8)
    pdf.set_text_color(*_GOLD_DEEP)
    pdf.cell(pdf.epw * 0.42, 4, "項目／狀態", align="L")
    pdf.cell(pdf.epw * 0.58 - 3, 4, "已有／建議", align="L")
    y += 7
    row_h = 11
    for i, (title, detail) in enumerate(pairs):
        bg = (255, 255, 255) if i % 2 == 0 else (252, 250, 245)
        pdf.set_fill_color(*bg)
        pdf.rect(pdf.l_margin, y, pdf.epw, row_h, style="F")
        # bottom hairline
        pdf.set_draw_color(*_LINE)
        pdf.set_line_width(0.15)
        pdf.line(pdf.l_margin, y + row_h, pdf.w - pdf.r_margin, y + row_h)
        # gold tick
        pdf.set_fill_color(*_GOLD)
        pdf.rect(pdf.l_margin, y + 3, 1.2, row_h - 6, style="F")
        pdf.set_xy(pdf.l_margin + 4, y + 3)
        pdf.set_font("ttcjk", size=10)
        pdf.set_text_color(*_INK)
        shown = title
        while pdf.get_string_width(shown) > pdf.epw * 0.4 and len(shown) > 4:
            shown = shown[:-2] + "…"
        pdf.cell(pdf.epw * 0.42 - 2, 5, shown, align="L")
        pdf.set_font("ttcjk", size=9)
        pdf.set_text_color(*_MUTED)
        det = detail or "—"
        while pdf.get_string_width(det) > pdf.epw * 0.52 and len(det) > 4:
            det = det[:-2] + "…"
        pdf.cell(pdf.epw * 0.58 - 4, 5, det, align="L")
        y += row_h
    pdf.set_y(y + 2)


def _draw_body(pdf, text: str) -> None:
    pdf.set_x(pdf.l_margin)
    pdf.set_font("ttcjk", size=10.5)
    pdf.set_text_color(*_INK)
    pdf.multi_cell(pdf.epw, 5.8, text)
    pdf.ln(0.5)


def _draw_note(pdf, text: str) -> None:
    pdf.ln(1)
    pdf.set_x(pdf.l_margin)
    pdf.set_font("ttcjk", size=8.5)
    pdf.set_text_color(*_MUTED)
    pdf.multi_cell(pdf.epw, 4.5, text)
    pdf.ln(0.5)


def _wrap(pdf, text: str, width: float) -> list[str]:
    """Simple width wrap using fpdf string width (CJK-safe char by char)."""
    if not text:
        return [""]
    if pdf.get_string_width(text) <= width:
        return [text]
    lines: list[str] = []
    cur = ""
    for ch in text:
        trial = cur + ch
        if pdf.get_string_width(trial) <= width:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = ch
    if cur:
        lines.append(cur)
    return lines or [text]


def pdf_filename(*, title: str = "", client: str = "", tool: str = "") -> str:
    """Safe download filename."""
    stamp = datetime.now().strftime("%Y%m%d")
    base = (client or tool or title or "client-report").strip()
    base = re.sub(r"[\\/:*?\"<>|]+", "", base)
    base = re.sub(r"\s+", "", base)[:24] or "report"
    return f"TIM-{base}-{stamp}.pdf"


def report_sha(data: bytes) -> str:
    return hashlib.sha256(data or b"").hexdigest()[:12]
