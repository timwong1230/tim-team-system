"""One-click client-facing PDF reports — card layout matching TIM TEAM coverage UI."""

from __future__ import annotations

import hashlib
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

# Prefer system CJK with Latin coverage (headers need "TIM TEAM" + digits).
_FONT_CANDIDATES = [
    os.environ.get("TIM_TEAM_CJK_FONT") or "",
    str(Path(__file__).resolve().parents[1] / "static" / "fonts" / "NotoSansCJKtc-Regular.otf"),
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    str(Path(__file__).resolve().parents[1] / "static" / "fonts" / "DroidSansFallbackFull.ttf"),
    "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
]

_FALLBACK_FONT_URL = (
    "https://github.com/StellarCN/scp_zh/raw/master/fonts/SimHei.ttf"
)

# Reference palette (coverage summary cards)
_INK = (26, 43, 76)  # #1A2B4C
_TEXT = (33, 37, 41)
_MUTED = (108, 117, 125)
_LINE = (222, 226, 230)
_SOFT = (248, 249, 250)
_WHITE = (255, 255, 255)
_GOLD = (197, 160, 40)
_WARN = (211, 84, 78)  # #D3544E
_WARN_SOFT = (255, 245, 245)  # #FFF5F5
_OK = (72, 140, 100)  # medical green
_CI = (192, 72, 72)  # critical illness red
_ACC = (217, 126, 56)  # accident orange
_LIFE = (192, 72, 72)
_DISCLAIMER_BG = (255, 249, 196)

_PILLAR_THEME = {
    "人壽": (_LIFE, "♥"),
    "人壽保險": (_LIFE, "♥"),
    "危疾": (_CI, "+"),
    "危疾保險": (_CI, "+"),
    "醫療": (_OK, "+"),
    "醫療保險": (_OK, "+"),
    "意外": (_ACC, "!"),
    "意外保險": (_ACC, "!"),
}

_MD_BOLD = re.compile(r"\*(.+?)\*")
_MD_EMPH = re.compile(r"_(.+?)_")
_EMOJIish = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U00002700-\U000027BF"
    "\U0001F1E0-\U0001F1FF"
    "\U00002600-\U000026FF"
    "\uFE0E\uFE0F"
    "\u200D"
    "]+",
    flags=re.UNICODE,
)
_SECTION_ONLY = re.compile(r"^\*[^*]+\*$")
_BULLET_START = re.compile(r"^[\u2022\u00b7\-\u2013\u2014]\s*")
_KV_SPLIT = re.compile(r"[：:]")
_HERO_RE = re.compile(r"(保障缺口|每月\s*Cashflow\s*[：:]|^最少年供)")
_STRONG_KEYS = ("總收入", "總支出", "已有保障總額", "現有每月保費", "期間最高", "提款年度合計")


def _cache_font_dir() -> Path:
    base = Path(os.environ.get("TIM_TEAM_FONT_CACHE") or (Path.home() / ".cache" / "tim-team"))
    base.mkdir(parents=True, exist_ok=True)
    return base


def resolve_cjk_font() -> str:
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


def format_hkd_report(amount: Any) -> str:
    try:
        v = float(amount or 0)
    except Exception:
        return "HK$0.00"
    sign = "-" if v < 0 else ""
    return f"{sign}HK${abs(v):,.2f}"


def pdf_filename(*, title: str = "", client: str = "", tool: str = "") -> str:
    stamp = datetime.now().strftime("%Y%m%d")
    base = (client or tool or title or "client-report").strip()
    base = re.sub(r"[\\/:*?\"<>|]+", "", base)
    base = re.sub(r"\s+", "", base)[:24] or "report"
    return f"TIM-{base}-{stamp}.pdf"


def report_sha(data: bytes) -> str:
    return hashlib.sha256(data or b"").hexdigest()[:12]


# ─── block parsing (generic WA → structured) ─────────────────────────────────


def _is_summary_title(plain: str) -> bool:
    if "摘要" in plain and len(plain) <= 28:
        return True
    if plain.endswith("試算") and len(plain) <= 24:
        return True
    if "Package 對比" in plain and len(plain) <= 28:
        return True
    return False


