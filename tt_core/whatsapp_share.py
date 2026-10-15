"""Client-facing WhatsApp summaries for sales tools (帶得走)."""

from __future__ import annotations

import urllib.parse
from typing import Any


def wa_me_url(text: str) -> str:
    """Open WhatsApp with prefilled message (no phone → pick chat)."""
    return f"https://wa.me/?text={urllib.parse.quote(text or '')}"


def _name_bit(client: str | None) -> str:
    name = str(client or "").strip()
    return f"— {name}" if name else ""


def protection_gap_summary(
    *,
    client: str = "",
    pillars: list[dict[str, Any]],
    summary: dict[str, Any],
    total_have: float,
    total_gap: float,
    total_prem: float,
    format_hkd,
) -> str:
    """短訊：四大保障狀態 + 缺口，方便 send 俾客戶。"""
    lines = [
        f"🛡️ *保障分析摘要* {_name_bit(client)}".rstrip(),
        "",
        f"四大保障達標：*{summary.get('ready', 0)}/{summary.get('total', 4)}*",
        "",
    ]
    for p in pillars:
        short = p.get("短名") or p.get("保單類型") or ""
        status = p.get("status_label") or ""
        have = format_hkd(p.get("已有保額") or 0)
        need = format_hkd(p.get("建議保額") or 0)
        lines.append(f"• *{short}*：{status}")
        lines.append(f"  已有 {have}／建議 {need}")
    lines += [
        "",
        f"已有保障總額：{format_hkd(total_have)}",
        f"保障缺口約：*{format_hkd(total_gap)}*",
        f"現有每月保費：{format_hkd(total_prem)}",
        "",
        "_呢份只供參考，實際需要視乎家庭責任、負債同 Lifestyle。有興趣再約詳談 🙂_",
    ]
    return "\n".join(lines)


def cashflow_summary(
    *,
    client: str = "",
    income: float,
    expense: float,
    cashflow: float,
    income_lines: list[tuple[str, float]] | None = None,
    expense_lines: list[tuple[str, float]] | None = None,
    format_hkd,
    budget_hint: str = "",
) -> str:
    """短訊：收入／支出／Cashflow + 保費 budget。"""
    lines = [
        f"💹 *每月 Cashflow 摘要* {_name_bit(client)}".rstrip(),
        "",
        "*收入*",
    ]
    for lab, amt in income_lines or []:
        if amt and float(amt) > 0:
            lines.append(f"• {lab}：{format_hkd(amt)}")
    lines.append(f"總收入：*{format_hkd(income)}*")
    lines += ["", "*支出*"]
    for lab, amt in expense_lines or []:
        if amt and float(amt) > 0:
            lines.append(f"• {lab}：{format_hkd(amt)}")
    lines.append(f"總支出：*{format_hkd(expense)}*")
    cf_emoji = "✅" if cashflow > 0 else ("⚠️" if cashflow < 0 else "➖")
    lines += [
        "",
        f"{cf_emoji} *每月 Cashflow：{format_hkd(cashflow)}*",
        "",
    ]
    if budget_hint:
        lines.append(budget_hint)
        lines.append("")
    lines.append("_數字供參考，可再一齊調整。有興趣了解儲蓄計劃再約 🙂_")
    return "\n".join(lines)


def medical_uw_summary(
    *,
    client: str = "",
    disease_zh: str,
    disease_en: str = "",
    scenario_label: str,
    outcomes: dict[str, Any],
    product_labels: dict[str, str],
    answer_rows: list[tuple[str, str]] | None = None,
    extra_reqs: list[str] | None = None,
) -> str:
    """短訊：健康討論／核保參考摘要（強調非最終核保）。"""
    title = disease_zh
    if disease_en:
        title = f"{disease_zh}（{disease_en}）"
    lines = [
        f"🩺 *健康狀況討論摘要* {_name_bit(client)}".rstrip(),
        "",
        f"疾病：*{title}*",
        f"對應情況：{scenario_label}",
        "",
    ]
    if answer_rows:
        lines.append("*問答重點*")
        for q, a in answer_rows[:8]:
            lines.append(f"• {q}：{a}")
        lines.append("")
    lines.append("*各計劃參考結果*")
    for key in ("life", "ci", "medical", "accident", "cancer"):
        lab = product_labels.get(key, key)
        val = outcomes.get(key, "—")
        lines.append(f"• {lab}：{val}")
    if extra_reqs:
        lines += ["", "*可能附加要求*"]
        for line in extra_reqs[:5]:
            lines.append(f"• {line}")
    lines += [
        "",
        "⚠️ _以上只供參考，並非正式核保決定；最終以保險公司核保為準。_",
        "_如需正式申請，我哋再一齊準備 🙂_",
    ]
    return "\n".join(lines)
