"""準客戶名單 — 簽單 / 招募, per user, quarterly, Excel-style products + Fact find."""

from __future__ import annotations

import datetime
import json
from typing import Any

import pandas as pd

from tt_core.commission import (
    PRODUCT_CATALOG,
    QSB_THRESHOLD,
    calc_fyc,
    normalize_others,
    normalize_premiums,
    products_summary,
    qsb_active,
)
from tt_core.constants import TEMPLATE_FACTFIND
from tt_core.db import read_data, run_query_gs

LIST_SALES = "sales"
LIST_RECRUIT = "recruit"
RECRUIT_CATEGORIES = ["Organic", "IRP", "MCV"]
QUARTERS = (1, 2, 3, 4)


def current_year() -> int:
    return datetime.date.today().year


def factfind_template() -> str:
    return TEMPLATE_FACTFIND


def encode_products(
    premiums: dict[str, float] | None,
    others: list[dict] | None = None,
) -> str:
    """Store catalog premiums + optional 其他 products as JSON."""
    clean = normalize_premiums(premiums)
    other_clean = normalize_others(others)
    if not clean and not other_clean:
        return ""
    payload: dict[str, Any] = dict(clean)
    if other_clean:
        payload["_other"] = other_clean
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def decode_deal(raw: Any) -> tuple[dict[str, float], list[dict]]:
    """Return (catalog_premiums, other_products)."""
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return {}, []
    text = str(raw).strip()
    if not text:
        return {}, []
    if text.startswith("{"):
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                others = normalize_others(data.get("_other"))
                premiums = normalize_premiums(data)
                return premiums, others
        except json.JSONDecodeError:
            return {}, []
    return {}, []


def decode_products(raw: Any) -> dict[str, float]:
    """Catalog premiums only (backward-compatible helper)."""
    premiums, _others = decode_deal(raw)
    return premiums


def display_products(raw: Any, *, ytd_fyc: float = 0.0) -> str:
    premiums, others = decode_deal(raw)
    if premiums or others:
        return products_summary(premiums, others=others, ytd_fyc=ytd_fyc)
    text = str(raw or "").strip()
    return text


def deal_fyc(raw: Any, *, ytd_fyc: float = 0.0) -> float:
    premiums, others = decode_deal(raw)
    if premiums or others:
        return calc_fyc(premiums, others=others, ytd_fyc=ytd_fyc)
    return 0.0


def get_prospects(
    *,
    username: str | None = None,
    list_type: str | None = None,
    year: int | None = None,
    quarter: int | None = None,
) -> pd.DataFrame:
    df = read_data("prospects")
    cols = [
        "id",
        "username",
        "list_type",
        "year",
        "quarter",
        "name",
        "selling_products",
        "fyc",
        "recruit_category",
        "factfind",
        "created_at",
        "updated_at",
    ]
    if df is None or df.empty:
        return pd.DataFrame(columns=cols)
    out = df.copy()
    for c in cols:
        if c not in out.columns:
            out[c] = ""
    if username:
        out = out[out["username"].astype(str) == str(username)]
    if list_type:
        out = out[out["list_type"].astype(str) == str(list_type)]
    if year is not None:
        out = out[pd.to_numeric(out["year"], errors="coerce") == int(year)]
    if quarter is not None:
        out = out[pd.to_numeric(out["quarter"], errors="coerce") == int(quarter)]
    out["fyc"] = pd.to_numeric(out["fyc"], errors="coerce").fillna(0.0)
    out["year"] = pd.to_numeric(out["year"], errors="coerce").fillna(0).astype(int)
    out["quarter"] = pd.to_numeric(out["quarter"], errors="coerce").fillna(0).astype(int)
    return out.sort_values(
        by=["year", "quarter", "name"], ascending=[False, True, True]
    ).reset_index(drop=True)


def add_sales_prospect(
    username: str,
    *,
    year: int,
    quarter: int,
    name: str,
    premiums: dict[str, float] | None = None,
    others: list[dict] | None = None,
    selling_products: str = "",
    fyc: float | None = None,
    ytd_fyc: float = 0.0,
    factfind: str = "",
) -> None:
    name = str(name or "").strip()
    if not name:
        raise ValueError("必須填寫 Name")
    if int(quarter) not in QUARTERS:
        raise ValueError("季度必須係 1–4")
    clean = normalize_premiums(premiums)
    other_clean = normalize_others(others)
    if clean or other_clean:
        products_raw = encode_products(clean, other_clean)
        fyc_val = calc_fyc(clean, others=other_clean, ytd_fyc=ytd_fyc)
    else:
        products_raw = str(selling_products or "").strip()
        fyc_val = float(fyc or 0)
    now = str(datetime.datetime.now())
    run_query_gs(
        "INSERT",
        "prospects",
        {
            "username": username,
            "list_type": LIST_SALES,
            "year": int(year),
            "quarter": int(quarter),
            "name": name,
            "selling_products": products_raw,
            "fyc": float(fyc_val),
            "recruit_category": "",
            "factfind": factfind or factfind_template(),
            "created_at": now,
            "updated_at": now,
        },
    )


