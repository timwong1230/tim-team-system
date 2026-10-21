"""Premium Financing (PFin) calculator for FWD 智盈匯聚 (優越版) V.

Formulas and bank / illustration snapshots are rewritten from the public
pfin-v.ai.studio client bundle (illustrative only — not a guarantee).
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent / "data_files"
BANKS_JSON = DATA_DIR / "pfin_banks.json"
ILLUSTRATION_JSON = DATA_DIR / "pfin_icon_v_illustration.json"

FX_DEFAULT = 7.85
DAY1_CV_RATIO = 0.82
BASE_PREMIUM_USD = 400_000.0


@lru_cache(maxsize=1)
def _banks_payload() -> dict[str, Any]:
    return json.loads(BANKS_JSON.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _illustration_payload() -> dict[str, Any]:
    return json.loads(ILLUSTRATION_JSON.read_text(encoding="utf-8"))


def list_banks() -> list[dict[str, Any]]:
    return list(_banks_payload().get("banks") or [])


def get_bank(bank_id: str) -> dict[str, Any] | None:
    for b in list_banks():
        if b.get("id") == bank_id:
            return b
    return None


def banks_disclaimer() -> str:
    return str(_banks_payload().get("disclaimer") or "")


def illustration_meta() -> dict[str, Any]:
    p = _illustration_payload()
    return {
        "product": p.get("product"),
        "product_en": p.get("product_en"),
        "base_premium_usd": float(p.get("base_premium_usd") or BASE_PREMIUM_USD),
        "base_issue_age": int(p.get("base_issue_age") or 22),
        "fx_usd_hkd": float(p.get("fx_usd_hkd") or FX_DEFAULT),
        "day1_guaranteed_cv_ratio": float(
            p.get("day1_guaranteed_cv_ratio") or DAY1_CV_RATIO
        ),
        "source_note": p.get("source_note"),
    }


def promo_discount_rate(premium_usd: float) -> float:
    """Company promo tier on single-pay premium (from public SPA)."""
    e = float(premium_usd or 0)
    if e < 200_000:
        return 0.04
    if e < 500_000:
        return 0.06
    return 0.08


def levy_usd(premium_usd: float, fx: float = FX_DEFAULT) -> float:
    """Levy capped at HKD 100 equivalent (public SPA: min(prem*0.1%, 100/FX))."""
    fx = float(fx or FX_DEFAULT)
    return min(float(premium_usd or 0) * 0.001, 100.0 / fx)


def irr(cashflows: list[float], guess: float = 0.05) -> float:
    """Annual IRR for a cashflow series (year 0…n). Returns 0 if undefined."""
    if not cashflows or len(cashflows) < 2:
        return 0.0
    if not any(c > 0 for c in cashflows) or not any(c < 0 for c in cashflows):
        return 0.0
    if sum(cashflows) <= 0:
        return 0.0

    def npv(rate: float) -> float:
        total = 0.0
        for i, c in enumerate(cashflows):
            total += c / ((1.0 + rate) ** i)
        return total

    # Newton
    r = float(guess)
    for _ in range(40):
        f = npv(r)
        # derivative
        df = 0.0
        for i, c in enumerate(cashflows):
            if i == 0:
                continue
            df -= i * c / ((1.0 + r) ** (i + 1))
        if abs(df) < 1e-12:
            break
        nxt = r - f / df
        if abs(nxt - r) < 1e-9:
            r = nxt
            break
        if nxt < -0.5 or nxt > 1.0 or not (nxt == nxt):  # NaN check
            break
        r = nxt
    else:
        if abs(npv(r)) < 1e-6:
            return float(r)

    # Bisection fallback
    lo, hi = -0.5, 0.8
    flo, fhi = npv(lo), npv(hi)
    if flo * fhi > 0:
        return 0.0
    for _ in range(40):
        mid = (lo + hi) / 2
        fm = npv(mid)
        if abs(fm) < 1e-8:
            return float(mid)
        if flo * fm <= 0:
            hi, fhi = mid, fm
        else:
            lo, flo = mid, fm
    return float((lo + hi) / 2)


def scale_illustration(
    premium_usd: float,
    *,
    scenario: str = "expected",
) -> list[dict[str, Any]]:
    """Scale base US$400k ICON V table to the chosen premium."""
    meta = illustration_meta()
    base = float(meta["base_premium_usd"])
    scale = float(premium_usd or 0) / base if base else 0.0
    out: list[dict[str, Any]] = []
    for row in _illustration_payload().get("rows") or []:
        gtee = round(float(row["guaranteedCV"]) * scale)
        rev = round(float(row["reversionaryCV"]) * scale)
        sp = round(float(row["specialBonusCV"]) * scale)
        death = round(float(row["deathBenefit"]) * scale)
        total = gtee + rev + sp
        scen = str(scenario or "expected")
        if scen == "pessimistic" and row.get("pessimisticTotalCV") is not None:
            total = round(float(row["pessimisticTotalCV"]) * scale)
            if row.get("pessimisticDeathBenefit") is not None:
                death = round(float(row["pessimisticDeathBenefit"]) * scale)
        elif scen == "optimistic" and row.get("optimisticTotalCV") is not None:
            total = round(float(row["optimisticTotalCV"]) * scale)
            if row.get("optimisticDeathBenefit") is not None:
                death = round(float(row["optimisticDeathBenefit"]) * scale)
        out.append(
            {
                "year": int(row["year"]),
                "age": int(row["age"]),
                "guaranteedCV": gtee,
                "reversionaryCV": rev,
                "specialBonusCV": sp,
                "totalSurrenderValue": total,
                "deathBenefit": death,
            }
        )
    return out


def compute_financing(
    premium_usd: float,
    bank_id: str,
    *,
    fx: float | None = None,
    interest_rate_pct: float | None = None,
    ltv: float | None = None,
    apply_promotion: bool = True,
    scenario: str = "expected",
    currency_mode: str = "HKD",  # interest display preference
) -> dict[str, Any]:
    """Run the ICON V + bank premium-financing projection."""
    bank = get_bank(bank_id)
    if not bank:
        raise ValueError(f"未知銀行：{bank_id}")
    meta = illustration_meta()
    fx_v = float(fx if fx is not None else meta["fx_usd_hkd"])
    prem = float(premium_usd or 0)
    if prem <= 0:
        raise ValueError("保費必須大於 0")

    day1 = round(prem * float(meta["day1_guaranteed_cv_ratio"]))
    ltv_v = float(
        ltv
        if ltv is not None
        else (bank.get("maxLTV") or {}).get("sameCurrencyRatio") or 0.9
    )
    loan_usd = round(day1 * ltv_v)
    loan_hkd = round(loan_usd * fx_v)

    fee_ratio = float((bank.get("setupFee") or {}).get("feeRatio") or 0)
    setup_usd = round(loan_usd * fee_ratio)
    setup_hkd = round(setup_usd * fx_v)
    # ZA Bank: waive setup fee when loan HKD > 2,000,000 (public SPA rule)
    if bank.get("id") == "za-bank" and loan_hkd > 2_000_000:
        setup_usd = 0
        setup_hkd = 0

    levy = levy_usd(prem, fx_v)
    levy_hkd = levy * fx_v

    disc_rate = promo_discount_rate(prem) if apply_promotion else 0.0
    disc_usd = round(prem * disc_rate)
    actual_paid = prem - disc_usd
    outlay = round(actual_paid - loan_usd + setup_usd + levy)
    outlay_hkd = round(outlay * fx_v)
    leverage = prem / outlay if outlay > 0 else 0.0

    # Interest: SPA uses HKD estimated rate for the main table
    rate = float(
        interest_rate_pct
        if interest_rate_pct is not None
        else (bank.get("interestRateHKD") or {}).get("currentEstimatedRate")
        or 0
    )
    annual_int_usd = round(loan_usd * rate / 100.0)
    annual_int_hkd = round(loan_hkd * rate / 100.0)

    scaled = scale_illustration(prem, scenario=scenario)
    years_out: list[dict[str, Any]] = []
    for row in scaled:
        yr = int(row["year"])
        sv = float(row["totalSurrenderValue"])
        db = float(row["deathBenefit"])
        cum_int = round(annual_int_usd * yr)
        net_sv = max(0.0, sv - loan_usd)
        net_db = max(0.0, db - loan_usd)
        total_cost = outlay + cum_int
        net_profit = net_sv - outlay - cum_int
        leveraged_roi = (net_profit / total_cost * 100.0) if total_cost > 0 else 0.0

        # Non-leveraged IRR: -premium … 0… +SV at year
        nl_cf = [-prem] + [0.0] * (yr - 1) + [sv]
        # Leveraged IRR: -outlay, then -interest each year, exit with net SV
        lev_cf = [-float(outlay)] + [-float(annual_int_usd)] * (yr - 1)
        lev_cf.append(-float(annual_int_usd) + net_sv)

        years_out.append(
            {
                "year": yr,
                "age": int(row["age"]),
                "guaranteed_cv_usd": float(row["guaranteedCV"]),
                "total_sv_usd": sv,
                "death_benefit_usd": db,
                "cumulative_interest_usd": cum_int,
                "net_sv_usd": net_sv,
                "net_death_benefit_usd": net_db,
                "net_profit_usd": net_profit,
                "leveraged_roi_pct": leveraged_roi,
                "leveraged_irr_pct": irr(lev_cf) * 100.0,
                "non_leveraged_irr_pct": irr(nl_cf) * 100.0,
                "total_sv_hkd": round(sv * fx_v),
                "net_sv_hkd": round(net_sv * fx_v),
                "net_profit_hkd": round(net_profit * fx_v),
                "cumulative_interest_hkd": round(cum_int * fx_v),
            }
        )

    focus_years = {1, 5, 6, 10, 15, 20, 30}
    focus = [y for y in years_out if y["year"] in focus_years]

    return {
        "ok": True,
        "product": meta["product"],
        "product_en": meta["product_en"],
        "bank": {
            "id": bank.get("id"),
            "name": bank.get("name"),
            "shortName": bank.get("shortName"),
            "badge": bank.get("badge"),
            "tagline": bank.get("tagline"),
            "rate_formula": (bank.get("interestRateHKD") or {}).get("formula"),
            "rate_details": (bank.get("interestRateHKD") or {}).get("details"),
            "ltv_description": (bank.get("maxLTV") or {}).get("description"),
            "setup_fee_description": (bank.get("setupFee") or {}).get("description"),
            "promotion_period": bank.get("promotionPeriod"),
        },
        "fx": fx_v,
        "scenario": scenario,
        "currency_mode": currency_mode,
        "summary": {
            "premium_usd": prem,
            "premium_hkd": round(prem * fx_v),
            "day1_guaranteed_cv_usd": day1,
            "day1_guaranteed_cv_hkd": round(day1 * fx_v),
            "ltv_ratio": ltv_v,
            "loan_usd": loan_usd,
            "loan_hkd": loan_hkd,
            "setup_fee_usd": setup_usd,
            "setup_fee_hkd": setup_hkd,
            "levy_usd": levy,
            "levy_hkd": levy_hkd,
            "apply_promotion": bool(apply_promotion),
            "discount_rate": disc_rate,
            "discount_usd": disc_usd,
            "discount_hkd": round(disc_usd * fx_v),
            "actual_premium_paid_usd": actual_paid,
            "actual_premium_paid_hkd": round(actual_paid * fx_v),
            "initial_outlay_usd": outlay,
            "initial_outlay_hkd": outlay_hkd,
            "leverage_ratio": leverage,
            "annual_interest_rate_pct": rate,
            "annual_interest_usd": annual_int_usd,
            "annual_interest_hkd": annual_int_hkd,
        },
        "years": years_out,
        "focus_years": focus,
        "disclaimer": (
            "數字為示意：利益說明按公開示範表（基準保費 US$400,000）按比例縮放；"
            "銀行利率／成數／優惠為擷取快照，會過期。紅利非保證；實際以保險公司正式"
            "利益說明、銀行批核及條款為準。"
        ),
        "banks_disclaimer": banks_disclaimer(),
    }


def format_usd(n: float) -> str:
    return f"US${float(n):,.0f}"


def format_hkd(n: float) -> str:
    return f"HK${float(n):,.0f}"


def format_pct(n: float, digits: int = 2) -> str:
    return f"{float(n):.{digits}f}%"


_SCENARIO_LABELS = {
    "expected": "當前假設（Expected）",
    "pessimistic": "較保守（Pessimistic）",
    "optimistic": "較樂觀（Optimistic）",
}


def scenario_label(scenario: str) -> str:
    return _SCENARIO_LABELS.get(str(scenario or ""), str(scenario or "—"))


def whatsapp_summary(result: dict[str, Any], *, client: str = "") -> str:
    """Client-facing WhatsApp summary from a compute_financing() result."""
    s = result.get("summary") or {}
    bank = result.get("bank") or {}
    lines = [
        f"*{result.get('product') or '智盈匯聚 V'} · 保費融資計劃書*",
    ]
    if client:
        lines.append(f"客戶：{client}")
    lines.extend(
        [
            f"銀行：{bank.get('name') or '—'}",
            f"保費：{format_usd(float(s.get('premium_usd') or 0))}"
            + (
                f"（折扣 {float(s.get('discount_rate') or 0) * 100:.0f}% → "
                f"實付 {format_usd(float(s.get('actual_premium_paid_usd') or 0))}）"
                if s.get("apply_promotion") and float(s.get("discount_usd") or 0)
                else ""
            ),
            f"貸款：{format_usd(float(s.get('loan_usd') or 0))}"
            f"（LTV {float(s.get('ltv_ratio') or 0) * 100:.0f}%）",
            f"初期自資：{format_usd(float(s.get('initial_outlay_usd') or 0))} · "
            f"槓桿 {float(s.get('leverage_ratio') or 0):.2f}x",
            f"預估年息：{float(s.get('annual_interest_rate_pct') or 0):.2f}%"
            f"（約 {format_usd(float(s.get('annual_interest_usd') or 0))}/年）",
            f"紅利情景：{scenario_label(str(result.get('scenario') or 'expected'))}",
            "",
            "*重點年份（槓桿 IRR）*",
        ]
    )
    for y in result.get("focus_years") or []:
        if int(y.get("year") or 0) in (1, 5, 6, 10, 20, 30):
            lines.append(
                f"第 {y['year']} 年：淨值 {format_usd(float(y.get('net_sv_usd') or 0))} · "
                f"IRR {float(y.get('leveraged_irr_pct') or 0):.1f}%"
            )
    lines.append("")
    lines.append("_示意數字；紅利／利率非保證；以正式計劃書及銀行批核為準_")
    return "\n".join(lines)
