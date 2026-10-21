"""盈聚‧天下 II（5 年供）— 四個銷售角度文案、示意投影、圖像時間線。"""

from __future__ import annotations

from typing import Any

# UI / builder 共用（順序即 selectbox 順序）
SELLING_ANGLES: list[str] = [
    "儲蓄錢包",
    "教育基金",
    "退休儲備",
    "醫療融資",
]

# 與 medical_finance 校準一致
_K5 = 2.9727
_G = 0.1189
_WD_FRAC_OF_ANNUAL = 0.35  # = 總保費約 7%／年


def _usd(n: float) -> str:
    return f"US${float(n):,.0f}"


def _hkd(n: float) -> str:
    return f"HK${float(n):,.0f}"


def default_withdraw_usd(annual_usd: float) -> float:
    return round(max(float(annual_usd or 0), 0.0) * _WD_FRAC_OF_ANNUAL, 0)


def project_scenario(
    annual_usd: float,
    *,
    age: int = 30,
    withdraw_start_year: int = 6,
    withdraw_years: int = 4,
    withdraw_usd: float | None = None,
    fx: float = 7.85,
    extra_years_after: int = 2,
) -> dict[str, Any]:
    """示意投影：第 5 年用 k5；其後每年先增長再提款（與醫療融資校準同一套）。"""
    a = max(float(annual_usd or 0), 0.0)
    fx = float(fx or 7.85)
    total_prem = round(a * 5, 0)
    y5 = round(a * _K5, 0)
    wd = float(withdraw_usd) if withdraw_usd is not None else default_withdraw_usd(a)
    wd = max(wd, 0.0)
    start = max(6, int(withdraw_start_year or 6))
    n_wd = max(0, int(withdraw_years or 0))
    end_wd = start + n_wd - 1 if n_wd else start - 1
    horizon = max(6, end_wd + int(extra_years_after or 0), start)

    rows: list[dict[str, Any]] = []
    # Year 5 snapshot（內部用；計劃書主畫面改以第 6 年為主）
    av = float(y5)
    rows.append(
        {
            "policy_year": 5,
            "age": int(age) + 5,
            "withdraw_usd": 0.0,
            "av_end_usd": round(av, 0),
            "av_end_hkd": round(av * fx, 0),
            "note": "供款期結束",
        }
    )
    total_wd = 0.0
    year6_pre_wd = round(y5 * (1.0 + _G), 0)
    for yr in range(6, horizon + 1):
        av = av * (1.0 + _G)
        if yr == 6:
            year6_pre_wd = round(av, 0)
        took = 0.0
        if n_wd and start <= yr <= end_wd:
            took = min(wd, max(av, 0.0))
            av = av - took
            total_wd += took
        rows.append(
            {
                "policy_year": yr,
                "age": int(age) + yr,
                "withdraw_usd": round(took, 0),
                "av_end_usd": round(av, 0),
                "av_end_hkd": round(max(av, 0.0) * fx, 0),
                "note": ("提款年" if took > 0 else "滾存"),
            }
        )

    after_wd = next((r for r in rows if r["policy_year"] == end_wd), None) if n_wd else None
    return {
        "annual_usd": a,
        "annual_hkd": round(a * fx, 0),
        "total_prem_usd": total_prem,
        "total_prem_hkd": round(total_prem * fx, 0),
        "year5_sv_usd": y5,
        "year5_sv_hkd": round(y5 * fx, 0),
        # 第 6 年戶口用提款前數字，方便對照已繳保費／breakeven 講解
        "year6_sv_usd": float(year6_pre_wd),
        "year6_sv_hkd": round(float(year6_pre_wd) * fx, 0),
        "withdraw_start_year": start,
        "withdraw_years": n_wd,
        "withdraw_end_year": end_wd if n_wd else None,
        "withdraw_usd": round(wd, 0),
        "withdraw_hkd": round(wd * fx, 0),
        "total_withdrawn_usd": round(total_wd, 0),
        "total_withdrawn_hkd": round(total_wd * fx, 0),
        "av_after_withdrawals_usd": float(after_wd["av_end_usd"]) if after_wd else None,
        "av_after_withdrawals_hkd": float(after_wd["av_end_hkd"]) if after_wd else None,
        "final_av_usd": round(max(av, 0.0), 0),
        "final_av_hkd": round(max(av, 0.0) * fx, 0),
        "horizon_year": horizon,
        "rows": rows,
        "growth_rate": _G,
        "k5": _K5,
        "fx": fx,
        "breakeven_prem_usd": total_prem,  # 已繳總保費，方便對照第 6 年戶口
    }