def parse_report_blocks(body: str) -> list[tuple[str, str]]:
    blocks: list[tuple[str, str]] = []
    raw = str(body or "").replace("\r\n", "\n").replace("\r", "\n")
    for raw_line in raw.split("\n"):
        stripped = raw_line.strip()
        if not stripped:
            if blocks and blocks[-1][0] != "blank":
                blocks.append(("blank", ""))
            continue
        if _SECTION_ONLY.match(stripped):
            blocks.append(("section", _plain_line(stripped)))
            continue
        if stripped.startswith("_") and stripped.endswith("_") and stripped.count("_") == 2:
            blocks.append(("note", _plain_line(stripped)))
            continue
        bullet_m = _BULLET_START.match(stripped)
        if bullet_m:
            blocks.append(("bullet", _plain_line(stripped[bullet_m.end() :])))
            continue
        if raw_line.startswith("  ") or raw_line.startswith("\t"):
            blocks.append(("detail", _plain_line(stripped)))
            continue
        plain = _plain_line(stripped)
        if not plain:
            continue
        if _is_summary_title(plain):
            continue
        if _HERO_RE.search(plain):
            blocks.append(("hero", plain))
            continue
        if any(k in plain for k in _STRONG_KEYS):
            blocks.append(("strong", plain))
            continue
        if "：" in plain or (":" in plain and not plain.startswith("http")):
            blocks.append(("kv", plain))
            continue
        if len(plain) <= 16 and not any(ch in plain for ch in "。！？$"):
            blocks.append(("section", plain))
            continue
        blocks.append(("body", plain))
    while blocks and blocks[0][0] == "blank":
        blocks.pop(0)
    while blocks and blocks[-1][0] == "blank":
        blocks.pop()
    return blocks


# ─── drawing primitives (reference card UI) ───────────────────────────────────


def _rrect(pdf, x, y, w, h, *, fill=None, draw=None, radius=2.5, style="F"):
    if fill is not None:
        pdf.set_fill_color(*fill)
    if draw is not None:
        pdf.set_draw_color(*draw)
        pdf.set_line_width(0.35)
        style = "FD" if fill is not None else "D"
    elif fill is not None:
        style = "F"
    pdf.rect(x, y, w, h, style=style, round_corners=True, corner_radius=radius)


def _section_title(pdf, text: str) -> None:
    pdf.ln(2)
    pdf.set_x(pdf.l_margin)
    pdf.set_font("ttcjk", size=13)
    pdf.set_text_color(*_TEXT)
    pdf.cell(pdf.epw, 7, text, align="L")
    pdf.ln(7.5)
    y = pdf.get_y()
    pdf.set_draw_color(*_TEXT)
    pdf.set_line_width(0.45)
    pdf.line(pdf.l_margin, y, pdf.w - pdf.r_margin, y)
    pdf.ln(4)


def _draw_client_info_box(pdf, rows: list[tuple[str, str]]) -> None:
    """客戶資料 box — white card, navy left rail, label/value rows."""
    if not rows:
        return
    row_h = 7.2
    pad_y = 4
    h = pad_y * 2 + row_h * len(rows)
    y0 = pdf.get_y()
    # outer card
    _rrect(pdf, pdf.l_margin, y0, pdf.epw, h, fill=_WHITE, draw=_LINE, radius=3)
    # navy left accent
    pdf.set_fill_color(*_INK)
    pdf.rect(pdf.l_margin, y0 + 1.5, 1.6, h - 3, style="F")

    y = y0 + pad_y
    for label, value in rows:
        pdf.set_xy(pdf.l_margin + 6, y)
        pdf.set_font("ttcjk", size=9)
        pdf.set_text_color(*_MUTED)
        pdf.cell(42, row_h - 1, f"{label}", align="L")
        pdf.set_font("ttcjk", size=10)
        pdf.set_text_color(*_TEXT)
        pdf.cell(pdf.epw - 52, row_h - 1, str(value), align="R")
        y += row_h
    pdf.set_y(y0 + h + 4)


def _pillar_theme(name: str) -> tuple[tuple[int, int, int], str]:
    key = str(name or "").strip()
    if key in _PILLAR_THEME:
        return _PILLAR_THEME[key]
    for k, v in _PILLAR_THEME.items():
        if k in key:
            return v
    return (_MUTED, "·")


def _ensure_space(pdf, need: float) -> None:
    if pdf.get_y() + need > pdf.page_break_trigger:
        pdf.add_page()


