"""WhatsApp summary helpers for sales tools."""

from __future__ import annotations

from tt_core.whatsapp_share import (
    cashflow_summary,
    medical_uw_summary,
    protection_gap_summary,
    wa_me_url,
)


def _hkd(n: float) -> str:
    sign = "-" if n < 0 else ""
    return f"{sign}${abs(n):,.0f}"


def test_wa_me_url_encodes():
    url = wa_me_url("你好 *測試*")
    assert url.startswith("https://wa.me/?text=")
    assert "你好" in url or "%E4%BD%A0%E5%A5%BD" in url


def test_protection_gap_summary():
    pillars = [
        {
            "短名": "人壽",
            "status_label": "有買但不足",
            "已有保額": 1_000_000,
            "建議保額": 5_000_000,
        },
        {
            "短名": "危疾",
            "status_label": "未做／缺口",
            "已有保額": 0,
            "建議保額": 2_000_000,
        },
    ]
    text = protection_gap_summary(
        client="陳生",
        pillars=pillars,
        summary={"ready": 0, "total": 4},
        total_have=1_000_000,
        total_gap=6_000_000,
        total_prem=800,
        format_hkd=_hkd,
    )
    assert "陳生" in text
    assert "人壽" in text and "危疾" in text
    assert "保障缺口" in text
    assert "$6,000,000" in text


def test_cashflow_summary():
    text = cashflow_summary(
        client="陳太",
        income=50_000,
        expense=35_000,
        cashflow=15_000,
        income_lines=[("工作收入", 50_000)],
        expense_lines=[("家用", 20_000), ("個人開支", 15_000)],
        format_hkd=_hkd,
        budget_hint="可考慮每月儲蓄保險保費 budget 約 $4,500–$7,500",
    )
    assert "陳太" in text
    assert "Cashflow" in text
    assert "$15,000" in text
    assert "工作收入" in text


def test_medical_uw_summary_has_disclaimer():
    text = medical_uw_summary(
        client="阿明",
        disease_zh="高血壓",
        disease_en="Hypertension",
        scenario_label="控制良好",
        outcomes={"life": "標準", "ci": "加費", "medical": "標準", "accident": "標準", "cancer": "標準"},
        product_labels={"life": "人壽", "ci": "危疾", "medical": "醫療", "accident": "意外", "cancer": "癌症"},
        answer_rows=[("控制情況", "良好")],
    )
    assert "高血壓" in text
    assert "人壽：標準" in text
    assert "非正式核保" in text or "只供參考" in text
