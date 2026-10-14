"""FWD Iris production report import & sync.

FWD Iris / Agent Assist does not expose a public API for team FYC.
This module syncs Iris Excel/CSV exports into monthly_fyc so Leaders
no longer need to type amounts by hand.
"""

from __future__ import annotations

import datetime
import io
import re
from typing import Any

import pandas as pd

from lib.constants import (
    IRIS_AGENT_ALIASES,
    IRIS_CODE_ALIASES,
    IRIS_FYC_ALIASES,
    IRIS_MONTH_ALIASES,
)
from lib.data import get_clean_users, upd_fyc
from lib.db import read_data, run_query_gs


def _norm(s: Any) -> str:
    return re.sub(r"\s+", " ", str(s or "").strip().lower())


def _find_col(columns: list[str], aliases: list[str]) -> str | None:
    normalized = {_norm(c): c for c in columns}
    for alias in aliases:
        if alias in normalized:
            return normalized[alias]
    for alias in aliases:
        for ncol, original in normalized.items():
            if alias in ncol:
                return original
    return None


def load_iris_file(uploaded_file) -> pd.DataFrame:
    """Load Iris export (.xlsx / .xls / .csv) into a DataFrame."""
    name = uploaded_file.name.lower()
    raw = uploaded_file.read()
    bio = io.BytesIO(raw)

    if name.endswith(".csv"):
        for enc in ("utf-8-sig", "utf-8", "cp950", "big5", "latin-1"):
            try:
                bio.seek(0)
                return pd.read_csv(bio, encoding=enc)
            except Exception:
                continue
        bio.seek(0)
        return pd.read_csv(bio)

    # Excel: try first sheet; if empty, try others
    bio.seek(0)
    xl = pd.ExcelFile(bio)
    for sheet in xl.sheet_names:
        df = xl.parse(sheet)
        if not df.empty and len(df.columns) >= 2:
            return df
    return xl.parse(xl.sheet_names[0])


def detect_columns(df: pd.DataFrame) -> dict[str, str | None]:
    cols = [str(c) for c in df.columns]
    return {
        "agent": _find_col(cols, IRIS_AGENT_ALIASES),
        "code": _find_col(cols, IRIS_CODE_ALIASES),
        "fyc": _find_col(cols, IRIS_FYC_ALIASES),
        "month": _find_col(cols, IRIS_MONTH_ALIASES),
    }