def _draw_coverage_card(
    pdf,
    *,
    title: str,
    status: str,
    have: float,
    need: float,
    premium: float = 0,
    policies: list[dict[str, Any]] | None = None,
) -> None:
    """Color header card (已有) or dashed gap card (缺乏), per reference screenshots."""
    color, icon = _pillar_theme(title)
    display = title if title.endswith("保障") or title.endswith("保險") else f"{title}保障"
    policies = policies or []

    if status == "missing" or (have <= 0 and not policies):
        _draw_gap_card(pdf, title=display, color=color, icon=icon)
        return

    # Covered / short — solid colored header + policy table
    header_h = 12
    table_header_h = 7
    row_h = 8
    n_rows = max(len(policies), 1)
    body_h = table_header_h + row_h * n_rows + 2
    total_h = header_h + body_h
    _ensure_space(pdf, total_h + 4)
    y0 = pdf.get_y()
    x = pdf.l_margin
    w = pdf.epw

    # Header bar (rounded top — draw full card then overlay)
    _rrect(pdf, x, y0, w, total_h, fill=_WHITE, draw=_LINE, radius=3)
    pdf.set_fill_color(*color)
    pdf.rect(x, y0, w, header_h, style="F", round_corners=("TOP_LEFT", "TOP_RIGHT"), corner_radius=3)

    # Header text
    pdf.set_xy(x + 4, y0 + 3)
    pdf.set_font("ttcjk", size=10)
    pdf.set_text_color(*_WHITE)
    left = f"{icon}  {display}"
    pdf.cell(w * 0.42, 6, left, align="L")
    pdf.set_font("ttcjk", size=8)
    right_bits = [f"總保額 {format_hkd_report(have)}"]
    if need > 0:
        right_bits.append(f"建議 {format_hkd_report(need)}")
    if premium > 0:
        right_bits.append(f"月保費 {format_hkd_report(premium)}")
    pdf.cell(w * 0.58 - 6, 6, "   ".join(right_bits), align="R")

    # Table header
    y = y0 + header_h
    pdf.set_fill_color(*_SOFT)
    pdf.rect(x, y, w, table_header_h, style="F")
    cols = [("保單／公司", 0.36), ("類型", 0.16), ("保額", 0.24), ("月保費", 0.24)]
    pdf.set_font("ttcjk", size=7.5)
    pdf.set_text_color(*_MUTED)
    cx = x + 3
    pdf.set_xy(cx, y + 1.5)
    for lab, frac in cols:
        pdf.cell(w * frac - 1, 4, lab, align="L")
    y += table_header_h

    # Rows
    if not policies:
        policies = [
            {
                "保險公司": "（合計）",
                "類型": "主要計劃" if status == "ok" else "保障不足",
                "保額": have,
                "保費": premium,
            }
        ]
    for i, pol in enumerate(policies):
        if i % 2:
            pdf.set_fill_color(252, 252, 253)
            pdf.rect(x, y, w, row_h, style="F")
        name = str(pol.get("保險公司") or pol.get("保單名稱") or "—")
        ptype = str(pol.get("類型") or "主要計劃")
        cover = format_hkd_report(pol.get("保額") or 0)
        prem = format_hkd_report(pol.get("保費") or 0)
        pdf.set_xy(x + 3, y + 1.5)
        pdf.set_font("ttcjk", size=8.5)
        pdf.set_text_color(*_TEXT)
        pdf.cell(w * 0.36 - 1, 5, _fit(pdf, name, w * 0.34), align="L")
        # type pill
        pill_w = min(pdf.get_string_width(ptype) + 4, w * 0.15)
        pdf.set_fill_color(238, 240, 243)
        pdf.rect(x + w * 0.36, y + 1.8, pill_w, 4.5, style="F", round_corners=True, corner_radius=1.2)
        pdf.set_xy(x + w * 0.36 + 1, y + 1.8)
        pdf.set_font("ttcjk", size=7)
        pdf.set_text_color(*_MUTED)
        pdf.cell(pill_w - 2, 4.5, ptype, align="C")
        pdf.set_xy(x + w * 0.52, y + 1.5)
        pdf.set_font("ttcjk", size=8.5)
        pdf.set_text_color(*color)
        pdf.cell(w * 0.24 - 1, 5, cover, align="R")
        pdf.set_text_color(*_TEXT)
        pdf.cell(w * 0.24 - 4, 5, prem, align="R")
        y += row_h

    # Short warning strip
    if status == "short":
        gap = max(0.0, float(need) - float(have))
        pdf.set_fill_color(255, 247, 237)
        pdf.rect(x, y0 + total_h - 0.1, w, 7, style="F", round_corners=("BOTTOM_LEFT", "BOTTOM_RIGHT"), corner_radius=3)
        pdf.set_xy(x + 4, y0 + total_h)
        # Actually extend card — simpler: draw note below
        pass

    pdf.set_y(y0 + total_h + 1)
    if status == "short":
        gap = max(0.0, float(need) - float(have))
        y = pdf.get_y()
        _rrect(pdf, x, y, w, 8, fill=(255, 247, 237), draw=(253, 186, 116), radius=2)
        pdf.set_xy(x + 4, y + 1.8)
        pdf.set_font("ttcjk", size=8)
        pdf.set_text_color(180, 83, 9)
        pdf.cell(w - 8, 4.5, f"有買但不足 — 建議再加 {format_hkd_report(gap)}", align="L")
        pdf.set_y(y + 10)
    else:
        pdf.ln(2)


