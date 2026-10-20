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

# Compact Traditional-Chinese-capable fallback (~2–4MB) if apt fonts missing
_FALLBACK_FONT_URL = (
    "https://github.com/StellarCN/scp_zh/raw/master/fonts/SimHei.ttf"
)
_MD_BOLD = re.compile(r"\*(.+?)\*")
_MD_EMPH = re.compile(r"_(.+?)_")
_EMOJIish = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U00002700-\U000027BF"
    "\U0001F1E0-\U0001F1FF"
    "]+",
    flags=re.UNICODE,
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
    # One-shot download for Cloud images without apt Chinese fonts
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


def build_client_pdf(
    *,
    title: str,
    body: str,
    client: str = "",
    tool_name: str = "",
    agent: str = "",
    footer: str = "",
) -> bytes:
    """Render a simple branded multi-page PDF (Traditional Chinese OK)."""
    from fpdf import FPDF

    font_path = resolve_cjk_font()
    plain = strip_whatsapp_markup(body)
    if not plain:
        plain = "（未有內容）"

    class _Report(FPDF):
        def header(self) -> None:
            self.set_x(self.l_margin)
            self.set_font("ttcjk", size=9)
            self.set_text_color(154, 123, 26)
            self.cell(self.epw, 6, "TIM TEAM · 客戶報告", align="L")
            self.ln(2)
            self.set_draw_color(197, 160, 40)
            self.set_line_width(0.4)
            self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
            self.ln(6)

        def footer(self) -> None:
            self.set_y(-14)
            self.set_x(self.l_margin)
            self.set_font("ttcjk", size=8)
            self.set_text_color(120, 120, 120)
            note = footer or "本報告只供參考，並非正式報價／核保決定；詳情以保險公司條款為準。"
            # Use epw (not 0) so cursor x never collapses usable width
            self.multi_cell(self.epw, 4, note, align="C")
            self.set_y(-8)
            self.set_x(self.l_margin)
            self.cell(self.epw, 4, f"第 {self.page_no()} 頁", align="C")

    pdf = _Report(format="A4")
    pdf.set_margins(16, 16, 16)
    pdf.set_auto_page_break(auto=True, margin=18)
    # Must register before add_page() — header() needs the font immediately
    pdf.add_font("ttcjk", fname=font_path)
    pdf.add_page()
    pdf.set_x(pdf.l_margin)

    pdf.set_text_color(28, 36, 48)
    pdf.set_font("ttcjk", size=18)
    pdf.multi_cell(pdf.epw, 9, str(title or "客戶報告").strip())
    pdf.ln(2)

    meta_bits = []
    if client:
        meta_bits.append(f"客戶：{client}")
    if tool_name:
        meta_bits.append(f"工具：{tool_name}")
    if agent:
        meta_bits.append(f"顧問：{agent}")
    meta_bits.append(f"日期：{datetime.now().strftime('%Y-%m-%d %H:%M')}")
    pdf.set_font("ttcjk", size=10)
    pdf.set_text_color(107, 114, 128)
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(pdf.epw, 5, "  ·  ".join(meta_bits))
    pdf.ln(3)
    y = pdf.get_y()
    pdf.set_draw_color(232, 228, 217)
    pdf.line(pdf.l_margin, y, pdf.w - pdf.r_margin, y)
    pdf.ln(5)

    pdf.set_text_color(28, 36, 48)
    pdf.set_font("ttcjk", size=12)
    for para in plain.split("\n"):
        line = para.rstrip()
        if not line:
            pdf.ln(3)
            continue
        # Normalize bullets that some fonts measure poorly
        if line.startswith("•"):
            line = "-" + line[1:]
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(pdf.epw, 7, line)
    # fpdf output
    out = pdf.output()
    if isinstance(out, (bytes, bytearray)):
        return bytes(out)
    # older fpdf returned str
    return str(out).encode("latin-1")


def pdf_filename(*, title: str = "", client: str = "", tool: str = "") -> str:
    """Safe download filename."""
    stamp = datetime.now().strftime("%Y%m%d")
    base = (client or tool or title or "client-report").strip()
    base = re.sub(r"[\\/:*?\"<>|]+", "", base)
    base = re.sub(r"\s+", "", base)[:24] or "report"
    return f"TIM-{base}-{stamp}.pdf"


def report_sha(data: bytes) -> str:
    return hashlib.sha256(data or b"").hexdigest()[:12]
