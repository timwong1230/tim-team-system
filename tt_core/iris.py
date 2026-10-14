"""FWD Iris production report import & sync.

Uses Monthly Completion for that month's FYC, and YTD Completion for
year-to-date / Team FYC totals. Never uses Monthly Submission.
"""

from __future__ import annotations

import datetime
import io
import re
from typing import Any

import pandas as pd

from tt_core.constants import (
    IRIS_AGENT_ALIASES,
    IRIS_CODE_ALIASES,
    IRIS_FYC_ALIASES,
    IRIS_FYC_REJECT_SUBSTR,
    IRIS_MONTH_ALIASES,
    IRIS_MONTHLY_COMPLETION_ALIASES,
    IRIS_YTD_COMPLETION_ALIASES,
    IRIS_YTD_MONTH_KEY,
)
from tt_core.data import get_clean_users, upd_fyc
from tt_core.db import read_data, run_query_gs


def _norm(s: Any) -> str:
    return re.sub(r"\s+", " ", str(s or "").strip().lower())


def _is_rejected(col_name: str, reject: list[str] | None) -> bool:
    if not reject:
        return False
    n = _norm(col_name)
    return any(r in n for r in reject)


def _find_col(
    columns: list[str],
    aliases: list[str],
    *,
    reject: list[str] | None = None,
) -> str | None:
    normalized = {_norm(c): c for c in columns}
    for alias in aliases:
        if alias in normalized and not _is_rejected(normalized[alias], reject):
            return normalized[alias]
    for alias in aliases:
        for ncol, original in normalized.items():
            if alias in ncol and not _is_rejected(original, reject):
                return original
    return None


def load_iris_bytes(raw: bytes, filename: str) -> pd.DataFrame:
    """Load Iris export bytes (.xlsx / .xls / .csv) into a DataFrame."""
    name = (filename or "").lower()
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

    bio.seek(0)
    xl = pd.ExcelFile(bio)
    for sheet in xl.sheet_names:
        df = xl.parse(sheet)
        if not df.empty and len(df.columns) >= 2:
            return df
    return xl.parse(xl.sheet_names[0])


def load_iris_file(uploaded_file) -> pd.DataFrame:
    """Load Iris export from a Streamlit uploader / file-like object."""
    name = getattr(uploaded_file, "name", "upload.xlsx")
    raw = uploaded_file.read()
    return load_iris_bytes(raw, name)


def _mostly_agent_codes(series: pd.Series, threshold: float = 0.7) -> bool:
    """True when values look like Iris agent numbers (e.g. 30947)."""
    s = series.dropna().astype(str).str.strip()
    s = s[s != ""]
    if s.empty:
        return False
    return bool(s.str.match(r"^\d{4,}$").mean() >= threshold)


def detect_columns(df: pd.DataFrame) -> dict[str, str | None]:
    """
    Detect Iris columns.
    - fyc / monthly: Monthly Completion (never Submission)
    - ytd: YTD Completion
    """
    cols = [str(c) for c in df.columns]
    agent = _find_col(cols, IRIS_AGENT_ALIASES)
    code = _find_col(cols, IRIS_CODE_ALIASES)
    month = _find_col(cols, IRIS_MONTH_ALIASES)

    # 1) Prefer explicit Monthly Completion
    monthly = _find_col(
        cols,
        IRIS_MONTHLY_COMPLETION_ALIASES,
        reject=IRIS_FYC_REJECT_SUBSTR,
    )
    # 2) Fallback FYC aliases, still reject submission
    if not monthly:
        monthly = _find_col(cols, IRIS_FYC_ALIASES, reject=IRIS_FYC_REJECT_SUBSTR)

    ytd = _find_col(
        cols,
        IRIS_YTD_COMPLETION_ALIASES,
        reject=IRIS_FYC_REJECT_SUBSTR,
    )
    # Don't use the same column for both
    if ytd and monthly and ytd == monthly:
        # If only one completion-like column matched both lists, keep monthly
        # and try a stricter YTD-only pass excluding that column
        other_cols = [c for c in cols if c != monthly]
        ytd = _find_col(
            other_cols,
            IRIS_YTD_COMPLETION_ALIASES,
            reject=IRIS_FYC_REJECT_SUBSTR,
        )

    # Many Iris team exports put Agent Code in a "name"/first column.
    if agent and not code and agent in df.columns and _mostly_agent_codes(df[agent]):
        code, agent = agent, None
    elif (
        agent
        and code
        and agent in df.columns
        and _mostly_agent_codes(df[agent])
        and not _mostly_agent_codes(df[code])
    ):
        agent, code = code, agent

    return {
        "agent": agent,
        "code": code,
        "fyc": monthly,  # monthly completion → that month's FYC
        "ytd": ytd,  # ytd completion → Team FYC / yearly
        "month": month,
    }


