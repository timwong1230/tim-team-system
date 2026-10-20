"""Client-facing PDF reports for 客戶工具."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def test_strip_whatsapp_markup():
    from tt_core.client_pdf import strip_whatsapp_markup

    raw = "🛡️ *保障分析摘要* — 陳生\n\n_只供參考_"
    plain = strip_whatsapp_markup(raw)
    assert "*" not in plain
    assert "_" not in plain
    assert "保障分析摘要" in plain
    assert "陳生" in plain
    assert "只供參考" in plain


def test_build_client_pdf_contains_chinese_and_is_pdf():
    from tt_core.client_pdf import build_client_pdf, pdf_filename, resolve_cjk_font

    font = resolve_cjk_font()
    assert Path(font).is_file()

    body = (
        "保障分析摘要 — 陳生\n\n"
        "四大保障達標：0/4\n"
        "• 人壽：有買但不足\n"
        "  已有 $1,000,000／建議 $5,000,000\n"
        "保障缺口約：$6,000,000\n"
    )
    data = build_client_pdf(
        title="保障缺口分析報告",
        body=body,
        client="陳生",
        tool_name="保障缺口",
        agent="Tim",
    )
    assert data.startswith(b"%PDF")
    assert len(data) > 500
    name = pdf_filename(client="陳生", tool="保障缺口")
    assert name.endswith(".pdf")
    assert "TIM-" in name


def test_app_wires_pdf_download_on_client_tools():
    src = (_ROOT / "app.py").read_text(encoding="utf-8")
    assert "下載 PDF 報告" in src
    assert "build_client_pdf" in src
    assert "pdf_title" in src
    assert "帶得走：WhatsApp／PDF" in src
    # All four client tools + recruit compare pass pdf_title
    assert src.count("pdf_title=") >= 4


def test_requirements_and_packages_for_pdf():
    req = (_ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert "fpdf2" in req
    pkgs = (_ROOT / "packages.txt").read_text(encoding="utf-8")
    assert "fonts-wqy-microhei" in pkgs or "fonts-droid" in pkgs
