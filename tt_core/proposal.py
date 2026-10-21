"""客戶計劃書 — Full Protection / Saving Plan builder."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent / "data_files"
CATALOG_PATH = DATA_DIR / "proposal_catalog.json"
FX_DEFAULT = 7.85


@lru_cache(maxsize=1)
def load_catalog() -> dict[str, Any]:
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def missing_data_notes() -> list[str]:
    return list(load_catalog().get("missing_data_notes") or [])


def plan_types() -> list[dict[str, Any]]:
    return list(load_catalog().get("plan_types") or [])


def products_in(category: str) -> list[dict[str, Any]]:
    return list(load_catalog().get(category) or [])


def get_product(category: str, product_id: str) -> dict[str, Any] | None:
    for p in products_in(category):
        if str(p.get("id")) == str(product_id):
            return p
    return None


def medical_premium_hkd(
    *,
    product_id: str,
    age: int,
    gender: str,
    level: str | None = None,
    deductible: int | None = None,
) -> dict[str, Any]:
    """Look up medical annual premium from finance tables."""
    from tt_core import medical_finance as mf

    prod = get_product("medical", product_id) or {}
    plan_id = str(prod.get("finance_plan_id") or product_id)
    meta = mf.get_plan(plan_id)
    lv = level or meta.get("default_level")
    ded = meta.get("default_deductible") if deductible is None else deductible
    annual = float(
        mf.medical_annual_hkd(
            int(age),
            str(gender),
            plan_id=plan_id,
            level=lv,
            deductible=int(ded or 0),
        )
        or 0
    )
    return {
        "ok": annual > 0,
        "annual_hkd": round(annual, 0),
        "monthly_hkd": round(annual / 12.0, 2) if annual else 0,
        "source": "table",
        "level": lv,
        "deductible": int(ded or 0),
        "label": mf.plan_label(plan_id, level=lv, deductible=int(ded or 0)),
    }


def format_hkd(amount: float) -> str:
    try:
        v = float(amount or 0)
    except Exception:
        return "HK$0"
    return f"HK${v:,.0f}"


def format_usd(amount: float) -> str:
    try:
        v = float(amount or 0)
    except Exception:
        return "US$0"
    return f"US${v:,.0f}"


def sa_hkd_from_usd(usd: float, *, fx: float = FX_DEFAULT) -> float:
    return round(float(usd or 0) * float(fx or FX_DEFAULT), 0)


def build_protection_proposal(
    *,
    client_name: str,
    age: int,
    gender: str,
    occupation: str = "",
    include_medical: bool = True,
    include_ci: bool = True,
    include_accident: bool = True,
    medical_id: str | None = None,
    medical_level: str | None = None,
    medical_deductible: int | None = None,
    ci_id: str | None = None,
    ci_sa_usd: float | None = None,
    ci_pay_term: int | None = None,
    ci_annual_hkd: float | None = None,
    accident_id: str | None = None,
    accident_sa_hkd: float | None = None,
    accident_annual_hkd: float | None = None,
    fx: float = FX_DEFAULT,
) -> dict[str, Any]:
    """Assemble a Full Protection proposal payload."""
    sections: list[dict[str, Any]] = []
    gaps: list[str] = []
    total_annual = 0.0

    if include_medical and medical_id:
        prod = get_product("medical", medical_id)
        if not prod:
            gaps.append(f"搵唔到醫療產品：{medical_id}")
        else:
            prem = medical_premium_hkd(
                product_id=medical_id,
                age=age,
                gender=gender,
                level=medical_level,
                deductible=medical_deductible,
            )
            annual = float(prem.get("annual_hkd") or 0)
            if annual <= 0:
                gaps.append(f"醫療「{prod.get('short')}」呢個年齡／選項暫時查唔到保費。")
            else:
                total_annual += annual
            cover = str(prod.get("cover_summary_default") or "每年保障額內全包")
            if medical_id == "vbooster" and int(prem.get("deductible") or 0) == 0:
                cover = "每年約 800 萬全數保障"
            sections.append(
                {
                    "category": "醫療保險",
                    "category_key": "medical",
                    "product_id": medical_id,
                    "product_name": prod.get("name"),
                    "short": prod.get("short"),
                    "premium_annual_hkd": annual,
                    "premium_display": f"{format_hkd(annual)}／年"
                    + (
                        f"（約 {format_hkd(annual / 12)}／月）"
                        if annual
                        else "（待輸入）"
                    ),
                    "premium_ok": annual > 0,
                    "premium_source": "table",
                    "cover_summary": cover,
                    "term": prod.get("term_note") or "",
                    "meta_rows": [
                        (
                            "保障級別",
                            str(prem.get("level") or prod.get("short") or "標準"),
                        ),
                        (
                            "自付費",
                            "無自付費"
                            if int(prem.get("deductible") or 0) == 0
                            else format_hkd(prem.get("deductible") or 0),
                        ),
                        ("保障期", str(prod.get("term_note") or "—")),
                        ("參考來源", "系統保費表"),
                    ],
                    "highlights": list(prod.get("highlights") or []),
                    "options": {
                        "level": prem.get("level"),
                        "deductible": prem.get("deductible"),
                    },
                }
            )

    if include_ci and ci_id:
        prod = get_product("critical_illness", ci_id)
        if not prod:
            gaps.append(f"搵唔到危疾產品：{ci_id}")
        else:
            sa = float(ci_sa_usd if ci_sa_usd is not None else prod.get("default_sa_usd") or 0)
            pay = int(ci_pay_term or prod.get("default_pay_term") or 20)
            annual = float(ci_annual_hkd or 0)
            if annual <= 0:
                gaps.append(
                    f"危疾「{prod.get('short')}」未有保費表——請手動輸入年保費（港元）。"
                )
            else:
                total_annual += annual
            sa_hkd = sa_hkd_from_usd(sa, fx=fx)
            sections.append(
                {
                    "category": "危疾保險",
                    "category_key": "critical_illness",
                    "product_id": ci_id,
                    "product_name": prod.get("name"),
                    "short": prod.get("short"),
                    "premium_annual_hkd": annual,
                    "premium_display": f"{format_hkd(annual)}／年"
                    if annual
                    else "待輸入年保費",
                    "premium_ok": annual > 0,
                    "premium_source": "manual",
                    "cover_summary": f"保額 {format_usd(sa)}",
                    "term": f"供款 {pay} 年；{prod.get('term_note') or ''}",
                    "meta_rows": [
                        ("供款年期", f"{pay} 年"),
                        ("保額", f"{format_usd(sa)}"),
                        ("約合港元", format_hkd(sa_hkd)),
                        ("保障期", str(prod.get("term_note") or "—")),
                    ],
                    "highlights": list(prod.get("highlights") or []),
                    "options": {"sa_usd": sa, "pay_term": pay, "fx": fx},
                }
            )

    if include_accident and accident_id:
        prod = get_product("accident", accident_id)
        if not prod:
            gaps.append(f"搵唔到意外產品：{accident_id}")
        else:
            sa = float(
                accident_sa_hkd
                if accident_sa_hkd is not None
                else prod.get("default_sa_hkd")
                or 0
            )
            annual = float(accident_annual_hkd or 0)
            if annual <= 0:
                gaps.append(
                    f"意外「{prod.get('short')}」未有保費表——請手動輸入年保費（港元）。"
                )
            else:
                total_annual += annual
            sections.append(
                {
                    "category": "意外保險",
                    "category_key": "accident",
                    "product_id": accident_id,
                    "product_name": prod.get("name"),
                    "short": prod.get("short"),
                    "premium_annual_hkd": annual,
                    "premium_display": f"{format_hkd(annual)}／年"
                    + (f"（約 {format_hkd(annual / 12)}／月）" if annual else ""),
                    "premium_ok": annual > 0,
                    "premium_source": "manual",
                    "cover_summary": f"保障額 {format_hkd(sa)}" if sa else "保障額待定",
                    "term": str(prod.get("term_note") or ""),
                    "meta_rows": [
                        ("保障額", format_hkd(sa) if sa else "—"),
                        ("保障期", str(prod.get("term_note") or "—")),
                        ("形式", "可附於主保單／獨立（以條款為準）"),
                        ("報價", "見客時以正式報價為準"),
                    ],
                    "highlights": list(prod.get("highlights") or []),
                    "options": {"sa_hkd": sa},
                }
            )

    summary_rows = []
    for s in sections:
        annual = float(s.get("premium_annual_hkd") or 0)
        summary_rows.append(
            {
                "保險類別": s["category"],
                "產品名稱": s.get("short") or s.get("product_name"),
                "年供保費": f"{format_hkd(annual)}／年" if annual else "待輸入",
                "保障摘要": s.get("cover_summary"),
                "供款／年期": s.get("term"),
            }
        )

    return {
        "kind": "full_protection",
        "title": "全面保障計劃書",
        "client": {
            "name": str(client_name or "").strip() or "客戶",
            "age": int(age),
            "gender": str(gender),
            "occupation": str(occupation or "").strip(),
        },
        "sections": sections,
        "summary_rows": summary_rows,
        "total_annual_hkd": round(total_annual, 0),
        "gaps": gaps,
        "ready": bool(sections) and not gaps,
    }


def build_saving_proposal(
    *,
    client_name: str,
    age: int,
    gender: str,
    occupation: str = "",
    saving_id: str = "yingju5",
    annual_usd: float | None = None,
    purpose: str = "教育基金",
    fx: float = FX_DEFAULT,
) -> dict[str, Any]:
    prod = get_product("saving", saving_id)
    gaps: list[str] = []
    if not prod:
        return {
            "kind": "saving",
            "title": "儲蓄計劃書",
            "client": {
                "name": str(client_name or "").strip() or "客戶",
                "age": int(age),
                "gender": str(gender),
                "occupation": str(occupation or "").strip(),
            },
            "sections": [],
            "summary_rows": [],
            "total_annual_hkd": 0,
            "gaps": [f"搵唔到儲蓄產品：{saving_id}"],
            "ready": False,
        }

    annual_u = float(
        annual_usd if annual_usd is not None else prod.get("default_annual_usd") or 0
    )
    if annual_u <= 0:
        gaps.append("請輸入年供金額（美元）。")
    pay_years = int(prod.get("pay_years") or 5)
    annual_hkd = round(annual_u * float(fx or FX_DEFAULT), 0)
    total_hkd = round(annual_hkd * pay_years, 0)

    # Illustrative CV multiple from yingju calibration (non-guaranteed)
    illus = None
    try:
        from tt_core.medical_finance import load_calibration

        cal = load_calibration()
        k5 = float(cal.get("k5_sv_per_annual_prem") or 0)
        if k5 > 0 and annual_u > 0:
            year5_sv = round(annual_u * k5, 0)
            illus = {
                "year5_sv_usd": year5_sv,
                "year5_sv_hkd": round(year5_sv * fx, 0),
                "note": "示意：第 5 年名義退保價值約數（非保證；以正式計劃書為準）",
            }
    except Exception:
        illus = None

    highlights = list(prod.get("highlights") or [])
    goals = list(prod.get("goals") or [])
    sections = [
        {
            "category": purpose or "儲蓄計劃",
            "category_key": "saving",
            "product_id": saving_id,
            "product_name": prod.get("name"),
            "short": prod.get("short"),
            "premium_annual_hkd": annual_hkd,
            "premium_display": f"{format_usd(annual_u)}／年（約 {format_hkd(annual_hkd)}）",
            "premium_ok": annual_u > 0,
            "premium_source": "manual_usd",
            "cover_summary": f"{pay_years} 年供；可滾存長線",
            "term": str(prod.get("term_note") or ""),
            "meta_rows": [
                ("供款年期", f"{pay_years} 年"),
                ("總供款（未計折扣）", format_hkd(total_hkd)),
                ("提取", "第 6 年起可按計劃提款（以條款為準）"),
                ("保障期", str(prod.get("term_note") or "—")),
            ],
            "highlights": highlights,
            "goals": goals,
            "illustration": illus,
            "options": {"annual_usd": annual_u, "pay_years": pay_years, "fx": fx},
        }
    ]
    summary_rows = [
        {
            "保險類別": purpose or "儲蓄",
            "產品名稱": prod.get("short") or prod.get("name"),
            "年供保費": f"{format_usd(annual_u)}／年"
            if annual_u
            else "待輸入",
            "保障摘要": sections[0]["cover_summary"],
            "供款／年期": f"{pay_years} 年",
        }
    ]
    return {
        "kind": "saving",
        "title": "儲蓄計劃書",
        "client": {
            "name": str(client_name or "").strip() or "客戶",
            "age": int(age),
            "gender": str(gender),
            "occupation": str(occupation or "").strip(),
        },
        "sections": sections,
        "summary_rows": summary_rows,
        "total_annual_hkd": annual_hkd,
        "gaps": gaps,
        "ready": annual_u > 0 and not gaps,
        "purpose": purpose,
    }


def proposal_whatsapp(proposal: dict[str, Any]) -> str:
    client = proposal.get("client") or {}
    name = client.get("name") or "客戶"
    lines = [
        f"*{name} · {proposal.get('title') or '計劃書'}*",
        f"年齡 {client.get('age')}／{client.get('gender')}"
        + (f"／{client.get('occupation')}" if client.get("occupation") else ""),
        "",
    ]
    for s in proposal.get("sections") or []:
        lines.append(f"*{s.get('category')}*")
        lines.append(f"產品：{s.get('product_name')}")
        lines.append(f"保費：{s.get('premium_display')}")
        if s.get("cover_summary"):
            lines.append(f"保障：{s.get('cover_summary')}")
        lines.append("")
    total = float(proposal.get("total_annual_hkd") or 0)
    if total > 0:
        lines.append(f"*合計年供約 {format_hkd(total)}*")
    lines.append("_細節以正式計劃書／條款為準；分紅非保證。_")
    return "\n".join(lines).strip()


def html_preview(proposal: dict[str, Any]) -> str:
    """In-app HTML preview — professional navy/gold, not template clone."""
    client = proposal.get("client") or {}
    name = _esc(client.get("name") or "客戶")
    title = _esc(proposal.get("title") or "計劃書")
    occ = _esc(client.get("occupation") or "—")
    sections_html = []
    for s in proposal.get("sections") or []:
        bullets = "".join(
            f"<li>{_esc(h)}</li>" for h in (s.get("highlights") or [])
        )
        meta = "".join(
            f"<div class='kv'><span>{_esc(k)}</span><strong>{_esc(v)}</strong></div>"
            for k, v in (s.get("meta_rows") or [])
            if str(k) not in ("保費", "產品", "年供")
        )
        goals = s.get("goals") or []
        goals_html = ""
        if goals:
            goals_html = (
                "<div class='goals'><div class='glabel'>目標</div><ul>"
                + "".join(f"<li>{_esc(g)}</li>" for g in goals)
                + "</ul></div>"
            )
        illus = s.get("illustration") or {}
        illus_html = ""
        if illus:
            illus_html = (
                f"<div class='illus'>{_esc(illus.get('note'))}："
                f"約 {_esc(format_usd(illus.get('year5_sv_usd') or 0))} "
                f"（≈ {_esc(format_hkd(illus.get('year5_sv_hkd') or 0))}）</div>"
            )
        premium_cls = "ok" if s.get("premium_ok") else "warn"
        sections_html.append(
            f"""