def auto_build_preview(df: pd.DataFrame, default_month: str) -> tuple[pd.DataFrame, dict]:
    """Detect columns and build sync preview in one step."""
    detected = detect_columns(df)
    if not detected.get("fyc") and not detected.get("ytd"):
        raise ValueError(
            "搵唔到 Monthly Completion / YTD Completion 欄。"
            "請確認檔案有呢兩欄（唔好用 Monthly Submission），"
            "或改用手動上傳並自己揀欄。"
        )
    if not detected.get("fyc"):
        raise ValueError(
            "搵唔到 Monthly Completion 欄（當月 FYC）。"
            "系統唔會用 Monthly Submission。"
        )
    preview = build_sync_preview(
        df,
        detected.get("agent"),
        detected.get("code"),
        detected["fyc"],
        detected.get("month"),
        default_month,
        col_ytd=detected.get("ytd"),
    )
    return preview, detected


def unmapped_agents(preview: pd.DataFrame) -> pd.DataFrame:
    """Unique unmatched Iris agents (for mapping UI)."""
    if preview is None or preview.empty:
        return pd.DataFrame(columns=["iris_name", "iris_code", "amount"])
    u = preview[~preview["matched"]].copy()
    if u.empty:
        return pd.DataFrame(columns=["iris_name", "iris_code", "amount"])
    return (
        u.groupby(["iris_name", "iris_code"], dropna=False)["amount"]
        .max()
        .reset_index()
        .sort_values(by="amount", ascending=False)
    )


def preview_summary(preview: pd.DataFrame) -> dict[str, Any]:
    if preview is None or preview.empty:
        return {
            "matched_rows": 0,
            "unmatched_rows": 0,
            "matched_users": 0,
            "unmapped_agents": 0,
        }
    matched = preview[preview["matched"]]
    return {
        "matched_rows": int(len(matched)),
        "unmatched_rows": int((~preview["matched"]).sum()),
        "matched_users": int(matched["username"].nunique()) if not matched.empty else 0,
        "unmapped_agents": int(len(unmapped_agents(preview))),
    }


