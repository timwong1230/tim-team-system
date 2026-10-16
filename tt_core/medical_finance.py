"""醫療融資計算機 — 5 年儲蓄、第 6 年起提款繳醫家保（方案 2）。"""

from __future__ import annotations

import csv
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent / "data_files"
PREMIUM_CSV = DATA_DIR / "vfamily_premiums.csv"
CALIBRATION_JSON = DATA_DIR / "yingju_calibration.json"

DEFAULT_FX = 7.85
DEFAULT_INFLATION = 0.0261
K5_DEFAULT = 2.9727
G_DEFAULT = 0.1189


@lru_cache(maxsize=1)
def load_calibration() -> dict[str, Any]:
    if CALIBRATION_JSON.exists():
        return json.loads(CALIBRATION_JSON.read_text(encoding="utf-8"))
    return {
        "fx_usd_hkd": DEFAULT_FX,
        "k5_sv_per_annual_prem": K5_DEFAULT,
        "withdrawal_growth_rate": G_DEFAULT,
        "pay_years": 5,
        "withdraw_start_year": 6,
        "target_age": 100,
        "product_name": "盈聚‧天下 II 保險計劃 – 5年供",
    }


@lru_cache(maxsize=1)
def load_vfamily_premiums() -> dict[int, dict[str, float]]:
    """attained_age -> {male, female} annual HKD."""
    out: dict[int, dict[str, float]] = {}
    with open(PREMIUM_CSV, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            age = int(row["attained_age"])
            out[age] = {
                "male": float(row["annual_male"]),
                "female": float(row["annual_female"]),
            }
    return out


def medical_annual_hkd(age: int, gender: str) -> float:
    table = load_vfamily_premiums()
    if age not in table:
        # clamp to available range
        ages = sorted(table)
        age = min(max(age, ages[0]), ages[-1])
    key = "female" if str(gender).strip().startswith("女") else "male"
    return float(table[age][key])


def inflated_medical_schedule(
    *,
    start_age: int,
    gender: str,
    inflation: float,
    end_age: int = 100,
) -> list[dict[str, Any]]:
    """Year-by-year medical premium from start_age to end_age (attained)."""
    infl = max(0.0, min(0.05, float(inflation)))
    rows = []
    for age in range(int(start_age), int(end_age) + 1):
        base = medical_annual_hkd(age, gender)
        years_elapsed = age - int(start_age)
        prem = base * ((1.0 + infl) ** years_elapsed)
        rows.append(
            {
                "age": age,
                "base_hkd": round(base, 0),
                "premium_hkd": round(prem, 0),
                "years_from_start": years_elapsed,
            }
        )
    return rows


def withdrawal_schedule_usd(
    *,
    start_age: int,
    gender: str,
    inflation: float,
    end_age: int = 100,
    fx: float | None = None,
) -> list[dict[str, Any]]:
    """
    From policy year 6 (attained age start_age+5) to end_age,
    withdrawal = that year's inflated medical premium (USD).
    """
    cal = load_calibration()
    fx = float(fx if fx is not None else cal.get("fx_usd_hkd") or DEFAULT_FX)
    med = inflated_medical_schedule(
        start_age=start_age, gender=gender, inflation=inflation, end_age=end_age
    )
    by_age = {r["age"]: r for r in med}
    first_wd_age = int(start_age) + 5  # after 5 premium years
    rows = []
    year = 6
    for age in range(first_wd_age, int(end_age) + 1):
        m = by_age.get(age) or {
            "premium_hkd": medical_annual_hkd(age, gender),
            "base_hkd": medical_annual_hkd(age, gender),
        }
        hkd = float(m["premium_hkd"])
        usd = hkd / fx
        rows.append(
            {
                "policy_year": year,
                "age": age,
                "premium_hkd": round(hkd, 0),
                "withdraw_usd": round(usd, 2),
                "base_hkd": round(float(m.get("base_hkd") or hkd), 0),
            }
        )
        year += 1
    return rows


def simulate_fund(
    annual_prem_usd: float,
    withdrawals: list[dict[str, Any]],
    *,
    k5: float | None = None,
    growth: float | None = None,
) -> dict[str, Any]:
    """Accumulate 5 years, then grow & withdraw rising medical premiums."""
    cal = load_calibration()
    k5 = float(k5 if k5 is not None else cal.get("k5_sv_per_annual_prem") or K5_DEFAULT)
    g = float(growth if growth is not None else cal.get("withdrawal_growth_rate") or G_DEFAULT)
    p = float(annual_prem_usd)
    av = k5 * p
    path = [{"policy_year": 5, "age": None, "av_usd": round(av, 2), "withdraw_usd": 0.0}]
    ok = True
    min_av = av
    for w in withdrawals:
        av = av * (1.0 + g) - float(w["withdraw_usd"])
        min_av = min(min_av, av)
        path.append(
            {
                "policy_year": w["policy_year"],
                "age": w["age"],
                "av_usd": round(av, 2),
                "withdraw_usd": w["withdraw_usd"],
                "premium_hkd": w["premium_hkd"],
            }
        )
        if av < -1e-6:
            ok = False
            break
    return {
        "ok": ok,
        "final_av_usd": round(av, 2),
        "min_av_usd": round(min_av, 2),
        "av_at_year5_usd": round(k5 * p, 2),
        "path": path,
        "growth_rate": g,
        "k5": k5,
    }


def min_annual_savings_usd(
    *,
    start_age: int,
    gender: str,
    inflation: float,
    end_age: int = 100,
    fx: float | None = None,
    lo: float = 500.0,
    hi: float = 200_000.0,
) -> dict[str, Any]:
    """Binary search minimum USD annual premium (5 years) for 方案2."""
    cal = load_calibration()
    fx = float(fx if fx is not None else cal.get("fx_usd_hkd") or DEFAULT_FX)
    wds = withdrawal_schedule_usd(
        start_age=start_age,
        gender=gender,
        inflation=inflation,
        end_age=end_age,
        fx=fx,
    )
    if not wds:
        return {"error": "沒有提款年度", "annual_prem_usd": 0.0}

    def feasible(p: float) -> bool:
        return bool(simulate_fund(p, wds)["ok"])

    if not feasible(hi):
        # escalate hi
        trial = hi
        for _ in range(8):
            trial *= 2
            if feasible(trial):
                hi = trial
                break
        else:
            return {
                "error": "即使用好高年供都撑唔到去目標年齡，請調低通脹或完結年齡",
                "annual_prem_usd": None,
                "withdrawals": wds,
            }

    if feasible(lo):
        best = lo
    else:
        best = hi
        a, b = lo, hi
        for _ in range(40):
            mid = (a + b) / 2
            if feasible(mid):
                best = mid
                b = mid
            else:
                a = mid

    # round up to nearest 10 USD for proposal practicality
    import math

    best_r = float(math.ceil(best / 10.0) * 10)
    sim = simulate_fund(best_r, wds)
    peak = max(w["premium_hkd"] for w in wds)
    total_wd_hkd = sum(w["premium_hkd"] for w in wds)
    return {
        "annual_prem_usd": best_r,
        "annual_prem_hkd": round(best_r * fx, 0),
        "total_5yr_usd": round(best_r * 5, 0),
        "total_5yr_hkd": round(best_r * 5 * fx, 0),
        "fx": fx,
        "inflation": float(inflation),
        "start_age": int(start_age),
        "end_age": int(end_age),
        "gender": gender,
        "first_withdraw_age": wds[0]["age"],
        "n_withdraw_years": len(wds),
        "peak_medical_hkd": peak,
        "total_medical_withdraw_hkd": round(total_wd_hkd, 0),
        "year5_av_usd": sim["av_at_year5_usd"],
        "final_av_usd": sim["final_av_usd"],
        "sim_ok": sim["ok"],
        "growth_rate": sim["growth_rate"],
        "product_name": cal.get("product_name"),
        "medical_plan": "醫家保醫療計劃（獨立保單）",
        "withdrawals": wds,
        "sim_path": sim["path"],
    }


def format_hkd(amount: float) -> str:
    return f"${amount:,.0f}"


def format_usd(amount: float) -> str:
    return f"US${amount:,.0f}"


def whatsapp_summary(result: dict[str, Any], *, client: str = "") -> str:
    name = f"— {client.strip()}" if str(client or "").strip() else ""
    lines = [
        f"💹 *醫療融資試算* {name}".rstrip(),
        "",
        f"醫保：{result.get('medical_plan')}",
        f"儲蓄：{result.get('product_name')}",
        f"客戶：{result.get('start_age')} 歲 · {result.get('gender')} · 通脹 {result.get('inflation', 0)*100:.2f}%",
        f"提款：{result.get('first_withdraw_age')}–{result.get('end_age')} 歲（第 6 年起）",
        "",
        f"*最少年供（儲 5 年）*",
        f"· {format_usd(result.get('annual_prem_usd') or 0)}／年",
        f"· 約 {format_hkd(result.get('annual_prem_hkd') or 0)}／年（匯率 {result.get('fx')}）",
        f"· 5 年合共約 {format_hkd(result.get('total_5yr_hkd') or 0)}",
        "",
        f"期間最高一年醫保保費約 {format_hkd(result.get('peak_medical_hkd') or 0)}",
        f"提款年度合計（通脹後）約 {format_hkd(result.get('total_medical_withdraw_hkd') or 0)}",
        "",
        "_試算基於現行醫家保保費表及盈聚計劃書校準假設，非保證回報／非正式報價。_",
    ]
    return "\n".join(lines)
