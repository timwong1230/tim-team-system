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
    include_life: bool = False,
    medical_id: str | None = None,
    medical_level: str | None = None,
    medical_deductible: int | None = None,
    medical_annual_hkd: float | None = None,
    ci_id: str | None = None,
    ci_sa_usd: float | None = None,
    ci_pay_term: int | None = None,
    ci_annual_hkd: float | None = None,
    accident_id: str | None = None,
    accident_sa_hkd: float | None = None,
    accident_annual_hkd: float | None = None,
    life_id: str | None = None,
    life_sa_hkd: float | None = None,
    life_pay_term: int | None = None,
    life_annual_hkd: float | None = None,
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
            use_table = str(prod.get("premium_source") or "") == "table" and bool(
                prod.get("finance_plan_id")
            )
            if use_table:
                prem = medical_premium_hkd(
                    product_id=medical_id,
                    age=age,
                    gender=gender,
                    level=medical_level,
                    deductible=medical_deductible,
                )
                annual = float(prem.get("annual_hkd") or 0)
                level_label = str(prem.get("level") or prod.get("short") or "標準")
                ded_val = int(prem.get("deductible") or 0)
                if annual <= 0:
                    gaps.append(
                        f"醫療「{prod.get('short')}」呢個年齡／選項暫時查唔到保費。"
                    )
                else:
                    total_annual += annual
            else:
                annual = float(medical_annual_hkd or 0)
                level_label = str(
                    medical_level
                    or (prod.get("levels") or ["標準"])[0]
                    or prod.get("short")
                    or "標準"
                )
                ded_val = int(medical_deductible or 0)
                if annual <= 0:
                    gaps.append(
                        f"醫療「{prod.get('short')}」未接保費表——請手動輸入年保費（港元）。"
                    )
                else:
                    total_annual += annual
            cover = str(prod.get("cover_summary_default") or "每年保障額內全包")
            if medical_id == "vbooster" and ded_val == 0:
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
                    "premium_source": "table" if use_table else "manual",
                    "cover_summary": cover,
                    "term": prod.get("term_note") or "",
                    "meta_rows": [
                        ("保障級別", level_label),
                        (
                            "自付費",
                            "無自付費" if ded_val == 0 else format_hkd(ded_val),
                        ),
                        ("保障期", str(prod.get("term_note") or "—")),
                    ],
                    "highlights": list(prod.get("highlights") or []),
                    "options": {
                        "level": level_label,
                        "deductible": ded_val,
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
                    ],
                    "highlights": list(prod.get("highlights") or []),
                    "options": {"sa_hkd": sa},
                }
            )

    if include_life and life_id:
        prod = get_product("life", life_id)
        if not prod:
            gaps.append(f"搵唔到人壽產品：{life_id}")
        else:
            sa = float(
                life_sa_hkd
                if life_sa_hkd is not None
                else prod.get("default_sa_hkd")
                or 0
            )
            pay = int(life_pay_term or prod.get("default_pay_term") or 20)
            annual = float(life_annual_hkd or 0)
            if annual <= 0:
                gaps.append(
                    f"人壽「{prod.get('short')}」未有保費表——請手動輸入年保費（港元）。"
                )
            else:
                total_annual += annual
            sections.append(
                {
                    "category": "人壽保險",
                    "category_key": "life",
                    "product_id": life_id,
                    "product_name": prod.get("name"),
                    "short": prod.get("short"),
                    "premium_annual_hkd": annual,
                    "premium_display": f"{format_hkd(annual)}／年"
                    if annual
                    else "待輸入年保費",
                    "premium_ok": annual > 0,
                    "premium_source": "manual",
                    "cover_summary": f"保額 {format_hkd(sa)}" if sa else "保額待定",
                    "term": f"供款／平衡年期 {pay} 年；{prod.get('term_note') or ''}",
                    "meta_rows": [
                        ("保額", format_hkd(sa) if sa else "—"),
                        ("供款年期", f"{pay} 年"),
                        ("保障期", str(prod.get("term_note") or "—")),
                    ],
                    "highlights": list(prod.get("highlights") or []),
                    "options": {"sa_hkd": sa, "pay_term": pay},
                }
            )

    from tt_core.proposal_offers import attach_offer_to_section

    for s in sections:
        attach_offer_to_section(s)

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
    annual_hkd: float | None = None,
    purpose: str = "教育基金",
    fx: float = FX_DEFAULT,
    withdraw_start_year: int | None = None,
    withdraw_years: int | None = None,
    withdraw_usd: float | None = None,
    illustration: dict[str, Any] | None = None,
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

    # 盈聚：優先用官方 PDF 嘅年齡／性別／年供
    age_v = int(age)
    gender_v = str(gender)
    if saving_id == "yingju5" and illustration:
        meta = illustration.get("meta") or {}
        if meta.get("age") is not None:
            age_v = int(meta["age"])
        if meta.get("gender"):
            gender_v = str(meta["gender"])
        if illustration.get("annual_usd") is not None:
            annual_usd = float(illustration["annual_usd"])
        if illustration.get("has_withdrawal_scenario"):
            if illustration.get("withdraw_start_year") is not None:
                withdraw_start_year = int(illustration["withdraw_start_year"])
            if illustration.get("withdraw_years") is not None:
                withdraw_years = int(illustration["withdraw_years"])
            if illustration.get("withdraw_usd") is not None:
                withdraw_usd = float(illustration["withdraw_usd"])

    currency = str(prod.get("currency") or "USD").upper()
    pay_years = int(prod.get("pay_years") or 5)
    annual_u = 0.0
    if currency == "HKD" or str(prod.get("premium_source")) == "manual_hkd":
        annual_hkd_v = float(
            annual_hkd
            if annual_hkd is not None
            else prod.get("default_annual_hkd")
            or 0
        )
        if annual_hkd_v <= 0:
            gaps.append("請輸入年供金額（港元）。")
        premium_display = (
            f"{format_hkd(annual_hkd_v)}／年" if annual_hkd_v else "待輸入年保費"
        )
        premium_source = "manual_hkd"
        summary_prem = premium_display if annual_hkd_v else "待輸入"
        options: dict[str, Any] = {
            "annual_hkd": annual_hkd_v,
            "pay_years": pay_years,
            "currency": "HKD",
        }
        extract_note = str(prod.get("extract_note") or "按計劃條款安排年金／提取")
        illus = None
    else:
        annual_u = float(
            annual_usd if annual_usd is not None else prod.get("default_annual_usd") or 0
        )
        if annual_u <= 0:
            gaps.append("請輸入年供金額（美元）。")
        annual_hkd_v = round(annual_u * float(fx or FX_DEFAULT), 0)
        premium_display = (
            f"{format_usd(annual_u)}／年（約 {format_hkd(annual_hkd_v)}）"
            if annual_u
            else "待輸入年保費"
        )
        premium_source = "manual_usd"
        summary_prem = f"{format_usd(annual_u)}／年" if annual_u else "待輸入"
        options = {"annual_usd": annual_u, "pay_years": pay_years, "fx": fx}
        extract_note = "第 6 年起可按計劃提款（以條款為準）"
        illus = None

    if saving_id == "yingju5" and not illustration:
        gaps.append("請上載盈聚‧天下 II 官方利益說明 PDF，計劃書先會用準確數字。")

    total_hkd = round(float(annual_hkd_v) * pay_years, 0)
    highlights = list(prod.get("highlights") or [])
    goals = list(prod.get("goals") or [])
    cover = str(prod.get("cover_summary_default") or f"{pay_years} 年供；可滾存長線")
    angle: dict[str, Any] | None = None
    title = "儲蓄計劃書"
    purpose_label = str(purpose or "儲蓄計劃")

    if saving_id == "yingju5" and annual_u > 0 and illustration:
        from tt_core.yingju_angles import build_angle_story

        angle = build_angle_story(
            purpose_label,
            annual_usd=annual_u,
            age=age_v,
            fx=float(fx or FX_DEFAULT),
            withdraw_start_year=withdraw_start_year,
            withdraw_years=withdraw_years,
            withdraw_usd=withdraw_usd,
            illustration=illustration,
        )
        purpose_label = str(angle.get("purpose") or purpose_label)
        title = str(angle.get("title") or title)
        goals = list(angle.get("goals") or goals)
        highlights = list(angle.get("highlights") or highlights)
        cover = str(angle.get("tagline") or cover)
        m = angle.get("metrics") or {}
        illus = {
            "year6_sv_usd": m.get("year6_sv_usd"),
            "year6_sv_hkd": m.get("year6_sv_hkd"),
            "withdraw_usd": m.get("withdraw_usd"),
            "av_after_withdrawals_usd": m.get("av_after_withdrawals_usd"),
            "note": "官方利益說明數字（紅利非保證）",
            "source": "official_illustration",
        }
        start_y = int(m.get("withdraw_start_year") or 6)
        n_wd = int(m.get("withdraw_years") or 0)
        if n_wd and float(m.get("withdraw_usd") or 0) > 0:
            extract_note = (
                f"第 {start_y} 年起官方示意每年提款約 "
                f"{format_usd(float(m.get('withdraw_usd') or 0))}（共 {n_wd} 年）；"
                f"提款後戶口約 {format_usd(float(m.get('av_after_withdrawals_usd') or 0))}"
            )
        else:
            extract_note = "建議書無提款情景；第 6 年起可按條款安排提款"
        options["purpose"] = purpose_label
        options["withdraw_start_year"] = start_y
        options["withdraw_years"] = m.get("withdraw_years")
        options["withdraw_usd"] = m.get("withdraw_usd")
        options["illustration_source"] = "official_pdf"

    sections = [
        {
            "category": purpose_label,
            "category_key": "saving",
            "product_id": saving_id,
            "product_name": prod.get("name"),
            "short": prod.get("short"),
            "premium_annual_hkd": annual_hkd_v,
            "premium_display": premium_display,
            "premium_ok": float(annual_hkd_v or 0) > 0,
            "premium_source": premium_source,
            "cover_summary": cover,
            "term": str(prod.get("term_note") or ""),
            "meta_rows": [
                ("供款年期", f"{pay_years} 年"),
                ("總供款（未計折扣）", format_hkd(total_hkd)),
                ("提款安排", extract_note),
                ("保障期", str(prod.get("term_note") or "—")),
            ],
            "highlights": highlights,
            "goals": goals,
            "illustration": illus,
            "visual": (angle or {}).get("visual"),
            "angle_tagline": (angle or {}).get("tagline"),
            "angle_disclaimer": (angle or {}).get("disclaimer"),
            "options": options,
        }
    ]
    from tt_core.proposal_offers import attach_offer_to_section

    attach_offer_to_section(sections[0])
    return {
        "kind": "saving",
        "title": title,
        "client": {
            "name": str(client_name or "").strip() or "客戶",
            "age": age_v,
            "gender": gender_v,
            "occupation": str(occupation or "").strip(),
        },
        "sections": sections,
        "summary_rows": [],
        "skip_summary": True,
        "total_annual_hkd": annual_hkd_v,
        "gaps": gaps,
        "ready": float(annual_hkd_v or 0) > 0 and not gaps,
        "purpose": purpose_label,
        "illustration_ok": bool(illustration) if saving_id == "yingju5" else None,
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
        promo = s.get("promo") or {}
        if promo.get("detail"):
            lines.append(f"保費折扣：{promo.get('detail')}")
            if promo.get("first_year_display"):
                lines.append(str(promo["first_year_display"]))
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
            if str(k) not in ("保費", "產品", "年供", "參考來源", "報價")
        )
        promo = s.get("promo") or {}
        promo_html = ""
        if promo.get("detail"):
            fy = (
                f"<div class='promo-fy'>{_esc(promo.get('first_year_display'))}</div>"
                if promo.get("first_year_display")
                else ""
            )
            note = (
                f"<div class='promo-note'>{_esc(promo.get('note'))}</div>"
                if promo.get("note")
                else ""
            )
            promo_html = (
                "<div class='promo'>"
                f"<div class='glabel'>{_esc(promo.get('label') or '保費折扣')}"
                f" · {_esc(promo.get('quarter') or '')}</div>"
                f"<div class='promo-detail'>{_esc(promo.get('detail'))}</div>"
                f"{fy}{note}"
                "</div>"
            )
        visual = s.get("visual") or {}
        visual_html = ""
        if visual.get("steps") or visual.get("value_table"):
            cards = visual.get("cards") or []
            cards_html = "".join(
                "<div class='vcard'>"
                f"<span>{_esc(c.get('label'))}</span>"
                f"<strong>{_esc(c.get('value'))}</strong>"
                f"<em>{_esc(c.get('sub'))}</em>"
                "</div>"
                for c in cards
            )
            steps_html = "".join(
                f"<div class='vstep tone-{_esc(st.get('tone') or 'pay')}'>"
                f"<div class='vphase'>{_esc(st.get('phase'))}</div>"
                f"<div class='vtitle'>{_esc(st.get('title'))}</div>"
                f"<div class='vbody'>{_esc(st.get('body'))}</div>"
                "</div>"
                for st in visual.get("steps") or []
            )
            vtable = visual.get("value_table") or []
            vtable_html = ""
            if vtable:
                rows_html = "".join(
                    "<tr>"
                    f"<td>第 {_esc(r.get('policy_year'))} 年</td>"
                    f"<td>{_esc(r.get('age'))} 歲</td>"
                    f"<td>{_esc(format_usd(float(r.get('withdraw_usd') or 0))) if float(r.get('withdraw_usd') or 0) else '—'}</td>"
                    f"<td>{_esc(format_usd(float(r.get('av_end_usd') or 0)))}</td>"
                    f"<td>{_esc(r.get('note') or '')}</td>"
                    "</tr>"
                    for r in vtable
                )
                vtable_html = (
                    "<div class='vtable'>"
                    f"<div class='glabel'>{_esc(visual.get('value_table_caption') or '重點年份')}</div>"
                    "<table class='vt'>"
                    "<thead><tr><th>保單年度</th><th>年齡</th><th>提款</th>"
                    f"<th>{_esc(visual.get('value_table_caption') or '期末戶口')}</th>"
                    "<th>備註</th></tr></thead>"
                    f"<tbody>{rows_html}</tbody></table></div>"
                )
            visual_html = (
                "<div class='visual'>"
                f"<div class='glabel'>{_esc(visual.get('caption') or '時間線')}</div>"
                f"<div class='vcards'>{cards_html}</div>"
                f"<div class='vtrack'>{steps_html}</div>"
                f"{vtable_html}"
                "</div>"
            )
        tagline = s.get("angle_tagline") or ""
        tagline_html = (
            f"<div class='tagline'>{_esc(tagline)}</div>" if tagline else ""
        )
        goals = s.get("goals") or []
        goals_html = ""
        if goals:
            goals_html = (
                "<div class='goals'><div class='glabel'>目標</div><ul>"
                + "".join(f"<li>{_esc(g)}</li>" for g in goals)
                + "</ul></div>"
            )
        premium_cls = "ok" if s.get("premium_ok") else "warn"
        sections_html.append(
            f"""
<article class="sec">
  <header>
    <div class="cat">{_esc(s.get('category'))}</div>
    <h3>{_esc(s.get('product_name'))}</h3>
    {tagline_html}
    <div class="prem {premium_cls}">{_esc(s.get('premium_display'))}</div>
  </header>
  <div class="meta">{meta}</div>
  {visual_html}
  {promo_html}
  {goals_html}
  <div class="hl"><div class="glabel">計劃重點</div><ul>{bullets}</ul></div>
</article>
"""
        )

    summary_rows = proposal.get("summary_rows") or []
    skip_summary = bool(proposal.get("skip_summary")) or not summary_rows
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
    summary_html = ""
    if not skip_summary:
        summary_html = f"""
    <div class="sum">
      <div class="glabel">SUMMARY</div>
      <table>
        <thead><tr><th>保險類別</th><th>產品</th><th>年供保費</th><th>保障摘要</th></tr></thead>
        <tbody>{trs}</tbody>
      </table>
      <div class="total">合計年供約 {_esc(format_hkd(total))}</div>
    </div>"""

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
  .promo{{background:#FFF8E8;border:1px solid #E6D3A1;border-radius:12px;
    padding:10px 12px;margin:0 0 12px;
    font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;}}
  .promo-detail{{font-size:13px;line-height:1.45;color:#1C2430;white-space:pre-line;}}
  .promo-fy{{margin-top:6px;font-size:13px;font-weight:700;color:#1A2B4C;}}
  .promo-note{{margin-top:4px;font-size:11px;color:#6B7280;}}
  .tagline{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
    font-size:13px;color:#8A7340;margin:0 0 8px;font-weight:600;}}
  .visual{{margin:0 0 14px;}}
  .vcards{{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:8px 0 12px;}}
  .vcard{{background:#EEF2F7;border-radius:12px;padding:10px 12px;
    font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;}}
  .vcard span{{display:block;font-size:11px;color:#6B7280;margin-bottom:3px;}}
  .vcard strong{{display:block;font-size:16px;color:#1A2B4C;font-weight:700;}}
  .vcard em{{display:block;font-size:11px;color:#8A7340;font-style:normal;margin-top:2px;}}
  .vtrack{{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;}}
  .vstep{{border-radius:14px;padding:10px 8px;min-height:110px;
    font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
    border:1px solid #E4DFD4;background:#fff;position:relative;}}
  .vstep.tone-pay{{background:linear-gradient(180deg,#E8EEF7,#fff);}}
  .vstep.tone-pot{{background:linear-gradient(180deg,#FFF4D6,#fff);border-color:#E6D3A1;}}
  .vstep.tone-enjoy{{background:linear-gradient(180deg,#E7F6EE,#fff);border-color:#B7DCC6;}}
  .vstep.tone-roll{{background:linear-gradient(180deg,#F3EEF8,#fff);border-color:#D5C8E6;}}
  .vphase{{font-size:10px;letter-spacing:.06em;color:#6B7280;margin-bottom:4px;}}
  .vtitle{{font-size:14px;font-weight:700;color:#1A2B4C;margin-bottom:6px;}}
  .vbody{{font-size:12px;line-height:1.35;color:#374151;white-space:pre-line;}}
  .vtable{{margin-top:12px;}}
  table.vt{{width:100%;border-collapse:collapse;
    font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;font-size:12px;}}
  table.vt th{{text-align:left;padding:8px 6px;border-bottom:2px solid #1A2B4C;color:#1A2B4C;}}
  table.vt td{{padding:8px 6px;border-bottom:1px solid #E8E4DA;}}
  @media (max-width:640px){{
    .vtrack{{grid-template-columns:1fr 1fr;}}
  }}
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
    {summary_html}
    {gaps_html}
    <div class="foot">只供內部見客參考。保障、保費、折扣及分紅均以保險公司正式計劃書及條款為準；分紅／特別紅利非保證。</div>
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