def normalize_month(value: Any, fallback: str) -> str:
    """Normalize various month formats to YYYY-MM."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return fallback
    s = str(value).strip()
    if not s or s.lower() in {"nan", "none"}:
        return fallback

    m = re.match(r"^(\d{4})[-/](\d{1,2})$", s)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}"

    m = re.match(r"^(\d{4})(\d{2})$", s)
    if m:
        return f"{m.group(1)}-{m.group(2)}"

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

    match = pd.DataFrame()
    if not df.empty:
        if iris_code:
            match = df[df["iris_code"].astype(str).str.strip() == iris_code]
        if match.empty and iris_name:
            match = df[
                df["iris_name"].astype(str).str.strip().str.lower() == iris_name.lower()
            ]

    payload = {
        "iris_name": iris_name,
        "iris_code": iris_code,
        "username": username,
        "notes": notes,
    }
    if not match.empty:
        from tt_core.db import get_sheet, clear_cache

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


def resolve_username(
    iris_name: str, iris_code: str, agent_map: pd.DataFrame, users: pd.DataFrame
) -> str | None:
    name = str(iris_name or "").strip()
    code = str(iris_code or "").strip()

    if name and re.fullmatch(r"\d{4,}", name) and not code:
        code = name

    if not agent_map.empty:
        if code:
            hit = agent_map[agent_map["iris_code"].astype(str).str.strip() == code]
            if not hit.empty and str(hit.iloc[0]["username"]).strip():
                return str(hit.iloc[0]["username"]).strip()
            hit = agent_map[agent_map["iris_name"].astype(str).str.strip() == code]
            if not hit.empty and str(hit.iloc[0]["username"]).strip():
                return str(hit.iloc[0]["username"]).strip()
        if name and not re.fullmatch(r"\d{4,}", name):
            hit = agent_map[
                agent_map["iris_name"].astype(str).str.strip().str.lower() == name.lower()
            ]
            if not hit.empty and str(hit.iloc[0]["username"]).strip():
                return str(hit.iloc[0]["username"]).strip()

    if not users.empty and name and not re.fullmatch(r"\d{4,}", name):
        hit = users[users["username"].astype(str).str.lower() == name.lower()]
        if not hit.empty:
            return str(hit.iloc[0]["username"])
        hit = users[
            users["username"]
            .astype(str)
            .str.lower()
            .apply(lambda u: u in name.lower() or name.lower() in u)
        ]
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
    col_ytd: str | None = None,
) -> pd.DataFrame:
    """Preview with monthly completion (+ optional YTD completion)."""
    agent_map = get_agent_map()
    users = get_clean_users()
    users = users[users["role"] == "Member"]

    rows = []
    for _, r in df.iterrows():
        agent = str(r[col_agent]).strip() if col_agent else ""
        code = str(r[col_code]).strip() if col_code else ""
        if agent in {"nan", "None"}:
            agent = ""
        if code in {"nan", "None"}:
            code = ""
        if agent and re.fullmatch(r"\d{4,}", agent) and not code:
            code, agent = agent, ""
        amount = parse_amount(r[col_fyc]) if col_fyc else 0.0
        ytd_amount = parse_amount(r[col_ytd]) if col_ytd else 0.0
        month_raw = r[col_month] if col_month else default_month
        month = normalize_month(month_raw, default_month)
        username = resolve_username(agent, code, agent_map, users)
        rows.append(
            {
                "iris_name": agent,
                "iris_code": code,
                "username": username or "",
                "month": month,
                "amount": amount,  # monthly completion
                "ytd_amount": ytd_amount,  # ytd completion
                "matched": bool(username),
            }
        )

    preview = pd.DataFrame(rows)
    if preview.empty:
        return preview

    # Agent-level totals: use max to avoid double-counting duplicate rows
    grouped = (
        preview.groupby(
            ["iris_name", "iris_code", "username", "month", "matched"], dropna=False
        )
        .agg(amount=("amount", "max"), ytd_amount=("ytd_amount", "max"))
        .reset_index()
    )
    return grouped.sort_values(by=["matched", "amount"], ascending=[False, False])


def apply_sync(preview: pd.DataFrame, synced_by: str, filename: str) -> dict[str, Any]:
    """
    Write:
    - monthly completion → monthly_fyc[selected month]
    - ytd completion → monthly_fyc[YTD]  (used for Team FYC / yearly)
    """
    matched = preview[preview["matched"] & (preview["username"] != "")].copy()
    updated = 0
    ytd_updated = 0
    has_ytd = "ytd_amount" in matched.columns
    for _, row in matched.iterrows():
        upd_fyc(row["username"], row["month"], float(row["amount"]), source="iris")
        updated += 1
        if has_ytd:
            upd_fyc(
                row["username"],
                IRIS_YTD_MONTH_KEY,
                float(row["ytd_amount"] or 0),
                source="iris_ytd",
            )
            ytd_updated += 1

    months = sorted(matched["month"].unique().tolist()) if not matched.empty else []
    note = f"months={','.join(months)}; monthly=completion; ytd_rows={ytd_updated}"
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
        "ytd_updated": ytd_updated,
        "matched_users": int(matched["username"].nunique()) if not matched.empty else 0,
        "unmatched": int((~preview["matched"]).sum()) if not preview.empty else 0,
        "months": months,
    }


def sample_template_csv() -> str:
    return (
        "Agent Name,Agent Code,Monthly Submission,Monthly Completion,YTD Completion,Month\n"
        "Tim,A001,60000,52000,397457,2026-10\n"
        "Oscar,A002,40000,38000,162848,2026-10\n"
    )
