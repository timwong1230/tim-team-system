"""Prospect lists — 簽單 / 招募, per user, quarterly, with Fact find."""

from __future__ import annotations

import datetime
from typing import Any

import pandas as pd

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
    selling_products: str,
    fyc: float,
    factfind: str = "",
) -> None:
    name = str(name or "").strip()
    if not name:
        raise ValueError("必須填寫 Name")
    if int(quarter) not in QUARTERS:
        raise ValueError("季度必須係 1–4")
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
            "selling_products": str(selling_products or "").strip(),
            "fyc": float(fyc or 0),
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


def update_prospect(row_id: str | int, fields: dict[str, Any]) -> None:
    allowed = {
        "name",
        "selling_products",
        "fyc",
        "recruit_category",
        "factfind",
        "year",
        "quarter",
    }
    payload = {k: v for k, v in fields.items() if k in allowed}
    if "name" in payload and not str(payload["name"] or "").strip():
        raise ValueError("Name 唔可以空白")
    if "recruit_category" in payload and payload["recruit_category"]:
        if payload["recruit_category"] not in RECRUIT_CATEGORIES:
            raise ValueError("類別必須係 Organic / IRP / MCV")
    if "fyc" in payload:
        payload["fyc"] = float(payload["fyc"] or 0)
    payload["updated_at"] = str(datetime.datetime.now())
    run_query_gs("UPDATE", "prospects", payload, row_id=row_id)


def delete_prospect(row_id: str | int) -> None:
    run_query_gs("DELETE", "prospects", row_id=row_id)


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
