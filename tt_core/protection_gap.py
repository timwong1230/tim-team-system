"""保障缺口 — existing policies vs recommended cover for protection sales."""

from __future__ import annotations

from typing import Any

POLICY_TYPES = ["人壽保險", "危疾保險", "醫療保險", "意外保險", "其他"]

# Suggested cover multiples / defaults (HKD). Agents can override on the page.
# Life / CI / Accident keyed off annual income; Medical is a flat starting target.
DEFAULT_RULES = {
    "人壽保險": {"multiple_of_annual_income": 10.0, "floor": 1_000_000.0},
    "危疾保險": {"multiple_of_annual_income": 4.0, "floor": 500_000.0},
    "醫療保險": {"flat": 1_000_000.0},  # treat as target medical cover / room plan reference
    "意外保險": {"multiple_of_annual_income": 3.0, "floor": 500_000.0},
    "其他": {"flat": 0.0},
}

EMPTY_ROW = {
    "保單類型": "人壽保險",
    "保險公司": "",
    "保額": 0.0,
    "保費": 0.0,  # monthly premium HKD
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
    """Per-type totals: cover + premium."""
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
    """Slices for current sum-insured mix (skip zeros)."""
    agg = aggregate(rows)
    return [
        {"類型": t, "保額": round(v["cover"], 0)}
        for t, v in agg.items()
        if v["cover"] > 0
    ]


def pie_gap_vs_covered(gap_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Single overview pie: total covered vs total remaining gap across
    the four main protection types (excludes 其他 unless targeted).
    """
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
) -> str:
    """Render a simple SVG pie chart (no extra Python deps)."""
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
    data = [(str(s.get(label_key) or ""), max(0.0, _num(s.get(value_key)))) for s in slices]
    data = [(lab, val) for lab, val in data if val > 0]
    if not data:
        data = [("尚未輸入", 1.0)]
    total = sum(v for _, v in data) or 1.0
    cx = cy = size / 2
    r = size * 0.38
    paths = []
    legend = []
    angle = -90.0  # start at top
    import math

    for i, (lab, val) in enumerate(data):
        sweep = val / total * 360.0
        color = palette[i % len(palette)]
        # Full circle special-case
        if sweep >= 359.999:
            paths.append(
                f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{color}" />'
            )
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
        pct = val / total * 100.0
        legend.append(
            f'<div style="display:flex;align-items:center;gap:8px;margin:4px 0;'
            f'font-size:13px;color:#374151;">'
            f'<span style="width:12px;height:12px;border-radius:2px;background:{color};'
            f'display:inline-block;"></span>'
            f'<span>{lab} · {format_hkd(val)}（{pct:.0f}%）</span></div>'
        )
        angle += sweep

    return (
        f'<div style="display:flex;flex-wrap:wrap;gap:16px;align-items:center;">'
        f'<svg width="{size}" height="{size}" viewBox="0 0 {size} {size}">'
        f'{"".join(paths)}</svg>'
        f'<div>{"".join(legend)}</div></div>'
    )