def default_withdraw_start_year(purpose: str, age: int) -> int:
    p = str(purpose or "")
    if p == "教育基金":
        # 受保人約 18 歲開始用教育金；至少第 6 年
        return max(6, 18 - int(age))
    if p == "退休儲備":
        return max(6, 65 - int(age))
    return 6


def default_withdraw_years(purpose: str) -> int:
    p = str(purpose or "")
    if p == "教育基金":
        return 4
    if p == "退休儲備":
        return 10
    if p == "醫療融資":
        return 20
    return 1  # 儲蓄錢包：示範一年犒賞，亦可改


def build_angle_story(
    purpose: str,
    *,
    annual_usd: float,
    age: int,
    fx: float = 7.85,
    withdraw_start_year: int | None = None,
    withdraw_years: int | None = None,
    withdraw_usd: float | None = None,
    illustration: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return angle-specific title/goals/highlights + visual + value table.

    When ``illustration`` (parsed official PDF) is provided, all money figures
    come from that PDF — no calibrated projection.
    """
    p = str(purpose or "").strip() or "儲蓄錢包"
    if p in {"財富傳承", "其他儲蓄"} or p not in SELLING_ANGLES:
        p = "儲蓄錢包"

    official = bool(illustration)
    if official:
        from tt_core.yingju_proposal_parse import scenario_from_illustration

        meta = illustration.get("meta") or {}
        age_v = int(meta.get("age") if meta.get("age") is not None else age)
        scen = scenario_from_illustration(
            illustration, fx=float(fx or 7.85), age=age_v
        )
        start = int(scen.get("withdraw_start_year") or 6)
        n_wd = int(scen.get("withdraw_years") or 0)
        num_tag = "官方利益說明"
        src_caption = "數字來自上載嘅官方利益說明 PDF（紅利非保證）"
    else:
        start = (
            int(withdraw_start_year)
            if withdraw_start_year is not None
            else default_withdraw_start_year(p, int(age))
        )
        n_wd = (
            int(withdraw_years)
            if withdraw_years is not None
            else default_withdraw_years(p)
        )
        scen = project_scenario(
            annual_usd,
            age=int(age),
            withdraw_start_year=start,
            withdraw_years=n_wd,
            withdraw_usd=withdraw_usd,
            fx=float(fx or 7.85),
        )
        num_tag = "示意"
        src_caption = "示意數字（非保證；以正式利益說明為準）"

    age = int(scen.get("age") or age)
    au, ah = scen["annual_usd"], scen["annual_hkd"]
    y6u, y6h = scen["year6_sv_usd"], scen["year6_sv_hkd"]
    wdu, wdh = scen["withdraw_usd"], scen["withdraw_hkd"]
    prem_u = scen["total_prem_usd"]
    after_u = scen.get("av_after_withdrawals_usd")
    after_h = scen.get("av_after_withdrawals_hkd")
    end_wd = scen.get("withdraw_end_year")
    # Guard display helpers when SV missing
    y6u = float(y6u or 0)
    y6h = float(y6h or 0)

    common_flex = [
        "分紅壽險：保證現金價值 + 歸原紅利 + 特別紅利（紅利非保證）",
        "保單貨幣轉換、保單分拆、紅利鎖定、保費假期等選項（以條款為準）",
        "提款會影響其後戶口價值及身故權益；實際以保險公司正式利益說明為準",
    ]

    if official:
        value_table_u = list(scen.get("rows") or [])
    else:
        # 價值表：重點年份（第 6、提款起／止、視野末端）
        focus_years = {6, start}
        if end_wd:
            focus_years.add(int(end_wd))
        focus_years.add(int(scen["horizon_year"]))
        seen: set[int] = set()
        value_table_u = []
        for r in sorted(scen["rows"], key=lambda x: x["policy_year"]):
            yr = int(r["policy_year"])
            if yr in focus_years and yr not in seen and yr >= 6:
                value_table_u.append(r)
                seen.add(yr)

    if p == "儲蓄錢包":
        title = "儲蓄錢包計劃書"
        tagline = "五年供款 · 建立第一桶金"
        goals = [
            "針對儲蓄紀律較弱嘅客戶：以保單結構建立五年強制供款節奏",
            "供款期後形成第一桶金，作為中長線儲備基礎",
            "第 6 年起可選擇部份提款（犒賞／旅行），亦可繼續滾存",
        ]
        highlights = [
            f"每年 {_usd(au)}（約 {_hkd(ah)}）· 供款 5 年",
            f"第 6 年期末戶口（{num_tag}）約 {_usd(y6u)}（約 {_hkd(y6h)}）；對照已繳保費 {_usd(prem_u)}",
            f"第 {start} 年示範提款約 {_usd(wdu)}（約 {_hkd(wdh)}）",
            (
                f"提款後戶口（{num_tag}）約 {_usd(after_u)}（約 {_hkd(after_h)}）"
                if after_u is not None
                else "亦可選擇唔提款，戶口繼續滾存"
            ),
            *common_flex,
        ]
        steps = [
            {
                "key": "pay",
                "phase": "第 1–5 年",
                "title": "強制供款",
                "body": f"每年 {_usd(au)}\n（約 {_hkd(ah)}）",
                "tone": "pay",
            },
            {
                "key": "pot",
                "phase": "第 6 年",
                "title": "第一桶金",
                "body": f"戶口約 {_usd(y6u)}\n（對照已繳 {_usd(prem_u)}）",
                "tone": "pot",
            },
            {
                "key": "enjoy",
                "phase": f"第 {start} 年",
                "title": "可選擇提款",
                "body": f"{num_tag} {_usd(wdu)}\n旅行／犒賞",
                "tone": "enjoy",
            },
            {
                "key": "roll",
                "phase": "提款後",
                "title": "戶口尚餘",
                "body": (
                    f"約 {_usd(after_u)}\n繼續滾存"
                    if after_u is not None
                    else "可選擇唔提\n繼續滾存"
                ),
                "tone": "roll",
            },
        ]
        cards = [
            {"label": "每年供款", "value": _usd(au), "sub": f"約 {_hkd(ah)}"},
            {"label": "5 年總供", "value": _usd(prem_u), "sub": f"約 {_hkd(scen['total_prem_hkd'])}"},
            {"label": f"第 6 年戶口（{num_tag}）", "value": _usd(y6u), "sub": f"約 {_hkd(y6h)}"},
            {
                "label": f"第 {start} 年提款（{num_tag}）",
                "value": _usd(wdu),
                "sub": f"其後戶口約 {_usd(after_u) if after_u is not None else '—'}",
            },
        ]
    elif p == "教育基金":
        years_to_18 = max(0, 18 - int(age))
        title = "教育基金計劃書"
        tagline = "子女教育金規劃方案"
        goals = [
            "以五年供款建立教育儲備，配合升學時間表安排提款",
            "提款年期及金額可按學費需要調整",
            "未用之儲備可繼續滾存，作後備教育或生活資金",
        ]
        highlights = [
            f"每年 {_usd(au)} × 5 年，建立教育儲備",
            f"第 6 年期末戶口（{num_tag}）約 {_usd(y6u)}（約 {_hkd(y6h)}）",
            f"預計約第 {start} 年（受保人約 {int(age) + start} 歲）起，連續 {n_wd} 年提款",
            f"每年{num_tag}提款 {_usd(wdu)}（約 {_hkd(wdh)}）；{n_wd} 年合共約 {_usd(scen['total_withdrawn_usd'])}",
            (
                f"提款期結束後戶口尚餘（{num_tag}）約 {_usd(after_u)}（約 {_hkd(after_h)}）"
                if after_u is not None
                else "提款安排可按實際學費調整"
            ),
            *common_flex,
        ]
        steps = [
            {
                "key": "pay",
                "phase": "第 1–5 年",
                "title": "建立儲備",
                "body": f"每年 {_usd(au)}",
                "tone": "pay",
            },
            {
                "key": "pot",
                "phase": "第 6 年",
                "title": "儲備成形",
                "body": f"戶口約 {_usd(y6u)}",
                "tone": "pot",
            },
            {
                "key": "school",
                "phase": f"第 {start}–{end_wd} 年" if end_wd else f"第 {start} 年",
                "title": "教育提款期",
                "body": f"每年約 {_usd(wdu)}\n學費／生活費",
                "tone": "enjoy",
            },
            {
                "key": "roll",
                "phase": "提款期後",
                "title": "尚餘滾存",
                "body": (
                    f"約 {_usd(after_u)}\n後備資金"
                    if after_u is not None
                    else "可按需要調整"
                ),
                "tone": "roll",
            },
        ]
        cards = [
            {"label": "每年供款", "value": _usd(au), "sub": f"約 {_hkd(ah)}"},
            {"label": f"第 6 年戶口（{num_tag}）", "value": _usd(y6u), "sub": f"約 {_hkd(y6h)}"},
            {
                "label": f"提款期（第 {start} 年起）",
                "value": f"{n_wd} 年 × {_usd(wdu)}",
                "sub": f"合共約 {_usd(scen['total_withdrawn_usd'])}",
            },
            {
                "label": f"提款後尚餘（{num_tag}）",
                "value": _usd(after_u) if after_u is not None else "—",
                "sub": f"約 {_hkd(after_h)}" if after_h is not None else f"而家 {int(age)} 歲",
            },
        ]
    elif p == "退休儲備":
        retire_age = 65
        years_to_retire = max(0, retire_age - int(age))
        title = "退休儲備計劃書"
        tagline = "退休現金流規劃方案"
        goals = [
            "以較短供款年期，換取其後長線滾存空間",
            "退休前後可安排定期提款，補貼生活開支",
            "未提取部分繼續滾存，配合個人退休節奏",
        ]
        highlights = [
            f"5 年供 {_usd(au)}／年，其後進入滾存階段",
            f"第 6 年期末戶口（{num_tag}）約 {_usd(y6u)}（約 {_hkd(y6h)}）",
            f"預計約第 {start} 年（約 {int(age) + start} 歲）起，每年{num_tag}提款 {_usd(wdu)}",
            (
                f"示範提款 {n_wd} 年後，戶口尚餘（{num_tag}）約 {_usd(after_u)}"
                if after_u is not None
                else "提款開始年份可按退休計劃調整"
            ),
            f"距離 {retire_age} 歲約 {years_to_retire} 年",
            *common_flex,
        ]
        steps = [
            {
                "key": "pay",
                "phase": "第 1–5 年",
                "title": "供款期",
                "body": f"每年 {_usd(au)}",
                "tone": "pay",
            },
            {
                "key": "grow",
                "phase": "第 6 年",
                "title": "儲備成形",
                "body": f"戶口約 {_usd(y6u)}",
                "tone": "pot",
            },
            {
                "key": "retire",
                "phase": f"第 {start} 年起",
                "title": "退休提款",
                "body": f"每年約 {_usd(wdu)}\n補貼生活",
                "tone": "enjoy",
            },
            {
                "key": "flex",
                "phase": "提款期後",
                "title": "尚餘滾存",
                "body": (
                    f"約 {_usd(after_u)}" if after_u is not None else "可延後提款"
                ),
                "tone": "roll",
            },
        ]
        cards = [
            {"label": "每年供款", "value": _usd(au), "sub": f"約 {_hkd(ah)}"},
            {"label": f"第 6 年戶口（{num_tag}）", "value": _usd(y6u), "sub": f"約 {_hkd(y6h)}"},
            {"label": f"每年提款（{num_tag}）", "value": _usd(wdu), "sub": f"第 {start} 年起"},
            {
                "label": f"提款後尚餘（{num_tag}）",
                "value": _usd(after_u) if after_u is not None else "—",
                "sub": f"示範 {n_wd} 年提款",
            },
        ]
    else:  # 醫療融資
        title = "醫療融資計劃書"
        tagline = "醫療保費預留方案"
        goals = [
            "前期以收入繳付醫療保費，同時五年供盈聚預留資金",
            "第 6 年起可以保單提款支援醫療保費，減輕長線現金流壓力",
            "提款金額可按通脹及實際保費調整；詳情可配合醫療融資計算機",
        ]
        highlights = [
            f"儲蓄端：盈聚‧天下 II（5 年供），每年 {_usd(au)}",
            f"第 6 年期末戶口（{num_tag}）約 {_usd(y6u)}（約 {_hkd(y6h)}）",
            f"第 {start} 年起{num_tag}每年提款 {_usd(wdu)}，用作支援醫療保費",
            (
                f"示範 {n_wd} 年提款後，戶口尚餘（{num_tag}）約 {_usd(after_u)}"
                if after_u is not None
                else "詳細通脹試算請用「醫療融資計算機」"
            ),
            *common_flex,
        ]
        steps = [
            {
                "key": "pay",
                "phase": "第 1–5 年",
                "title": "預留資金",
                "body": f"盈聚每年 {_usd(au)}\n同期繳醫保",
                "tone": "pay",
            },
            {
                "key": "pot",
                "phase": "第 6 年",
                "title": "融資戶口",
                "body": f"約 {_usd(y6u)}",
                "tone": "pot",
            },
            {
                "key": "med",
                "phase": f"第 {start} 年起",
                "title": "提款繳醫保",
                "body": f"每年約 {_usd(wdu)}",
                "tone": "enjoy",
            },
            {
                "key": "long",
                "phase": "長線",
                "title": "戶口尚餘",
                "body": (
                    f"約 {_usd(after_u)}\n繼續支援"
                    if after_u is not None
                    else "可按通脹調整"
                ),
                "tone": "roll",
            },
        ]
        cards = [
            {"label": "每年供盈聚", "value": _usd(au), "sub": f"約 {_hkd(ah)}"},
            {"label": f"第 6 年戶口（{num_tag}）", "value": _usd(y6u), "sub": f"約 {_hkd(y6h)}"},
            {"label": f"每年提款（{num_tag}）", "value": _usd(wdu), "sub": "支援醫保"},
            {
                "label": f"提款後尚餘（{num_tag}）",
                "value": _usd(after_u) if after_u is not None else "—",
                "sub": f"示範 {n_wd} 年",
            },
        ]

    return {
        "purpose": p,
        "title": title,
        "tagline": tagline,
        "goals": goals,
        "highlights": highlights,
        "metrics": scen,
        "scenario": scen,
        "visual": {
            "type": "timeline",
            "caption": src_caption,
            "steps": steps,
            "cards": cards,
            "value_table": value_table_u,
            "value_table_caption": f"重點年份戶口（{num_tag}）",
        },
        "disclaimer": (
            (
                "數字直接取自上載嘅官方利益說明 PDF（當前假設紅利）；"
                "紅利／提款非保證；實際以保險公司正式計劃書及條款為準。"
            )
            if official
            else (
                "數字按現行利益說明校準模型作示意（第 5 年倍數及之後增長假設），"
                "紅利／提款非保證；實際以保險公司正式計劃書及條款為準。"
                "建議上載官方建議書以使用準確數字。"
            )
        ),
    }