def add_recruit_prospect(
    username: str,
    *,
    year: int,
    quarter: int,
    name: str,
    category: str,
    factfind: str = "",
) -> None:
    name = str(name or "").strip()
    cat = str(category or "").strip()
    if not name:
        raise ValueError("必須填寫 Name")
    if cat not in RECRUIT_CATEGORIES:
        raise ValueError("類別必須係 Organic / IRP / MCV")
    if int(quarter) not in QUARTERS:
        raise ValueError("季度必須係 1–4")
    now = str(datetime.datetime.now())
    run_query_gs(
        "INSERT",
        "prospects",
        {
            "username": username,
            "list_type": LIST_RECRUIT,
            "year": int(year),
            "quarter": int(quarter),
            "name": name,
            "selling_products": "",
            "fyc": 0,
            "recruit_category": cat,
            "factfind": factfind or factfind_template(),
            "created_at": now,
            "updated_at": now,
        },
    )


def update_prospect(row_id: str | int, fields: dict[str, Any]) -> bool:
    allowed = {
        "name",
        "selling_products",
        "fyc",
        "recruit_category",
        "factfind",
        "year",
        "quarter",
        "premiums",
        "others",
        "ytd_fyc",
    }
    payload = {k: v for k, v in fields.items() if k in allowed}
    ytd = float(payload.pop("ytd_fyc", 0) or 0)
    if "premiums" in payload or "others" in payload:
        clean = normalize_premiums(payload.pop("premiums", None))
        other_clean = normalize_others(payload.pop("others", None))
        payload["selling_products"] = encode_products(clean, other_clean)
        payload["fyc"] = calc_fyc(clean, others=other_clean, ytd_fyc=ytd)
    if "name" in payload and not str(payload["name"] or "").strip():
        raise ValueError("Name 唔可以空白")
    if "recruit_category" in payload and payload["recruit_category"]:
        if payload["recruit_category"] not in RECRUIT_CATEGORIES:
            raise ValueError("類別必須係 Organic / IRP / MCV")
    if "fyc" in payload:
        payload["fyc"] = float(payload["fyc"] or 0)
    payload["updated_at"] = str(datetime.datetime.now())
    return bool(run_query_gs("UPDATE", "prospects", payload, row_id=row_id))


def delete_prospect(row_id: str | int) -> bool:
    return bool(run_query_gs("DELETE", "prospects", row_id=row_id))


def quarter_fyc_total(df: pd.DataFrame, year: int, quarter: int) -> float:
    if df.empty:
        return 0.0
    sub = df[
        (df["list_type"].astype(str) == LIST_SALES)
        & (df["year"] == int(year))
        & (df["quarter"] == int(quarter))
    ]
    return float(sub["fyc"].sum()) if not sub.empty else 0.0


def year_fyc_total(df: pd.DataFrame, year: int) -> float:
    if df.empty:
        return 0.0
    sub = df[(df["list_type"].astype(str) == LIST_SALES) & (df["year"] == int(year))]
    return float(sub["fyc"].sum()) if not sub.empty else 0.0


def quarter_counts(df: pd.DataFrame, year: int, list_type: str) -> dict[int, int]:
    out = {q: 0 for q in QUARTERS}
    if df.empty:
        return out
    sub = df[(df["list_type"].astype(str) == list_type) & (df["year"] == int(year))]
    for q in QUARTERS:
        out[q] = int((sub["quarter"] == q).sum())
    return out


def product_catalog():
    return PRODUCT_CATALOG


def member_ytd_fyc(username: str) -> float:
    """Iris / system Year-to-date FYC for QSB gate."""
    try:
        from tt_core.data import get_data

        df = get_data("Yearly")
        if df is None or df.empty:
            return 0.0
        row = df[df["username"].astype(str) == str(username)]
        if row.empty:
            return 0.0
        return float(row.iloc[0].get("fyc") or 0)
    except Exception:
        return 0.0


def qsb_status(username: str) -> dict[str, Any]:
    ytd = member_ytd_fyc(username)
    return {
        "ytd_fyc": ytd,
        "active": qsb_active(ytd),
        "threshold": float(QSB_THRESHOLD),
    }
