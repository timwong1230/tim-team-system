"""Match current-quarter customer premium discounts onto proposal sections."""

from __future__ import annotations

import re
from typing import Any

from tt_core.quarterly_offers import current_quarter_key, default_catalog

# proposal product_id -> tokens matched against offer「產品」column
PRODUCT_OFFER_TOKENS: dict[str, list[str]] = {
    "vfamily": ["醫家保"],
    "vprime": ["尊衛您"],
    "vbooster": ["倍衛您"],
    "vtheone": ["至．衛一", "至.衛一", "衛一"],
    "veasy": ["易衛您"],
    "vsmartstaff": ["智員善", "智．升", "智.升"],
    "gba_op": ["大灣區"],
    "ci_yingyuan": ["應援保"],
    "ci_yingyuan_plus": ["應援保"],
    "ci_zhishang": ["緻尚保"],
    "ci_zhishang_plus": ["緻尚保"],
    "ci_easy": ["好易揀"],
    "full_care_accident": ["全意守護"],
    "chengyu_term": ["承譽"],
    "zizhubao_term": ["自主保"],
    "yingju5": ["盈聚"],
    "yingshuoyue": ["盈∙歲悅", "盈歲悅", "歲悅"],
    "zhiying_v": ["智盈匯聚"],
}


def _load_customer_catalog(quarter: str | None = None) -> dict[str, Any]:
    q = quarter or current_quarter_key()
    try:
        from tt_core.data import get_quarterly_catalog

        cat = get_quarterly_catalog(q, "customer")
        if isinstance(cat, dict) and cat.get("sections"):
            return cat
    except Exception:
        pass
    return default_catalog(q, "customer")


def _row_dict(columns: list[str], cells: list[Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for i, col in enumerate(columns):
        out[str(col)] = str(cells[i] if i < len(cells) else "").strip()
    return out


def _offer_text(row: dict[str, str]) -> str:
    for key in ("優惠重點", "優惠", "詳情"):
        if row.get(key):
            return row[key]
    # fallback: join non-product columns
    parts = [v for k, v in row.items() if k != "產品" and v]
    return "\n".join(parts)


def _match_score(product_cell: str, tokens: list[str]) -> int:
    cell = str(product_cell or "")
    score = 0
    for t in tokens:
        if t and t in cell:
            score += len(t)
    return score


def _prefer_row(
    product_id: str,
    rows: list[tuple[int, dict[str, str]]],
) -> dict[str, str] | None:
    if not rows:
        return None
    rows = sorted(rows, key=lambda x: -x[0])
    best_score = rows[0][0]
    top = [r for s, r in rows if s == best_score]
    if product_id == "vfamily":
        # Prefer 無子女／基本；避開「+ 子女之家…」加購列
        no_child = [
            r
            for r in top
            if "子女之家" not in (r.get("產品") or "")
            and "+ 子女" not in (r.get("產品") or "")
        ]
        if no_child:
            return no_child[0]
    if product_id in {"vprime", "vbooster"}:
        # Shared 倍衛您／尊衛您 row — keep as-is; deductible line picked later
        return top[0]
    return top[0]


def _pick_deductible_lines(detail: str, deductible: int | None) -> str:
    text = str(detail or "").replace("\\n", "\n")
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if deductible is None or not any("自付費" in ln for ln in lines):
        return text.strip()

    ded = int(deductible)
    chosen: list[str] = []
    extras: list[str] = []
    for ln in lines:
        if "齊投保" in ln:
            extras.append(ln)
            continue
        if re.search(r"自付費\s*0\b", ln) or "自付費$0" in ln:
            if ded == 0:
                chosen.append(ln)
            continue
        if "<$100k" in ln or "< $100k" in ln or "＜$100k" in ln:
            if 0 < ded < 100_000:
                chosen.append(ln)
            continue
        if "≥$100k" in ln or ">=$100k" in ln or "≧$100k" in ln:
            if ded >= 100_000:
                chosen.append(ln)
            continue
    if chosen:
        return "\n".join(chosen + extras)
    return text.strip()


def _first_year_net_hkd(annual: float, detail: str) -> tuple[float | None, str]:
    """Return (net first-year HKD, short reason) when detail encodes 首年 discount."""
    if annual <= 0:
        return None, ""
    text = str(detail or "")
    # 首年 3 個月 / 首年 5／次年 3／…（月份串）
    m = re.search(r"首年\s*(\d+)\s*(?:個?月|／|/)", text)
    if m:
        months = int(m.group(1))
        if 0 < months < 12:
            net = round(float(annual) * (12 - months) / 12.0, 0)
            return net, f"已扣 {months} 個月"
    m = re.search(r"首年\s*(\d+(?:\.\d+)?)\s*%", text)
    if m:
        pct = float(m.group(1))
        if 0 < pct < 100:
            net = round(float(annual) * (1.0 - pct / 100.0), 0)
            return net, f"已扣 {pct:g}%"
    return None, ""


def find_customer_offer(
    product_id: str,
    *,
    deductible: int | None = None,
    annual_hkd: float | None = None,
    quarter: str | None = None,
) -> dict[str, Any] | None:
    """Look up current-quarter customer offer for a proposal product."""
    tokens = PRODUCT_OFFER_TOKENS.get(str(product_id) or "")
    if not tokens:
        return None
    cat = _load_customer_catalog(quarter)
    scored: list[tuple[int, dict[str, str]]] = []
    for sec in cat.get("sections") or []:
        cols = [str(c) for c in (sec.get("columns") or [])]
        if not cols:
            continue
        for raw in sec.get("rows") or []:
            row = _row_dict(cols, list(raw))
            product_cell = row.get("產品") or row.get("項目") or ""
            score = _match_score(product_cell, tokens)
            if score > 0:
                scored.append((score, row))
    picked = _prefer_row(str(product_id), scored)
    if not picked:
        return None
    detail = _pick_deductible_lines(_offer_text(picked), deductible)
    note = picked.get("備註") or ""
    annual = float(annual_hkd or 0)
    net, reason = _first_year_net_hkd(annual, detail)
    q = (quarter or current_quarter_key()).upper()
    out: dict[str, Any] = {
        "label": "保費折扣",
        "quarter": q,
        "product_label": picked.get("產品") or picked.get("項目") or "",
        "detail": detail,
        "note": note,
        "banner": str(cat.get("banner") or ""),
        "footnote": str(cat.get("footnote") or ""),
    }
    if net is not None:
        out["first_year_hkd"] = net
        out["first_year_display"] = f"推廣期首年約 HK${net:,.0f}（{reason}）"
    return out


def attach_offer_to_section(section: dict[str, Any]) -> dict[str, Any]:
    """Mutate section with promo block when a customer offer matches."""
    opts = section.get("options") or {}
    ded = opts.get("deductible")
    if ded is not None:
        try:
            ded = int(ded)
        except Exception:
            ded = None
    promo = find_customer_offer(
        str(section.get("product_id") or ""),
        deductible=ded,
        annual_hkd=float(section.get("premium_annual_hkd") or 0),
    )
    if promo:
        section["promo"] = promo
    return section