def normalize_month(value: Any, fallback: str) -> str:
    """Normalize various month formats to YYYY-MM."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return fallback
    s = str(value).strip()
    if not s or s.lower() in {"nan", "none"}:
        return fallback

    # Already YYYY-MM
    m = re.match(r"^(\d{4})[-/](\d{1,2})$", s)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}"

    # YYYYMM
    m = re.match(r"^(\d{4})(\d{2})$", s)
    if m:
        return f"{m.group(1)}-{m.group(2)}"

    # Excel serial / datetime
    try:
        dt = pd.to_datetime(value, errors="coerce")
        if pd.notna(dt):
            return dt.strftime("%Y-%m")
    except Exception:
        pass

    return fallback


def parse_amount(value: Any) -> float:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value)
    s = s.replace(",", "").replace("HK$", "").replace("$", "").replace(" ", "")
    s = re.sub(r"[^\d.\-]", "", s)
    try:
        return float(s) if s else 0.0
    except ValueError:
        return 0.0


def get_agent_map() -> pd.DataFrame:
    df = read_data("iris_agent_map")
    if df.empty:
        return pd.DataFrame(columns=["iris_name", "iris_code", "username", "notes"])
    return df.drop_duplicates(subset=["iris_name", "iris_code"], keep="last")


def save_agent_mapping(iris_name: str, iris_code: str, username: str, notes: str = "") -> None:
    df = get_agent_map()
    iris_name = str(iris_name or "").strip()
    iris_code = str(iris_code or "").strip()
    username = str(username or "").strip()

    # Update existing row matched by name or code
    match = pd.DataFrame()
    if not df.empty:
        if iris_code:
            match = df[df["iris_code"].astype(str).str.strip() == iris_code]
        if match.empty and iris_name:
            match = df[df["iris_name"].astype(str).str.strip().str.lower() == iris_name.lower()]

    payload = {
        "iris_name": iris_name,
        "iris_code": iris_code,
        "username": username,
        "notes": notes,
    }
    if not match.empty:
        # iris_agent_map has no id — delete+reinsert via row find on name
        from lib.db import get_sheet, clear_cache

        ws = get_sheet("iris_agent_map")
        if ws:
            cell = ws.find(str(match.iloc[0]["iris_name"]) or str(match.iloc[0]["iris_code"]))
            if cell:
                headers = ws.row_values(1)
                for col, val in payload.items():
                    if col in headers:
                        ws.update_cell(cell.row, headers.index(col) + 1, val)
                clear_cache()
                return
    run_query_gs("INSERT", "iris_agent_map", payload)


def resolve_username(iris_name: str, iris_code: str, agent_map: pd.DataFrame, users: pd.DataFrame) -> str | None:
    name = str(iris_name or "").strip()
    code = str(iris_code or "").strip()

    if not agent_map.empty:
        if code:
            hit = agent_map[agent_map["iris_code"].astype(str).str.strip() == code]
            if not hit.empty and str(hit.iloc[0]["username"]).strip():
                return str(hit.iloc[0]["username"]).strip()
        if name:
            hit = agent_map[
                agent_map["iris_name"].astype(str).str.strip().str.lower() == name.lower()
            ]
            if not hit.empty and str(hit.iloc[0]["username"]).strip():
                return str(hit.iloc[0]["username"]).strip()

    if not users.empty and name:
        # Direct username match
        hit = users[users["username"].astype(str).str.lower() == name.lower()]
        if not hit.empty:
            return str(hit.iloc[0]["username"])
        # Partial contains
        hit = users[users["username"].astype(str).str.lower().apply(lambda u: u in name.lower() or name.lower() in u)]
        if len(hit) == 1:
            return str(hit.iloc[0]["username"])
    return None


def build_sync_preview(
    df: pd.DataFrame,
    col_agent: str | None,
    col_code: str | None,
    col_fyc: str,
    col_month: str | None,
    default_month: str,
) -> pd.DataFrame:
    """Return preview rows with matched system username and normalized FYC."""
    agent_map = get_agent_map()
    users = get_clean_users()
    users = users[users["role"] == "Member"]

    rows = []
    for _, r in df.iterrows():
        agent = r[col_agent] if col_agent else ""
        code = r[col_code] if col_code else ""
        amount = parse_amount(r[col_fyc])
        month_raw = r[col_month] if col_month else default_month
        month = normalize_month(month_raw, default_month)
        username = resolve_username(agent, code, agent_map, users)
        rows.append(
            {
                "iris_name": str(agent).strip(),
                "iris_code": str(code).strip(),
                "username": username or "",
                "month": month,
                "amount": amount,
                "matched": bool(username),
            }
        )

    preview = pd.DataFrame(rows)
    if preview.empty:
        return preview

    # Aggregate same user+month (Iris exports often have multiple policy lines)
    grouped = (
        preview.groupby(["iris_name", "iris_code", "username", "month", "matched"], dropna=False)["amount"]
        .sum()
        .reset_index()
    )
    return grouped.sort_values(by=["matched", "amount"], ascending=[False, False])


def apply_sync(preview: pd.DataFrame, synced_by: str, filename: str) -> dict[str, Any]:
    """Write matched FYC rows into monthly_fyc and log the sync."""
    matched = preview[preview["matched"] & (preview["username"] != "")].copy()
    updated = 0
    for _, row in matched.iterrows():
        upd_fyc(row["username"], row["month"], float(row["amount"]), source="iris")
        updated += 1

    months = sorted(matched["month"].unique().tolist()) if not matched.empty else []
    note = f"months={','.join(months)}"
    run_query_gs(
        "INSERT",
        "iris_sync_log",
        {
            "synced_at": str(datetime.datetime.now()),
            "synced_by": synced_by,
            "month": months[0] if len(months) == 1 else "multi",
            "filename": filename,
            "rows_total": int(len(preview)),
            "rows_matched": int(matched["username"].nunique()) if not matched.empty else 0,
            "rows_updated": updated,
            "status": "ok" if updated else "no_match",
            "note": note,
        },
    )
    return {
        "updated": updated,
        "matched_users": int(matched["username"].nunique()) if not matched.empty else 0,
        "unmatched": int((~preview["matched"]).sum()) if not preview.empty else 0,
        "months": months,
    }


def sample_template_csv() -> str:
    return (
        "Agent Name,Agent Code,FYC,Month\n"
        "Tim,A001,52000,2026-10\n"
        "Oscar,A002,38000,2026-10\n"
    )
