"""盈聚‧天下 II（5 年供）— 四個銷售角度文案 + 圖像時間線數字。"""

from __future__ import annotations

from typing import Any

# UI / builder 共用（順序即 selectbox 順序）
SELLING_ANGLES: list[str] = [
    "儲蓄錢包",
    "教育基金",
    "退休儲備",
    "醫療融資",
]

# 與 medical_finance 校準一致：Year5 SV ≈ annual×k5；level 提款 ≈ annual×0.35（= 總保費 7%）
_K5 = 2.9727
_WD_FRAC_OF_ANNUAL = 0.35


def angle_metrics(annual_usd: float, *, fx: float = 7.85) -> dict[str, Any]:
    a = max(float(annual_usd or 0), 0.0)
    year5_sv = round(a * _K5, 0)
    year6_wd = round(a * _WD_FRAC_OF_ANNUAL, 0)
    total_prem = round(a * 5, 0)
    return {
        "annual_usd": a,
        "annual_hkd": round(a * fx, 0),
        "total_prem_usd": total_prem,
        "total_prem_hkd": round(total_prem * fx, 0),
        "year5_sv_usd": year5_sv,
        "year5_sv_hkd": round(year5_sv * fx, 0),
        "year6_wd_usd": year6_wd,
        "year6_wd_hkd": round(year6_wd * fx, 0),
        "wd_pct_of_total": 7,
        "k5": _K5,
        "fx": fx,
    }


def _usd(n: float) -> str:
    return f"US${n:,.0f}"


def _hkd(n: float) -> str:
    return f"HK${n:,.0f}"


