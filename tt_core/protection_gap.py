"""保障缺口 — existing policies vs recommended cover for protection sales."""

from __future__ import annotations

import math
from typing import Any

POLICY_TYPES = ["人壽保險", "危疾保險", "醫療保險", "意外保險", "其他"]

# Complete protection = these four pillars (equal visual weight in the status pie)
CORE_PILLARS = ["人壽保險", "危疾保險", "醫療保險", "意外保險"]

STATUS_LABELS = {
    "ok": "已達標",
    "short": "有買但不足",
    "missing": "未做／缺口",
}

STATUS_COLORS = {
    "ok": "#059669",
    "short": "#D97706",
    "missing": "#DC2626",
}

DEFAULT_RULES = {
    "人壽保險": {"multiple_of_annual_income": 10.0, "floor": 1_000_000.0},
    "危疾保險": {"multiple_of_annual_income": 4.0, "floor": 500_000.0},
    "醫療保險": {"flat": 1_000_000.0},
    "意外保險": {"multiple_of_annual_income": 3.0, "floor": 500_000.0},
    "其他": {"flat": 0.0},
}

EMPTY_ROW = {
    "保單類型": "人壽保險",
    "保險公司": "",
    "保額": 0.0,
    "保費": 0.0,
}


def empty_portfolio(n: int = 4) -> list[dict[str, Any]]:
    return [dict(EMPTY_ROW) for _ in range(n)]


def _num(v: Any) -> float:
    try:
        if v is None or v == "":
            return 0.0
        return float(v)
    except Exception:
        return 0.0


def suggested_targets(monthly_income: float) -> dict[str, float]:
    annual = max(0.0, _num(monthly_income)) * 12.0
    out: dict[str, float] = {}
    for ptype, rule in DEFAULT_RULES.items():
        if "flat" in rule:
            out[ptype] = float(rule["flat"])
        else:
            mult = float(rule.get("multiple_of_annual_income") or 0)
            floor = float(rule.get("floor") or 0)
            out[ptype] = max(floor, annual * mult) if annual > 0 else floor
    return out


def normalize_rows(rows: list[dict] | None) -> list[dict[str, Any]]:
    clean: list[dict[str, Any]] = []
    for raw in rows or []:
        if not isinstance(raw, dict):
            continue
        ptype = str(raw.get("保單類型") or "").strip() or "其他"
        if ptype not in POLICY_TYPES:
            ptype = "其他"
        company = str(raw.get("保險公司") or "").strip()
        cover = _num(raw.get("保額"))
        premium = _num(raw.get("保費"))
        if cover <= 0 and premium <= 0 and not company:
            continue
        clean.append(
            {
                "保單類型": ptype,
                "保險公司": company,
                "保額": cover,
                "保費": premium,
            }
        )
    return clean