def _draw_gap_card(pdf, *, title: str, color=None, icon: str = "!") -> None:
    """Dashed red「缺乏保障」card matching reference."""
    color = color or _WARN
    h = 28
    _ensure_space(pdf, h + 4)
    y0 = pdf.get_y()
    x = pdf.l_margin
    w = pdf.epw
    header_h = 11

    # Pale body
    pdf.set_fill_color(*_WARN_SOFT)
    pdf.rect(x, y0, w, h, style="F", round_corners=True, corner_radius=3)
    # Header
    pdf.set_fill_color(*color)
    pdf.rect(x, y0, w, header_h, style="F", round_corners=("TOP_LEFT", "TOP_RIGHT"), corner_radius=3)

    pdf.set_xy(x + 4, y0 + 2.5)
    pdf.set_font("ttcjk", size=10)
    pdf.set_text_color(*_WHITE)
    pdf.cell(w * 0.55, 6, f"{icon}  {title}", align="L")
    # Badge
    badge = "缺乏保障"
    bw = pdf.get_string_width(badge) + 6
    pdf.set_fill_color(255, 255, 255)
    pdf.set_text_color(*color)
    pdf.rect(x + w - bw - 4, y0 + 2.5, bw, 6, style="F", round_corners=True, corner_radius=1.5)
    pdf.set_xy(x + w - bw - 4, y0 + 2.5)
    pdf.set_font("ttcjk", size=8)
    pdf.cell(bw, 6, badge, align="C")

    # Body message
    pdf.set_xy(x + 4, y0 + header_h + 3)
    pdf.set_font("ttcjk", size=9.5)
    pdf.set_text_color(*color)
    pdf.cell(w - 8, 5, "!  尚未投保此類保障", align="C")
    pdf.set_xy(x + 4, y0 + header_h + 8.5)
    pdf.set_font("ttcjk", size=8)
    pdf.set_text_color(150, 70, 65)
    pdf.cell(w - 8, 4.5, "建議考慮添加以獲得全面保障", align="C")

    # Dashed border on top
    pdf.set_draw_color(*color)
    pdf.set_line_width(0.5)
    pdf.set_dash_pattern(dash=1.2, gap=0.9)
    pdf.rect(x, y0, w, h, style="D", round_corners=True, corner_radius=3)
    pdf.set_dash_pattern(dash=0, gap=0)

    pdf.set_y(y0 + h + 4)


def _fit(pdf, text: str, width: float) -> str:
    t = str(text or "")
    if pdf.get_string_width(t) <= width:
        return t
    while len(t) > 1 and pdf.get_string_width(t + "…") > width:
        t = t[:-1]
    return t + "…" if t else ""


def _draw_disclaimer_bar(pdf, text: str) -> None:
    _ensure_space(pdf, 16)
    y = pdf.get_y() + 2
    lines = _wrap(pdf, f"重要聲明：{text}", pdf.epw - 10, size=7.5)
    h = 5 + len(lines) * 3.8
    pdf.set_fill_color(*_DISCLAIMER_BG)
    pdf.rect(pdf.l_margin, y, pdf.epw, h, style="F", round_corners=True, corner_radius=2)
    pdf.set_font("ttcjk", size=7.5)
    pdf.set_text_color(*_TEXT)
    yy = y + 2.5
    for line in lines:
        pdf.set_xy(pdf.l_margin + 4, yy)
        pdf.cell(pdf.epw - 8, 3.6, line, align="L")
        yy += 3.8
    pdf.set_y(y + h + 2)


def _wrap(pdf, text: str, width: float, *, size: float = 9) -> list[str]:
    pdf.set_font("ttcjk", size=size)
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