<article class="sec">
  <header>
    <div class="cat">{_esc(s.get('category'))}</div>
    <h3>{_esc(s.get('product_name'))}</h3>
    <div class="prem {premium_cls}">{_esc(s.get('premium_display'))}</div>
  </header>
  <div class="meta">{meta}</div>
  {goals_html}
  <div class="hl"><div class="glabel">計劃內容</div><ul>{bullets}</ul></div>
  {illus_html}
</article>
"""
        )

    summary_rows = proposal.get("summary_rows") or []
    trs = "".join(
        "<tr>"
        f"<td>{_esc(r.get('保險類別'))}</td>"
        f"<td>{_esc(r.get('產品名稱'))}</td>"
        f"<td>{_esc(r.get('年供保費'))}</td>"
        f"<td>{_esc(r.get('保障摘要'))}</td>"
        "</tr>"
        for r in summary_rows
    )
    total = float(proposal.get("total_annual_hkd") or 0)
    gaps = proposal.get("gaps") or []
    gaps_html = ""
    if gaps:
        gaps_html = (
            "<div class='gaps'><strong>待補資料</strong><ul>"
            + "".join(f"<li>{_esc(g)}</li>" for g in gaps)
            + "</ul></div>"
        )

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  html,body{{margin:0;padding:0;background:transparent;
    font-family:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif;}}
  .sheet{{
    background:linear-gradient(165deg,#0F1B2D 0%,#1A2B4C 42%,#243656 100%);
    color:#F4F1EA;border-radius:18px;overflow:hidden;
    box-shadow:0 18px 40px rgba(15,27,45,.28);
  }}
  .hero{{padding:28px 24px 22px;border-bottom:1px solid rgba(212,175,55,.35);}}
  .eyebrow{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
    font-size:11px;letter-spacing:.16em;text-transform:uppercase;color:#D4AF37;}}
  .hero h1{{margin:10px 0 6px;font-size:34px;font-weight:600;letter-spacing:-.02em;}}
  .hero .sub{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
    font-size:14px;color:rgba(244,241,234,.78);line-height:1.5;}}
  .body{{background:#F7F4EE;color:#1C2430;padding:18px 16px 22px;}}
  .sec{{
    background:#fff;border:1px solid #E4DFD4;border-radius:14px;
    padding:16px 16px 14px;margin:0 0 14px;
  }}
  .cat{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
    font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:#8A7340;}}
  .sec h3{{margin:6px 0 8px;font-size:20px;font-weight:600;}}
  .prem{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
    font-size:15px;font-weight:700;margin-bottom:10px;}}
  .prem.ok{{color:#1A2B4C;}}
  .prem.warn{{color:#B45309;}}
  .meta{{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:12px;}}
  .kv{{background:#F7F4EE;border-radius:10px;padding:8px 10px;
    font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;font-size:12px;}}
  .kv span{{display:block;color:#6B7280;margin-bottom:2px;}}
  .kv strong{{color:#1C2430;font-weight:600;}}
  .glabel{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
    font-size:12px;font-weight:700;color:#5B4A28;margin-bottom:4px;}}
  ul{{margin:0;padding-left:18px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
    font-size:13px;line-height:1.45;color:#374151;}}
  .goals{{margin-bottom:10px;}}
  .illus{{margin-top:10px;padding:10px;border-radius:10px;background:#EEF2F7;
    font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;font-size:12px;color:#334155;}}
  .sum{{background:#fff;border:1px solid #E4DFD4;border-radius:14px;padding:14px;overflow:auto;}}
  table{{width:100%;border-collapse:collapse;table-layout:fixed;
    font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;font-size:12px;}}
  th{{text-align:left;padding:10px 8px;border-bottom:2px solid #1A2B4C;color:#1A2B4C;
    white-space:nowrap;}}
  td{{padding:10px 8px;border-bottom:1px solid #E8E4DA;vertical-align:top;
    word-break:keep-all;overflow-wrap:anywhere;line-height:1.45;}}
  td:nth-child(1){{width:18%;}}
  td:nth-child(2){{width:22%;}}
  td:nth-child(3){{width:22%;}}
  td:nth-child(4){{width:38%;}}
  .total{{margin-top:10px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
    font-size:16px;font-weight:700;color:#1A2B4C;}}
  .gaps{{margin-top:12px;padding:12px;border-radius:12px;background:#FFF7ED;border:1px solid #FDBA74;
    font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;font-size:13px;color:#9A3412;}}
  .foot{{margin-top:12px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
    font-size:11px;color:#6B7280;line-height:1.4;}}
</style></head><body>
<div class="sheet">
  <div class="hero">
    <div class="eyebrow">TIM TEAM · Proposal</div>
    <h1>{name}</h1>
    <div class="sub">{title}<br>
      { _esc(client.get('age')) } 歲 · {_esc(client.get('gender'))} · 職業 {occ}
    </div>
  </div>
  <div class="body">
    {''.join(sections_html) or '<p>尚未選擇產品。</p>'}
    <div class="sum">
      <div class="glabel">SUMMARY</div>
      <table>
        <thead><tr><th>保險類別</th><th>產品</th><th>年供保費</th><th>保障摘要</th></tr></thead>
        <tbody>{trs}</tbody>
      </table>
      <div class="total">合計年供約 { _esc(format_hkd(total)) }</div>
    </div>
    {gaps_html}
    <div class="foot">本計劃書由 TIM TEAM M+2 產生，只供內部見客參考。保障、保費、折扣及分紅均以保险公司正式計劃書及條款為準；分紅／特別紅利非保證。</div>
  </div>
</div>
</body></html>"""


def _esc(value: Any) -> str:
    s = str(value if value is not None else "")
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