def aggregate(rows: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    agg = {t: {"cover": 0.0, "premium": 0.0, "count": 0.0} for t in POLICY_TYPES}
    for r in rows:
        t = r["保單類型"]
        if t not in agg:
            t = "其他"
        agg[t]["cover"] += _num(r.get("保額"))
        agg[t]["premium"] += _num(r.get("保費"))
        agg[t]["count"] += 1
    return agg


def gap_table(
    rows: list[dict[str, Any]], targets: dict[str, float]
) -> list[dict[str, Any]]:
    agg = aggregate(rows)
    out = []
    for t in POLICY_TYPES:
        if t == "其他" and agg[t]["cover"] <= 0 and _num(targets.get(t)) <= 0:
            continue
        have = agg[t]["cover"]
        need = max(0.0, _num(targets.get(t)))
        gap = max(0.0, need - have)
        covered_pct = (have / need * 100.0) if need > 0 else (100.0 if have > 0 else 0.0)
        out.append(
            {
                "保單類型": t,
                "已有保額": round(have, 0),
                "建議保額": round(need, 0),
                "保障缺口": round(gap, 0),
                "已保障%": round(min(covered_pct, 999.0), 1),
                "現有月保費": round(agg[t]["premium"], 0),
                "保單數": int(agg[t]["count"]),
            }
        )
    return out


def pie_current_cover(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    agg = aggregate(rows)
    return [
        {"類型": t, "保額": round(v["cover"], 0)}
        for t, v in agg.items()
        if v["cover"] > 0
    ]


def pie_gap_vs_covered(gap_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    covered = 0.0
    gap = 0.0
    for r in gap_rows:
        if r["保單類型"] == "其他":
            continue
        covered += _num(r["已有保額"])
        gap += _num(r["保障缺口"])
    slices = []
    if covered > 0:
        slices.append({"項目": "已有保障", "金額": round(covered, 0)})
    if gap > 0:
        slices.append({"項目": "保障缺口", "金額": round(gap, 0)})
    if not slices:
        slices.append({"項目": "尚未輸入", "金額": 1})
    return slices


def classify_pillar(have: float, need: float) -> str:
    have = _num(have)
    need = _num(need)
    if have <= 0:
        return "missing"
    if need <= 0:
        return "ok"
    if have + 1e-6 >= need * 0.8:
        return "ok"
    return "short"


def pillar_status(gap_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Always return 4 core pillars so missing types stay visible (equal weight)."""
    by_type = {r["保單類型"]: r for r in gap_rows}
    out = []
    for t in CORE_PILLARS:
        r = by_type.get(t) or {
            "保單類型": t,
            "已有保額": 0.0,
            "建議保額": 0.0,
            "保障缺口": 0.0,
            "已保障%": 0.0,
        }
        have = _num(r.get("已有保額"))
        need = _num(r.get("建議保額"))
        gap = _num(r.get("保障缺口"))
        status = classify_pillar(have, need)
        out.append(
            {
                "保單類型": t,
                "短名": t.replace("保險", ""),
                "已有保額": have,
                "建議保額": need,
                "保障缺口": gap,
                "已保障%": _num(r.get("已保障%")),
                "status": status,
                "status_label": STATUS_LABELS[status],
                "color": STATUS_COLORS[status],
                "weight": 1.0,
            }
        )
    return out


def completeness_summary(pillars: list[dict[str, Any]]) -> dict[str, Any]:
    ok = sum(1 for p in pillars if p["status"] == "ok")
    short = sum(1 for p in pillars if p["status"] == "short")
    missing = sum(1 for p in pillars if p["status"] == "missing")
    return {
        "ok": ok,
        "short": short,
        "missing": missing,
        "ready": ok,
        "total": len(CORE_PILLARS),
        "missing_names": [p["短名"] for p in pillars if p["status"] == "missing"],
        "short_names": [p["短名"] for p in pillars if p["status"] == "short"],
        "complete": missing == 0 and short == 0,
    }


def format_hkd(amount: float) -> str:
    sign = "-" if amount < 0 else ""
    return f"{sign}${abs(amount):,.0f}"


def total_monthly_premium(rows: list[dict[str, Any]]) -> float:
    return round(sum(_num(r.get("保費")) for r in rows), 0)


def svg_pie(
    slices: list[dict[str, Any]],
    *,
    label_key: str,
    value_key: str,
    size: int = 260,
    colors: list[str] | None = None,
    color_key: str | None = None,
    center_title: str = "",
    center_sub: str = "",
    legend_html: list[str] | None = None,
) -> str:
    palette = colors or [
        "#C5A028",
        "#1a1a2e",
        "#059669",
        "#2563EB",
        "#DC2626",
        "#7C3AED",
        "#EA580C",
        "#0891B2",
    ]
    data = []
    for s in slices:
        lab = str(s.get(label_key) or "")
        val = max(0.0, _num(s.get(value_key)))
        col = str(s.get(color_key) or "") if color_key else ""
        data.append((lab, val, col))
    data = [(lab, val, col) for lab, val, col in data if val > 0]
    if not data:
        data = [("尚未輸入", 1.0, "#9CA3AF")]
    total = sum(v for _, v, _ in data) or 1.0
    cx = cy = size / 2
    r = size * 0.40
    inner = size * 0.22
    paths: list[str] = []
    legend = list(legend_html or [])
    angle = -90.0

    for i, (lab, val, col) in enumerate(data):
        sweep = val / total * 360.0
        color = col or palette[i % len(palette)]
        if sweep >= 359.999:
            paths.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{color}" />')
        else:
            a0 = math.radians(angle)
            a1 = math.radians(angle + sweep)
            x0, y0 = cx + r * math.cos(a0), cy + r * math.sin(a0)
            x1, y1 = cx + r * math.cos(a1), cy + r * math.sin(a1)
            large = 1 if sweep > 180 else 0
            paths.append(
                f'<path d="M {cx} {cy} L {x0:.3f} {y0:.3f} '
                f'A {r} {r} 0 {large} 1 {x1:.3f} {y1:.3f} Z" fill="{color}" />'
            )
        if legend_html is None:
            pct = val / total * 100.0
            legend.append(
                f'<div style="display:flex;align-items:center;gap:8px;margin:4px 0;'
                f'font-size:13px;color:#374151;">'
                f'<span style="width:12px;height:12px;border-radius:2px;background:{color};'
                f'display:inline-block;"></span>'
                f'<span>{lab} · {format_hkd(val)}（{pct:.0f}%）</span></div>'
            )
        angle += sweep

    paths.append(f'<circle cx="{cx}" cy="{cy}" r="{inner}" fill="#FFFFFF" />')
    center = ""
    if center_title or center_sub:
        center = (
            f'<text x="{cx}" y="{cy - 6}" text-anchor="middle" '
            f'font-size="22" font-weight="700" fill="#111827">{center_title}</text>'
            f'<text x="{cx}" y="{cy + 16}" text-anchor="middle" '
            f'font-size="12" fill="#6B7280">{center_sub}</text>'
        )

    return (
        f'<div style="display:flex;flex-wrap:wrap;gap:16px;align-items:center;">'
        f'<svg width="{size}" height="{size}" viewBox="0 0 {size} {size}">'
        f'{"".join(paths)}{center}</svg>'
        f'<div>{"".join(legend)}</div></div>'
    )


def svg_pillar_status_pie(pillars: list[dict[str, Any]], *, size: int = 280) -> str:
    """Always-on 4-slice status pie — missing pillars stay red and visible."""
    summary = completeness_summary(pillars)
    legend = []
    for p in pillars:
        color = p["color"]
        detail = (
            f'{p["短名"]} · {p["status_label"]}'
            f'（已有 {format_hkd(p["已有保額"])}／建議 {format_hkd(p["建議保額"])}）'
        )
        legend.append(
            f'<div style="display:flex;align-items:flex-start;gap:8px;margin:6px 0;'
            f'font-size:13px;color:#374151;line-height:1.35;">'
            f'<span style="width:12px;height:12px;border-radius:2px;background:{color};'
            f'display:inline-block;margin-top:3px;flex-shrink:0;"></span>'
            f'<span>{detail}</span></div>'
        )
    return svg_pie(
        pillars,
        label_key="短名",
        value_key="weight",
        size=size,
        color_key="color",
        center_title=f'{summary["ready"]}/{summary["total"]}',
        center_sub="類已達標",
        legend_html=legend,
    )


def html_pillar_gap_bars(pillars: list[dict[str, Any]]) -> str:
    """Horizontal bars: filled = have, empty track = still need."""
    blocks = []
    for p in pillars:
        need = max(_num(p["建議保額"]), 1.0)
        have = _num(p["已有保額"])
        pct = min(100.0, have / need * 100.0)
        color = p["color"]
        blocks.append(
            f'<div style="margin:10px 0 14px 0;">'
            f'<div style="display:flex;justify-content:space-between;font-size:13px;'
            f'color:#374151;margin-bottom:4px;">'
            f'<strong>{p["短名"]}</strong>'
            f'<span>{p["status_label"]} · {format_hkd(have)} / {format_hkd(need)}</span>'
            f"</div>"
            f'<div style="background:#F3F4F6;border-radius:999px;height:14px;overflow:hidden;">'
            f'<div style="width:{pct:.1f}%;height:100%;background:{color};'
            f'border-radius:999px;"></div></div>'
            f"</div>"
        )
    return (
        '<div style="border:1px solid #E5E7EB;border-radius:12px;padding:14px 16px;'
        'background:#FFFDF8;">'
        '<div style="font-size:13px;color:#6B7280;margin-bottom:8px;">'
        "每條代表建議保額；色條係已有，灰色空白就係缺口。"
        f"</div>{''.join(blocks)}</div>"
    )