def _split_kv(text: str) -> tuple[str, str]:
    parts = _KV_SPLIT.split(text, maxsplit=1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return text.strip(), ""


# ─── PDF document shell ───────────────────────────────────────────────────────


def _make_pdf(*, footer_note: str = ""):
    from fpdf import FPDF

    font_path = resolve_cjk_font()
    note = footer_note or "本報告只供參考，並非正式報價／核保決定；詳情以保險公司條款為準。"

    class _Report(FPDF):
        def header(self) -> None:
            self.set_fill_color(*_WHITE)
            self.rect(0, 0, self.w, self.h, style="F")
            # Slim brand strip
            self.set_fill_color(*_INK)
            self.rect(0, 0, self.w, 12, style="F")
            self.set_xy(self.l_margin, 3)
            self.set_font("ttcjk", size=9)
            self.set_text_color(*_GOLD)
            self.cell(self.epw * 0.5, 6, "TIM TEAM", align="L")
            self.set_text_color(220, 220, 220)
            self.cell(self.epw * 0.5, 6, "客戶報告", align="R")
            self.set_y(16)

        def footer(self) -> None:
            self.set_y(-12)
            self.set_font("ttcjk", size=8)
            self.set_text_color(*_MUTED)
            self.set_x(self.l_margin)
            self.cell(self.epw, 5, f"{self.page_no()}", align="C")

    pdf = _Report(format="A4")
    pdf.set_margins(14, 18, 14)
    pdf.set_auto_page_break(auto=True, margin=16)
    pdf.add_font("ttcjk", fname=font_path)
    pdf.add_page()
    pdf._tt_footer_note = note  # noqa: SLF001
    return pdf, note


def _pdf_bytes(pdf) -> bytes:
    out = pdf.output()
    if isinstance(out, (bytes, bytearray)):
        return bytes(out)
    return str(out).encode("latin-1")


def _draw_title(pdf, title: str) -> None:
    pdf.set_x(pdf.l_margin)
    pdf.set_font("ttcjk", size=18)
    pdf.set_text_color(*_TEXT)
    pdf.multi_cell(pdf.epw, 8, str(title or "客戶報告").strip())
    pdf.ln(1)


# ─── public builders ──────────────────────────────────────────────────────────


def build_protection_gap_pdf(
    *,
    title: str = "保障缺口分析報告",
    client: str = "",
    agent: str = "",
    pillars: list[dict[str, Any]] | None = None,
    policies: list[dict[str, Any]] | None = None,
    summary: dict[str, Any] | None = None,
    total_have: float = 0,
    total_gap: float = 0,
    total_prem: float = 0,
    footer: str = "",
) -> bytes:
    """Card-based coverage report matching the reference UI screenshots."""
    pdf, note = _make_pdf(footer_note=footer)
    pillars = list(pillars or [])
    policies = list(policies or [])
    summary = summary or {}

    _draw_title(pdf, title)

    # 客戶資料
    _section_title(pdf, "客戶資料")
    info_rows = []
    if client:
        info_rows.append(("客戶姓名", client))
    if agent:
        info_rows.append(("顧問", agent))
    info_rows.append(("日期", datetime.now().strftime("%Y-%m-%d %H:%M")))
    ready = summary.get("ready", 0)
    total = summary.get("total", 4)
    info_rows.append(("四大保障達標", f"{ready}/{total}"))
    info_rows.append(("已有保障總額", format_hkd_report(total_have)))
    info_rows.append(("保障缺口總額", format_hkd_report(total_gap)))
    info_rows.append(("現有每月保費", format_hkd_report(total_prem)))
    _draw_client_info_box(pdf, info_rows)

    # Split existing vs lacking (reference section 2 / 3)
    have_list = [p for p in pillars if p.get("status") != "missing"]
    miss_list = [p for p in pillars if p.get("status") == "missing"]

    # Policies by type
    by_type: dict[str, list[dict]] = {}
    for row in policies:
        t = str(row.get("保單類型") or "")
        by_type.setdefault(t, []).append(row)

    if have_list:
        _section_title(pdf, f"已有保障（{len(have_list)}項）")
        for p in have_list:
            ptype = str(p.get("保單類型") or "")
            short = str(p.get("短名") or ptype.replace("保險", ""))
            pols = by_type.get(ptype) or []
            # normalize policy dicts for table
            norm = []
            for r in pols:
                norm.append(
                    {
                        "保險公司": r.get("保險公司") or "—",
                        "類型": "主要計劃",
                        "保額": r.get("保額") or 0,
                        "保費": r.get("保費") or 0,
                    }
                )
            _draw_coverage_card(
                pdf,
                title=short,
                status=str(p.get("status") or "ok"),
                have=float(p.get("已有保額") or 0),
                need=float(p.get("建議保額") or 0),
                premium=sum(float(r.get("保費") or 0) for r in pols),
                policies=norm,
            )

    if miss_list:
        _section_title(pdf, f"缺乏保障（{len(miss_list)}項）")
        for p in miss_list:
            short = str(p.get("短名") or str(p.get("保單類型") or "").replace("保險", ""))
            color, icon = _pillar_theme(short)
            _draw_gap_card(pdf, title=f"{short}保障", color=color, icon=icon)

    _draw_disclaimer_bar(
        pdf,
        footer
        or "建議保額只供銷售參考，並非核保或財務建議；實際需要視乎家庭責任、負債、Lifestyle。",
    )
    return _pdf_bytes(pdf)


def build_pfin_pdf(
    *,
    title: str = "保費融資計劃書",
    client: str = "",
    agent: str = "",
    result: dict[str, Any] | None = None,
    footer: str = "",
) -> bytes:
    """Structured Premium Financing proposal PDF (ICON V + bank)."""
    from tt_core.pfin import format_hkd, format_usd, scenario_label

    result = result or {}
    s = result.get("summary") or {}
    bank = result.get("bank") or {}
    pdf, _note = _make_pdf(footer_note=footer)

    _draw_title(pdf, title or "保費融資計劃書")
    _section_title(pdf, "客戶資料")
    info = []
    if client:
        info.append(("客戶姓名", client))
    if agent:
        info.append(("顧問", agent))
    info.append(("日期", datetime.now().strftime("%Y-%m-%d %H:%M")))
    info.append(("產品", str(result.get("product") or "FWD 智盈匯聚 (優越版) V")))
    info.append(("融資銀行", str(bank.get("name") or "—")))
    info.append(("紅利情景", scenario_label(str(result.get("scenario") or "expected"))))
    info.append(("匯率", f"1 USD = {float(result.get('fx') or 7.85):.2f} HKD"))
    _draw_client_info_box(pdf, info)

    _section_title(pdf, "融資摘要")
    heroes = [
        f"首日保證 CV：{format_usd(float(s.get('day1_guaranteed_cv_usd') or 0))}",
        f"貸款：{format_usd(float(s.get('loan_usd') or 0))}",
        f"初期自資：{format_usd(float(s.get('initial_outlay_usd') or 0))}",
        f"槓桿：{float(s.get('leverage_ratio') or 0):.2f}x",
    ]
    _draw_hero_metrics(pdf, heroes)

    detail_rows = [
        ("保費（USD）", format_usd(float(s.get("premium_usd") or 0))),
        ("保費（約 HKD）", format_hkd(float(s.get("premium_hkd") or 0))),
        (
            "保費折扣",
            (
                f"{float(s.get('discount_rate') or 0) * 100:.0f}%（"
                f"{format_usd(float(s.get('discount_usd') or 0))}）"
                if s.get("apply_promotion")
                else "未套用"
            ),
        ),
        ("實付保費", format_usd(float(s.get("actual_premium_paid_usd") or 0))),
        ("LTV 成數", f"{float(s.get('ltv_ratio') or 0) * 100:.0f}%"),
        ("貸款額（約 HKD）", format_hkd(float(s.get("loan_hkd") or 0))),
        ("設立費", format_usd(float(s.get("setup_fee_usd") or 0))),
        ("Levy", format_usd(float(s.get("levy_usd") or 0))),
        (
            "預估年息",
            f"{float(s.get('annual_interest_rate_pct') or 0):.2f}%（約 "
            f"{format_usd(float(s.get('annual_interest_usd') or 0))}/年）",
        ),
    ]
    _draw_client_info_box(pdf, detail_rows)

    if bank.get("rate_formula") or bank.get("badge"):
        _section_title(pdf, "銀行條款（快照）")
        bank_rows = []
        if bank.get("badge"):
            bank_rows.append(("標籤", str(bank["badge"])))
        if bank.get("rate_formula"):
            bank_rows.append(("利率公式", str(bank["rate_formula"])))
        if bank.get("ltv_description"):
            bank_rows.append(("LTV 說明", str(bank["ltv_description"])))
        if bank.get("setup_fee_description"):
            bank_rows.append(("設立費", str(bank["setup_fee_description"])))
        if bank.get("promotion_period"):
            bank_rows.append(("優惠期", str(bank["promotion_period"])))
        _draw_client_info_box(pdf, bank_rows)

    focus = list(result.get("focus_years") or [])
    if focus:
        _section_title(pdf, "重點年份（示意）")
        _draw_pfin_year_table(pdf, focus)

    _draw_disclaimer_bar(
        pdf,
        footer
        or str(result.get("disclaimer") or "")
        or "數字為示意；紅利／利率非保證；實際以正式利益說明及銀行批核為準。",
    )
    return _pdf_bytes(pdf)


def _draw_pfin_year_table(pdf, rows: list[dict[str, Any]]) -> None:
    """Compact year projection table for PFin PDF."""
    from tt_core.pfin import format_usd

    headers = ["年度", "年齡", "退保價值", "扣貸淨值", "累計利息", "淨利潤", "槓桿IRR"]
    # relative column weights
    weights = [0.10, 0.10, 0.18, 0.18, 0.16, 0.16, 0.12]
    col_ws = [pdf.epw * w for w in weights]
    row_h = 7.2

    def _header():
        _ensure_space(pdf, row_h + 4)
        y = pdf.get_y()
        pdf.set_fill_color(*_INK)
        pdf.rect(pdf.l_margin, y, pdf.epw, row_h, style="F")
        x = pdf.l_margin
        pdf.set_font("ttcjk", size=8)
        pdf.set_text_color(*_WHITE)
        for h, w in zip(headers, col_ws):
            pdf.set_xy(x, y + 1.2)
            pdf.cell(w, row_h - 2, h, align="C")
            x += w
        pdf.set_y(y + row_h)

    _header()
    for i, r in enumerate(rows):
        _ensure_space(pdf, row_h + 2)
        y = pdf.get_y()
        fill = _SOFT if i % 2 == 0 else _WHITE
        pdf.set_fill_color(*fill)
        pdf.rect(pdf.l_margin, y, pdf.epw, row_h, style="F")
        vals = [
            f"第 {int(r.get('year') or 0)}",
            f"{int(r.get('age') or 0)}",
            format_usd(float(r.get("total_sv_usd") or 0)),
            format_usd(float(r.get("net_sv_usd") or 0)),
            format_usd(float(r.get("cumulative_interest_usd") or 0)),
            format_usd(float(r.get("net_profit_usd") or 0)),
            f"{float(r.get('leveraged_irr_pct') or 0):.1f}%",
        ]
        x = pdf.l_margin
        pdf.set_font("ttcjk", size=8)
        pdf.set_text_color(*_TEXT)
        for v, w in zip(vals, col_ws):
            pdf.set_xy(x, y + 1.2)
            pdf.cell(w, row_h - 2, _fit(pdf, v, w - 2), align="C")
            x += w
        pdf.set_y(y + row_h)
    pdf.ln(3)


def build_client_pdf(
    *,
    title: str,
    body: str,
    client: str = "",
    tool_name: str = "",
    agent: str = "",
    footer: str = "",
    pdf_data: dict[str, Any] | None = None,
) -> bytes:
    """
    Render client PDF. If pdf_data kind == 'protection_gap', use card layout;
    otherwise render WA body with the same professional chrome.
    """
    data = pdf_data or {}
    if data.get("kind") == "protection_gap":
        return build_protection_gap_pdf(
            title=title or "保障缺口分析報告",
            client=client,
            agent=agent,
            pillars=data.get("pillars") or [],
            policies=data.get("policies") or [],
            summary=data.get("summary") or {},
            total_have=float(data.get("total_have") or 0),
            total_gap=float(data.get("total_gap") or 0),
            total_prem=float(data.get("total_prem") or 0),
            footer=footer,
        )
    if data.get("kind") == "pfin":
        return build_pfin_pdf(
            title=title or "保費融資計劃書",
            client=client,
            agent=agent,
            result=data.get("result") or {},
            footer=footer,
        )

    pdf, note = _make_pdf(footer_note=footer)
    blocks = parse_report_blocks(body)
    if not blocks:
        blocks = [("body", "（未有內容）")]

    _draw_title(pdf, title)
    _section_title(pdf, "客戶資料")
    info = []
    if client:
        info.append(("客戶姓名", client))
    if tool_name:
        info.append(("工具", tool_name))
    if agent:
        info.append(("顧問", agent))
    info.append(("日期", datetime.now().strftime("%Y-%m-%d %H:%M")))
    _draw_client_info_box(pdf, info)

    _section_title(pdf, "報告內容")

    # Hero metrics as compact ink strip
    heroes = [t for k, t in blocks if k == "hero"]
    if heroes:
        _draw_hero_metrics(pdf, heroes[:3])

    for kind, text in blocks:
        if kind == "hero":
            continue
        if kind == "blank":
            pdf.ln(2)
            continue
        if kind == "section":
            # Sub-section as soft bar
            y = pdf.get_y()
            _ensure_space(pdf, 10)
            pdf.set_fill_color(*_SOFT)
            pdf.rect(pdf.l_margin, y, pdf.epw, 8, style="F", round_corners=True, corner_radius=1.5)
            pdf.set_fill_color(*_INK)
            pdf.rect(pdf.l_margin, y + 1.5, 1.4, 5, style="F")
            pdf.set_xy(pdf.l_margin + 5, y + 1.5)
            pdf.set_font("ttcjk", size=10)
            pdf.set_text_color(*_TEXT)
            pdf.cell(pdf.epw - 8, 5, text, align="L")
            pdf.set_y(y + 10)
            continue
        if kind == "strong":
            label, value = _split_kv(text)
            y = pdf.get_y()
            pdf.set_draw_color(*_LINE)
            pdf.set_line_width(0.2)
            pdf.line(pdf.l_margin, y, pdf.w - pdf.r_margin, y)
            pdf.set_xy(pdf.l_margin, y + 1.5)
            pdf.set_font("ttcjk", size=9.5)
            pdf.set_text_color(*_MUTED)
            pdf.cell(pdf.epw * 0.45, 6, label or text, align="L")
            pdf.set_font("ttcjk", size=10.5)
            pdf.set_text_color(*_INK)
            pdf.cell(pdf.epw * 0.55, 6, value, align="R")
            pdf.set_y(y + 8.5)
            continue
        if kind == "bullet":
            y = pdf.get_y()
            pdf.set_fill_color(*_GOLD)
            pdf.ellipse(pdf.l_margin + 1.5, y + 2.2, 1.8, 1.8, style="F")
            pdf.set_xy(pdf.l_margin + 6, y)
            pdf.set_font("ttcjk", size=10)
            pdf.set_text_color(*_TEXT)
            pdf.multi_cell(pdf.epw - 6, 5.5, text)
            pdf.ln(0.5)
            continue
        if kind == "detail":
            pdf.set_x(pdf.l_margin + 6)
            pdf.set_font("ttcjk", size=9)
            pdf.set_text_color(*_MUTED)
            pdf.multi_cell(pdf.epw - 6, 5, text)
            continue
        if kind == "note":
            pdf.set_x(pdf.l_margin)
            pdf.set_font("ttcjk", size=8.5)
            pdf.set_text_color(*_MUTED)
            pdf.multi_cell(pdf.epw, 4.5, text)
            pdf.ln(1)
            continue
        if kind == "kv":
            label, value = _split_kv(text)
            y = pdf.get_y()
            _rrect(pdf, pdf.l_margin, y, pdf.epw, 8.5, fill=_WHITE, draw=_LINE, radius=1.5)
            pdf.set_xy(pdf.l_margin + 3, y + 1.8)
            pdf.set_font("ttcjk", size=8)
            pdf.set_text_color(*_MUTED)
            pdf.cell(32, 5, label, align="L")
            pdf.set_font("ttcjk", size=10)
            pdf.set_text_color(*_TEXT)
            pdf.cell(pdf.epw - 40, 5, value, align="L")
            pdf.set_y(y + 10)
            continue
        pdf.set_x(pdf.l_margin)
        pdf.set_font("ttcjk", size=10)
        pdf.set_text_color(*_TEXT)
        pdf.multi_cell(pdf.epw, 5.5, text)
        pdf.ln(0.5)

    _draw_disclaimer_bar(pdf, footer or note)
    return _pdf_bytes(pdf)


def _draw_hero_metrics(pdf, items: list[str]) -> None:
    n = len(items)
    y = pdf.get_y()
    h = 16
    _ensure_space(pdf, h + 4)
    pdf.set_fill_color(*_INK)
    pdf.rect(pdf.l_margin, y, pdf.epw, h, style="F", round_corners=True, corner_radius=3)
    col_w = pdf.epw / n
    for i, text in enumerate(items):
        label, value = _split_kv(text)
        if not value:
            label, value = "重點", label
        x = pdf.l_margin + i * col_w
        pdf.set_xy(x + 3, y + 2.5)
        pdf.set_font("ttcjk", size=7.5)
        pdf.set_text_color(*_GOLD)
        pdf.cell(col_w - 6, 4, label, align="L")
        pdf.set_xy(x + 3, y + 7.5)
        pdf.set_font("ttcjk", size=11)
        pdf.set_text_color(*_WHITE)
        pdf.cell(col_w - 6, 5.5, _fit(pdf, value, col_w - 8), align="L")
        if i < n - 1:
            pdf.set_draw_color(55, 70, 100)
            pdf.set_line_width(0.2)
            pdf.line(x + col_w, y + 3, x + col_w, y + h - 3)
    pdf.set_y(y + h + 4)
