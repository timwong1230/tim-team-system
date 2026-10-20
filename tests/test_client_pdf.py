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


def test_parse_report_blocks_classifies_structure():
    from tt_core.client_pdf import parse_report_blocks

    raw = (
        "🛡️ *保障分析摘要* — 陳生\n\n"
        "四大保障達標：*0/4*\n"
        "• *人壽*：有買但不足\n"
        "  已有 $1,000,000／建議 $5,000,000\n"
        "已有保障總額：$1,000,000\n"
        "保障缺口約：*$6,000,000*\n"
        "_只供參考_\n"
    )
    blocks = parse_report_blocks(raw)
    kinds = [k for k, _ in blocks]
    texts = [t for _, t in blocks]
    assert not any("保障分析摘要" in t for t in texts)
    assert "bullet" in kinds
    assert "detail" in kinds
    assert "hero" in kinds
    assert "strong" in kinds
    assert "note" in kinds
    assert any("保障缺口" in t for k, t in blocks if k == "hero")


def test_build_client_pdf_contains_chinese_and_is_pdf():
    from tt_core.client_pdf import build_client_pdf, pdf_filename, resolve_cjk_font

    font = resolve_cjk_font()
    assert Path(font).is_file()

    body = (
        "*保障分析摘要* — 陳生\n\n"
        "四大保障達標：*0/4*\n"
        "• *人壽*：有買但不足\n"
        "  已有 $1,000,000／建議 $5,000,000\n"
        "• *危疾*：未有\n"
        "  已有 $0／建議 $2,000,000\n"
        "保障缺口約：*$6,000,000*\n"
        "_呢份只供參考，實際需要視乎家庭責任。_\n"
    )
    data = build_client_pdf(
        title="保障缺口分析報告",
        body=body,
        client="陳生",
        tool_name="保障缺口",
        agent="Tim",
    )
    assert data.startswith(b"%PDF")
    assert len(data) > 800
    name = pdf_filename(client="陳生", tool="保障缺口")
    assert name.endswith(".pdf")
    assert "TIM-" in name


def test_build_protection_gap_pdf_card_layout():
    from tt_core.client_pdf import build_protection_gap_pdf, format_hkd_report

    assert format_hkd_report(300000).startswith("HK$")
    pillars = [
        {
            "保單類型": "人壽保險",
            "短名": "人壽",
            "已有保額": 0,
            "建議保額": 5_000_000,
            "status": "missing",
            "status_label": "未做／缺口",
        },
        {
            "保單類型": "危疾保險",
            "短名": "危疾",
            "已有保額": 300_000,
            "建議保額": 500_000,
            "status": "short",
            "status_label": "有買但不足",
        },
        {
            "保單類型": "醫療保險",
            "短名": "醫療",
            "已有保額": 1_000_000,
            "建議保額": 1_000_000,
            "status": "ok",
            "status_label": "已達標",
        },
        {
            "保單類型": "意外保險",
            "短名": "意外",
            "已有保額": 500_000,
            "建議保額": 500_000,
            "status": "ok",
            "status_label": "已達標",
        },
    ]
    policies = [
        {"保單類型": "危疾保險", "保險公司": "CTF Life", "保額": 300_000, "保費": 377},
        {"保單類型": "醫療保險", "保險公司": "FWD", "保額": 1_000_000, "保費": 446},
        {"保單類型": "意外保險", "保險公司": "AIA", "保額": 500_000, "保費": 90},
    ]
    data = build_protection_gap_pdf(
        client="陳生",
        agent="Tim",
        pillars=pillars,
        policies=policies,
        summary={"ready": 2, "total": 4},
        total_have=1_800_000,
        total_gap=5_200_000,
        total_prem=913,
    )
    assert data.startswith(b"%PDF")
    assert len(data) > 2000


def test_app_wires_pdf_download_on_client_tools():
    src = (_ROOT / "app.py").read_text(encoding="utf-8")
    assert "下載 PDF 報告" in src
    assert "build_client_pdf" in src
    assert "pdf_title" in src
    assert "帶得走：WhatsApp／PDF" in src
    assert 'kind": "protection_gap"' in src or "protection_gap" in src
    assert src.count("pdf_title=") >= 4


def test_requirements_and_packages_for_pdf():
    req = (_ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert "fpdf2" in req
    pkgs = (_ROOT / "packages.txt").read_text(encoding="utf-8")
    assert "fonts-wqy-microhei" in pkgs or "fonts-droid" in pkgs