def build_angle_story(
    purpose: str,
    *,
    annual_usd: float,
    age: int,
    fx: float = 7.85,
) -> dict[str, Any]:
    """Return angle-specific title/goals/highlights + visual timeline payload."""
    m = angle_metrics(annual_usd, fx=fx)
    p = str(purpose or "").strip() or "儲蓄錢包"
    if p not in SELLING_ANGLES:
        # legacy labels
        if p in {"財富傳承", "其他儲蓄"}:
            p = "儲蓄錢包"
        elif p not in SELLING_ANGLES:
            p = "儲蓄錢包"

    y5u, y5h = m["year5_sv_usd"], m["year5_sv_hkd"]
    wdu, wdh = m["year6_wd_usd"], m["year6_wd_hkd"]
    au, ah = m["annual_usd"], m["annual_hkd"]

    common_flex = [
        "5 年供款完成後，第 6 年起可按計劃安排部份提款（示意約每年總保費 7%，非保證）",
        "亦可以唔提款，等保單價值繼續滾存",
        "分紅壽險：保證現金價值 + 歸原紅利 + 特別紅利（紅利非保證）",
        "保單貨幣轉換、保單分拆、紅利鎖定、保費假期等選項（以條款為準）",
    ]

    if p == "儲蓄錢包":
        title = "儲蓄錢包計劃書"
        tagline = "強制儲錢 · 砌第一桶金 · 第 6 年可以享受"
        goals = [
            "針對儲唔到錢／月光族：用保單結構幫你「逼自己」儲足 5 年",
            "5 年後擁有第一桶金，建立儲蓄習慣同安全感",
            "第 6 年起可提一筆犒賞自己（旅行／買嘢），亦可以繼續滾存",
        ]
        highlights = [
            f"每年約 {_usd(au)}（約 {_hkd(ah)}）· 供 5 年，養成強制儲蓄節奏",
            f"示意第 5 年名義退保價值約 {_usd(y5u)}（約 {_hkd(y5h)}）— 你嘅第一桶金",
            f"第 6 年起示意可提約 {_usd(wdu)}／年（約 {_hkd(wdh)}），旅行或犒賞自己都得",
            "提定唔提？你話事——唔提就繼續滾，滾大個「錢包」",
            *common_flex[2:],
        ]
        steps = [
            {
                "key": "pay",
                "phase": "第 1–5 年",
                "title": "強制儲錢",
                "body": f"每年 {_usd(au)}\n（約 {_hkd(ah)}）",
                "tone": "pay",
            },
            {
                "key": "pot",
                "phase": "第 5 年尾",
                "title": "第一桶金",
                "body": f"約 {_usd(y5u)}\n（約 {_hkd(y5h)}）",
                "tone": "pot",
            },
            {
                "key": "enjoy",
                "phase": "第 6 年起",
                "title": "可以享受",
                "body": f"示意可提約 {_usd(wdu)}／年\n旅行 · 買嘢 · 犒賞",
                "tone": "enjoy",
            },
            {
                "key": "roll",
                "phase": "或者…",
                "title": "繼續滾存",
                "body": "唔提都得\n錢包繼續長大",
                "tone": "roll",
            },
        ]
        cards = [
            {"label": "每年供款", "value": _usd(au), "sub": f"約 {_hkd(ah)}"},
            {"label": "5 年總供", "value": _usd(m["total_prem_usd"]), "sub": f"約 {_hkd(m['total_prem_hkd'])}"},
            {"label": "第 5 年桶金（示意）", "value": _usd(y5u), "sub": f"約 {_hkd(y5h)}"},
            {"label": "第 6 年可提（示意）", "value": _usd(wdu), "sub": "約總保費 7%／年"},
        ]
    elif p == "教育基金":
        # 假設受保人／子女而家 age；18 歲用錢 → 還有 max(0, 18-age) 年
        years_to_18 = max(0, 18 - int(age))
        title = "教育基金計劃書"
        tagline = "而家開始儲 · 將來學費有着落"
        goals = [
            "為子女教育提前鎖定供款節奏，避免臨急臨忙",
            "5 年供完之後，可按升學時間表彈性提款",
            "用唔晒可以繼續滾存，做後備教育／生活資金",
        ]
        highlights = [
            f"每年 {_usd(au)} × 5 年，建立教育專用戶口",
            f"示意第 5 年約 {_usd(y5u)}（約 {_hkd(y5h)}）作教育儲備基礎",
            f"第 6 年起示意每年可提約 {_usd(wdu)}，配合學費／遊學／生活費",
            (
                f"距離 18 歲仲有約 {years_to_18} 年——提早部署，見客時更有數講"
                if years_to_18 > 0
                else "已接近／到達升學階段——可聚焦提款節奏同滾存彈性"
            ),
            *common_flex[2:],
        ]
        steps = [
            {
                "key": "pay",
                "phase": "第 1–5 年",
                "title": "供教育金",
                "body": f"每年 {_usd(au)}",
                "tone": "pay",
            },
            {
                "key": "pot",
                "phase": "第 5 年尾",
                "title": "教育儲備",
                "body": f"約 {_usd(y5u)}",
                "tone": "pot",
            },
            {
                "key": "school",
                "phase": "升學期",
                "title": "按需要提",
                "body": f"示意約 {_usd(wdu)}／年\n學費／生活費",
                "tone": "enjoy",
            },
            {
                "key": "roll",
                "phase": "用唔晒",
                "title": "繼續滾",
                "body": "留低滾存\n做後備資金",
                "tone": "roll",
            },
        ]
        cards = [
            {"label": "每年供款", "value": _usd(au), "sub": f"約 {_hkd(ah)}"},
            {"label": "教育儲備（Yr5 示意）", "value": _usd(y5u), "sub": f"約 {_hkd(y5h)}"},
            {"label": "升學期可提（示意）", "value": _usd(wdu), "sub": "每年"},
            {
                "label": "距 18 歲",
                "value": f"{years_to_18} 年" if years_to_18 else "即期",
                "sub": f"而家 {int(age)} 歲",
            },
        ]
    elif p == "退休儲備":
        retire_age = 65
        years_to_retire = max(0, retire_age - int(age))
        title = "退休儲備計劃書"
        tagline = "5 年供 · 長線滾 · 退休期有現金流選項"
        goals = [
            "用短供款年期，換取長線滾存空間",
            "退休前後可選擇開始定期提款，補貼生活",
            "未提嘅部分繼續滾，彈性配合退休節奏",
        ]
        highlights = [
            f"5 年供 {_usd(au)}／年，之後進入長線滾存階段",
            f"示意第 5 年約 {_usd(y5u)}，作為退休儲備起點",
            f"第 6 年起示意可提約 {_usd(wdu)}／年；亦可延後至 {retire_age} 歲先提",
            f"距離 {retire_age} 歲約 {years_to_retire} 年——愈早開始，滾存時間愈長",
            *common_flex[2:],
        ]
        steps = [
            {
                "key": "pay",
                "phase": "第 1–5 年",
                "title": "供退休金",
                "body": f"每年 {_usd(au)}",
                "tone": "pay",
            },
            {
                "key": "grow",
                "phase": "供完之後",
                "title": "長線滾存",
                "body": f"起點約 {_usd(y5u)}\n繼續長大",
                "tone": "pot",
            },
            {
                "key": "retire",
                "phase": f"約 {retire_age} 歲",
                "title": "退休提款",
                "body": f"示意約 {_usd(wdu)}／年\n補貼生活",
                "tone": "enjoy",
            },
            {
                "key": "flex",
                "phase": "彈性",
                "title": "早提／晚提",
                "body": "第 6 年都可開始\n你話事",
                "tone": "roll",
            },
        ]
        cards = [
            {"label": "每年供款", "value": _usd(au), "sub": f"約 {_hkd(ah)}"},
            {"label": "Yr5 儲備（示意）", "value": _usd(y5u), "sub": f"約 {_hkd(y5h)}"},
            {"label": "可提現金流（示意）", "value": _usd(wdu), "sub": "每年"},
            {"label": f"距 {retire_age} 歲", "value": f"{years_to_retire} 年", "sub": f"而家 {int(age)} 歲"},
        ]
    else:  # 醫療融資
        title = "醫療融資計劃書"
        tagline = "5 年儲盈聚 · 第 6 年起提款繳醫保"
        goals = [
            "前期用收入交醫保，同時 5 年供盈聚預留彈藥",
            "第 6 年起以保單提款支持醫療保費，減輕長線現金流壓力",
            "提款金額可隨通脹調整需要；實際以正式利益說明為準",
        ]
        highlights = [
            f"儲蓄端：盈聚‧天下 II（5 年供），每年 {_usd(au)}",
            f"示意第 5 年戶口約 {_usd(y5u)}，之後進入提款支援期",
            f"第 6 年起示意可提約 {_usd(wdu)}／年，用作繳付醫療保費",
            "詳細醫保通脹試算可配合「醫療融資計算機」一齊見客",
            *common_flex[2:],
        ]
        steps = [
            {
                "key": "pay",
                "phase": "第 1–5 年",
                "title": "儲彈藥",
                "body": f"盈聚每年 {_usd(au)}\n同期交醫保",
                "tone": "pay",
            },
            {
                "key": "pot",
                "phase": "第 5 年尾",
                "title": "融資戶口",
                "body": f"約 {_usd(y5u)}",
                "tone": "pot",
            },
            {
                "key": "med",
                "phase": "第 6 年起",
                "title": "提款繳醫保",
                "body": f"示意約 {_usd(wdu)}／年\n支援醫療保費",
                "tone": "enjoy",
            },
            {
                "key": "long",
                "phase": "長線",
                "title": "繼續支援",
                "body": "戶口繼續滾\n對沖保費通脹",
                "tone": "roll",
            },
        ]
        cards = [
            {"label": "每年供盈聚", "value": _usd(au), "sub": f"約 {_hkd(ah)}"},
            {"label": "Yr5 戶口（示意）", "value": _usd(y5u), "sub": f"約 {_hkd(y5h)}"},
            {"label": "Yr6 起可提（示意）", "value": _usd(wdu), "sub": "支援醫保"},
            {"label": "策略", "value": "方案 2", "sub": "儲完先提"},
        ]

    return {
        "purpose": p,
        "title": title,
        "tagline": tagline,
        "goals": goals,
        "highlights": highlights,
        "metrics": m,
        "visual": {
            "type": "timeline",
            "caption": "圖像時間線（示意；非保證；以正式利益說明為準）",
            "steps": steps,
            "cards": cards,
        },
        "disclaimer": "數字按現行利益說明校準作示意，紅利／提款非保證，實際以保险公司正式計劃書為準。",
    }
