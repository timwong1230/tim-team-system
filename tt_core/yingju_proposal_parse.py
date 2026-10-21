"""Parse FWD 盈聚‧天下 II official illustration PDFs into structured numbers."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, BinaryIO

_NUM = re.compile(r"^-?[\d,]+(?:\.\d+)?$")
_YEAR = re.compile(r"^\d{1,3}$")


def _f(s: str) -> float:
    return float(str(s).replace(",", "").strip())


def _is_num(s: str) -> bool:
    return bool(_NUM.match(str(s).strip()))


def _pdf_text_pages(source: str | Path | bytes | BinaryIO) -> list[str]:
    try:
        import pymupdf as fitz
    except ImportError:  # pragma: no cover
        import fitz

    if isinstance(source, (bytes, bytearray)):
        doc = fitz.open(stream=bytes(source), filetype="pdf")
    elif hasattr(source, "read"):
        data = source.read()
        doc = fitz.open(stream=data, filetype="pdf")
    else:
        doc = fitz.open(str(source))
    try:
        return [page.get_text() for page in doc]
    finally:
        doc.close()


def _parse_summary_meta(pages: list[str]) -> dict[str, Any]:
    blob = "\n".join(pages[:3])
    meta: dict[str, Any] = {
        "product_name": "FWD 盈聚‧天下 II 保險計劃（5 年供）",
        "age": None,
        "gender": "",
        "annual_usd": None,
        "currency": "USD",
        "pay_years": 5,
    }
    m = re.search(r"年齡[：:]\s*(\d{1,3})", blob)
    if m:
        meta["age"] = int(m.group(1))
    m = re.search(r"性別[：:]\s*([男女])", blob)
    if m:
        meta["gender"] = m.group(1)
    m = re.search(
        r"投保時每年總保費\s*\(\s*1\s*\)\s*[：:︰]\s*([\d,]+(?:\.\d+)?)",
        blob,
    )
    if m:
        meta["annual_usd"] = _f(m.group(1))
    else:
        m = re.search(
            r"盈聚‧天下\s*II[^\n]*5\s*年供[\s\S]{0,200}?([\d,]+\.\d+)\s*\n\s*-\s*\n\s*5\s*年",
            blob,
        )
        if m:
            meta["annual_usd"] = _f(m.group(1))
    if "保單貨幣：港" in blob.replace(" ", "") or "保單貨幣︰港" in blob:
        meta["currency"] = "HKD"
    return meta


def _iter_number_tokens(text: str) -> list[str]:
    out: list[str] = []
    for raw in text.splitlines():
        s = raw.strip()
        if not s:
            continue
        if _is_num(s) or _YEAR.match(s):
            out.append(s.replace(",", "") if "," in s or "." in s else s)
    return out


def _page_is_base_sv(text: str) -> bool:
    if "於各保單年度終結時之保單價值" not in text:
        return False
    if "作出提款後" in text:
        return False
    if "身故權益總額" in text:
        return False
    return "退保價值總額" in text


def _page_is_wd_sv(text: str) -> bool:
    if "作出提款後之保單價值" not in text and "作出提款後" not in text:
        return False
    if "身故權益總額" in text and "退保價值總額" not in text:
        return False
    return "退保價值總額" in text and "提款" in text


def _parse_base_value_rows(pages: list[str]) -> list[dict[str, Any]]:
    rows: dict[int, dict[str, Any]] = {}
    for text in pages:
        if not _page_is_base_sv(text):
            continue
        tokens = _iter_number_tokens(text)
        i = 0
        while i + 6 < len(tokens):
            if not _YEAR.match(tokens[i]):
                i += 1
                continue
            year = int(tokens[i])
            if year < 1 or year > 150:
                i += 1
                continue
            age_tok = tokens[i + 1]
            nums = tokens[i + 2 : i + 7]
            if not _is_num(age_tok) or len(nums) < 5 or not all(_is_num(x) for x in nums):
                i += 1
                continue
            prem, gtee, rev, sp, total = (_f(x) for x in nums)
            age = int(float(age_tok))
            if age < 0 or age > 130:
                i += 1
                continue
            # 退保價值總額 ≈ 保證 + 歸原 + 特別
            if abs((gtee + rev + sp) - total) > 3:
                i += 1
                continue
            rows[year] = {
                "policy_year": year,
                "age": age,
                "total_prem_usd": prem,
                "guaranteed_usd": gtee,
                "reversionary_usd": rev,
                "special_usd": sp,
                "sv_usd": total,
                "withdraw_usd": 0.0,
                "source": "base",
            }
            i += 7
    return [rows[k] for k in sorted(rows)]


def _parse_withdrawal_rows(pages: list[str]) -> list[dict[str, Any]]:
    rows: dict[int, dict[str, Any]] = {}
    for text in pages:
        if not _page_is_wd_sv(text):
            continue
        tokens = _iter_number_tokens(text)
        i = 0
        while i + 9 < len(tokens):
            if not _YEAR.match(tokens[i]):
                i += 1
                continue
            year = int(tokens[i])
            if year < 1 or year > 150:
                i += 1
                continue
            age_tok = tokens[i + 1]
            nums = tokens[i + 2 : i + 10]
            if not _is_num(age_tok) or len(nums) < 8 or not all(_is_num(x) for x in nums):
                i += 1
                continue
            prem, wd, face, gtee, rev, sp, lock, total = (_f(x) for x in nums)
            age = int(float(age_tok))
            if age < 0 or age > 130:
                i += 1
                continue
            # 退保價值總額 ≈ 保證 + 歸原 + 特別 + 鎖定
            if abs((gtee + rev + sp + lock) - total) > 3:
                i += 1
                continue
            rows[year] = {
                "policy_year": year,
                "age": age,
                "total_prem_usd": prem,
                "withdraw_usd": wd,
                "nominal_usd": face,
                "guaranteed_usd": gtee,
                "reversionary_usd": rev,
                "special_usd": sp,
                "lock_usd": lock,
                "sv_usd": total,
                "source": "withdrawal",
            }
            i += 10
    return [rows[k] for k in sorted(rows)]


def parse_yingju_illustration_pdf(source: str | Path | bytes | BinaryIO) -> dict[str, Any]:
    """Return structured illustration data from an official Yingju II PDF."""
    pages = _pdf_text_pages(source)
    full = "\n".join(pages)
    if "盈聚" not in full or "天下" not in full:
        raise ValueError("呢份 PDF 唔似盈聚‧天下 II 利益說明，請上載官方建議書。")

    meta = _parse_summary_meta(pages)
    base_rows = _parse_base_value_rows(pages)
    wd_rows = _parse_withdrawal_rows(pages)

    if not base_rows and not wd_rows:
        raise ValueError("搵唔到保單年度退保價值表，請確認係完整官方利益說明 PDF。")

    by_year_base = {r["policy_year"]: r for r in base_rows}
    annual = meta.get("annual_usd")
    if annual is None:
        y1 = by_year_base.get(1) or (wd_rows[0] if wd_rows else None)
        if y1:
            annual = float(y1["total_prem_usd"])
            meta["annual_usd"] = annual

    y6 = by_year_base.get(6)
    y5 = by_year_base.get(5)
    if y6 is None and wd_rows:
        # 提款表第 6 年係提款後；若無 base 表，仍可顯示但標明
        y6 = next((r for r in wd_rows if r["policy_year"] == 6), None)
    if y5 is None and wd_rows:
        y5 = next((r for r in wd_rows if r["policy_year"] == 5), None)

    wd_schedule = [r for r in wd_rows if float(r.get("withdraw_usd") or 0) > 0]
    first_wd = wd_schedule[0] if wd_schedule else None
    last_wd = wd_schedule[-1] if wd_schedule else None

    return {
        "ok": True,
        "meta": meta,
        "annual_usd": annual,
        "base_rows": base_rows,
        "withdrawal_rows": wd_rows,
        "year5_sv_usd": float(y5["sv_usd"]) if y5 else None,
        "year6_sv_usd": float(y6["sv_usd"]) if y6 else None,
        "year6_total_prem_usd": float(y6["total_prem_usd"]) if y6 else None,
        "has_withdrawal_scenario": bool(wd_schedule),
        "withdraw_start_year": int(first_wd["policy_year"]) if first_wd else None,
        "withdraw_end_year": int(last_wd["policy_year"]) if last_wd else None,
        "withdraw_usd": float(first_wd["withdraw_usd"]) if first_wd else None,
        "withdraw_years": len(wd_schedule),
        "source_label": "官方利益說明 PDF",
    }


def focus_rows_from_illustration(
    parsed: dict[str, Any],
    *,
    years: list[int] | None = None,
    fx: float = 7.85,
) -> list[dict[str, Any]]:
    """Pick key years for proposal value table (official numbers only)."""
    base = {r["policy_year"]: r for r in parsed.get("base_rows") or []}
    wd = {r["policy_year"]: r for r in parsed.get("withdrawal_rows") or []}
    fx = float(fx or 7.85)
    if years is None:
        years = [6, 10, 15, 20]
        if parsed.get("withdraw_start_year"):
            years.append(int(parsed["withdraw_start_year"]))
        if parsed.get("withdraw_end_year"):
            # 提款開始後第 5／10 年樣本期，避免只顯示最後一年
            start = int(parsed["withdraw_start_year"] or 6)
            years.extend([start + 4, start + 9, int(parsed["withdraw_end_year"])])
        for r in parsed.get("base_rows") or []:
            if int(r.get("age") or 0) in {18, 22, 65, 100}:
                years.append(int(r["policy_year"]))
    out: list[dict[str, Any]] = []
    seen: set[int] = set()
    for yr in sorted(set(int(y) for y in years)):
        if yr in seen or yr < 6:
            continue
        # 第 6 年優先用無提款表（breakeven 畫面）
        if yr == 6 and yr in base:
            row = base[yr]
        elif yr in wd and float(wd[yr].get("withdraw_usd") or 0) > 0:
            row = wd[yr]
        elif yr in base:
            row = base[yr]
        elif yr in wd:
            row = wd[yr]
        else:
            continue
        seen.add(yr)
        wdv = float(row.get("withdraw_usd") or 0)
        av = float(row.get("sv_usd") or 0)
        out.append(
            {
                "policy_year": yr,
                "age": row.get("age"),
                "withdraw_usd": wdv,
                "av_end_usd": av,
                "av_end_hkd": round(av * fx, 0),
                "total_prem_usd": float(row.get("total_prem_usd") or 0),
                "note": (
                    "提款後戶口（官方）"
                    if wdv > 0
                    else (
                        "第 6 年退保價值（對照已繳保費）"
                        if yr == 6
                        else "官方退保價值"
                    )
                ),
                "source": row.get("source"),
            }
        )
    return out


def scenario_from_illustration(
    parsed: dict[str, Any],
    *,
    fx: float = 7.85,
    age: int | None = None,
) -> dict[str, Any]:
    """Build a metrics/scenario dict from official illustration numbers only."""
    fx = float(fx or 7.85)
    meta = parsed.get("meta") or {}
    annual = float(parsed.get("annual_usd") or meta.get("annual_usd") or 0)
    age_v = int(age if age is not None else (meta.get("age") or 0))
    total_prem = round(annual * 5, 0)
    y5 = parsed.get("year5_sv_usd")
    y6 = parsed.get("year6_sv_usd")
    y5u = float(y5) if y5 is not None else None
    y6u = float(y6) if y6 is not None else None

    has_wd = bool(parsed.get("has_withdrawal_scenario"))
    start = int(parsed["withdraw_start_year"]) if parsed.get("withdraw_start_year") else 6
    n_wd = int(parsed.get("withdraw_years") or 0) if has_wd else 0
    end_wd = int(parsed["withdraw_end_year"]) if parsed.get("withdraw_end_year") else None
    wd = float(parsed.get("withdraw_usd") or 0) if has_wd else 0.0

    wd_by_year = {int(r["policy_year"]): r for r in (parsed.get("withdrawal_rows") or [])}
    after_u = None
    if has_wd and end_wd and end_wd in wd_by_year:
        after_u = float(wd_by_year[end_wd].get("sv_usd") or 0)
    elif has_wd and start in wd_by_year:
        after_u = float(wd_by_year[start].get("sv_usd") or 0)

    total_wd = round(wd * n_wd, 0) if n_wd and wd else 0.0
    rows = focus_rows_from_illustration(parsed, fx=fx)
    horizon = max([int(r["policy_year"]) for r in rows] + [6, start])

    return {
        "annual_usd": annual,
        "annual_hkd": round(annual * fx, 0),
        "total_prem_usd": total_prem,
        "total_prem_hkd": round(total_prem * fx, 0),
        "year5_sv_usd": y5u,
        "year5_sv_hkd": round(y5u * fx, 0) if y5u is not None else None,
        "year6_sv_usd": y6u,
        "year6_sv_hkd": round(y6u * fx, 0) if y6u is not None else None,
        "withdraw_start_year": start if has_wd else start,
        "withdraw_years": n_wd,
        "withdraw_end_year": end_wd if n_wd else None,
        "withdraw_usd": round(wd, 0),
        "withdraw_hkd": round(wd * fx, 0),
        "total_withdrawn_usd": total_wd,
        "total_withdrawn_hkd": round(total_wd * fx, 0),
        "av_after_withdrawals_usd": after_u,
        "av_after_withdrawals_hkd": round(after_u * fx, 0) if after_u is not None else None,
        "final_av_usd": after_u if after_u is not None else y6u,
        "final_av_hkd": (
            round((after_u if after_u is not None else (y6u or 0)) * fx, 0)
            if (after_u is not None or y6u is not None)
            else None
        ),
        "horizon_year": horizon,
        "rows": rows,
        "growth_rate": None,
        "k5": None,
        "fx": fx,
        "breakeven_prem_usd": float(parsed.get("year6_total_prem_usd") or total_prem),
        "age": age_v,
        "source": "official_illustration",
        "source_label": str(parsed.get("source_label") or "官方利益說明 PDF"),
        "has_withdrawal_scenario": has_wd,
    }
