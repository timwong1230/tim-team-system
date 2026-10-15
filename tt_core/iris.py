"""TIM TEAM report import & sync.

Two report kinds:
1. Daily production → MTD-COMPLETION FYC → monthly_fyc[YYYY-MM]
2. MDRT Progress → Total Credit eligible for MDRT → monthly_fyc[MDRT_2027]

Team SC stays manual on the Dashboard. Never uses Monthly Submission as FYC.
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
)


def _get_clean_users():
    from tt_core.data import get_clean_users as _impl

    return _impl()


def _upd_fyc(*args, **kwargs):
    from tt_core.data import upd_fyc as _impl

    return _impl(*args, **kwargs)


def _read_data(*args, **kwargs):
    from tt_core.db import read_data as _impl

    return _impl(*args, **kwargs)


def _run_query_gs(*args, **kwargs):
    from tt_core.db import run_query_gs as _impl

    return _impl(*args, **kwargs)


# Inline fallbacks — Streamlit Cloud sometimes caches an older constants.py
try:
    from tt_core.constants import MDRT_CREDIT_ALIASES, MDRT_PROGRESS_MONTH_KEY
except Exception:  # pragma: no cover
    MDRT_CREDIT_ALIASES = [
        "total credit eligible for mdrt",
        "credit eligible for mdrt",
        "total credit eligible",
        "eligible for mdrt",
        "mdrt credit",
        "total mdrt credit",
        "mdrt total credit",
        "total credit",
    ]
    MDRT_PROGRESS_MONTH_KEY = "MDRT_2027"


def _norm(s: Any) -> str:
    """Normalize header text: casefold, treat _/- as spaces."""
    s = str(s or "").strip().lower()
    s = re.sub(r"[_\-]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


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


def _pdf_tables_to_df(raw: bytes) -> pd.DataFrame | None:
    """Best-effort table extract from MDRT / production PDFs."""
    try:
        import pdfplumber
    except Exception:
        return None

    tables: list[list[list[Any]]] = []
    try:
        with pdfplumber.open(io.BytesIO(raw)) as pdf:
            for page in pdf.pages:
                for table in page.extract_tables() or []:
                    if table and len(table) >= 2 and len(table[0]) >= 2:
                        tables.append(table)
    except Exception:
        return None
    if not tables:
        return None

    def _score(table: list[list[Any]]) -> tuple[int, int]:
        header = " ".join(str(c or "") for c in table[0]).lower()
        bonus = 0
        if "credit" in header or "mdrt" in header:
            bonus += 100
        if "agent" in header or "code" in header:
            bonus += 40
        if "completion" in header or "fyc" in header:
            bonus += 40
        return (bonus, len(table) * max(len(table[0]), 1))

    best = max(tables, key=_score)
    header = []
    for i, cell in enumerate(best[0]):
        label = str(cell or "").strip() or f"col{i}"
        header.append(label)
    # Deduplicate headers
    seen: dict[str, int] = {}
    clean_header = []
    for h in header:
        n = seen.get(h, 0)
        seen[h] = n + 1
        clean_header.append(h if n == 0 else f"{h}_{n}")
    rows = [[("" if c is None else str(c).strip()) for c in r] for r in best[1:]]
    # Normalize ragged rows
    width = len(clean_header)
    norm_rows = []
    for r in rows:
        if len(r) < width:
            r = r + [""] * (width - len(r))
        norm_rows.append(r[:width])
    df = pd.DataFrame(norm_rows, columns=clean_header)
    return df if not df.empty else None


def _pdf_text_to_df(raw: bytes) -> pd.DataFrame:
    """
    Parse MDRT Progress PDF text into Agent Code + Total Credit columns.
    Looks for lines containing an agent code (4–6 digits) and a money amount.
    """
    chunks: list[str] = []
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(raw))
        for page in reader.pages:
            chunks.append(page.extract_text() or "")
    except Exception as e:
        raise ValueError(f"無法讀取 PDF：{e}") from e

    text = "\n".join(chunks)
    if not text.strip():
        raise ValueError(
            "PDF 無文字層（可能係掃瞄圖）。請用可選取文字嘅 PDF，或匯出 Excel/CSV。"
        )

    rows: list[dict[str, str]] = []
    for line in text.splitlines():
        line = re.sub(r"[ \t]+", " ", (line or "").strip())
        if not line:
            continue
        low = line.lower()
        if "total credit eligible for mdrt" in low and not re.search(r"\d{4,}", line):
            continue
        codes = re.findall(r"\b(\d{4,6})\b", line)
        if not codes:
            continue
        # Money-like tokens; ignore bare years like 2026
        amounts = []
        for m in re.finditer(r"(?:HK\$|\$)?\s*(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+\.\d+|\d{3,})", line):
            token = m.group(1)
            if re.fullmatch(r"20\d{2}", token):
                continue
            if token in codes:
                continue
            amounts.append(token)
        if not amounts:
            continue
        code = codes[0]
        amount = amounts[-1]
        # Name = text before first code, if any
        name_part = line.split(code, 1)[0].strip(" |-:\t")
        rows.append(
            {
                "Agent Name": name_part,
                "Agent Code": code,
                "Total Credit eligible for MDRT": amount,
            }
        )

    if not rows:
        raise ValueError(
            "PDF 入面搵唔到 Agent Code + Total Credit。"
            "請確認係 MDRT Progress Report，或改用 Excel/CSV。"
        )
    # De-dupe by agent code, keep last (usually the totals row)
    df = pd.DataFrame(rows)
    df = df.drop_duplicates(subset=["Agent Code"], keep="last")
    return df.reset_index(drop=True)


def _flatten_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Flatten MultiIndex / Unnamed Excel headers into plain strings."""
    if isinstance(df.columns, pd.MultiIndex):
        flat = []
        for col in df.columns.values:
            parts = [str(p).strip() for p in col if str(p).strip() and not str(p).startswith("Unnamed")]
            flat.append(" ".join(parts) if parts else " ".join(str(p) for p in col))
        df = df.copy()
        df.columns = flat
    else:
        df = df.copy()
        df.columns = [str(c).strip() for c in df.columns]
    return df


def _pick_mtd_comp_column(columns: list[str]) -> str | None:
    """Hard-prefer MTD_Comp_FYC; never MTD_Sub_FYC."""
    exact = None
    soft: list[str] = []
    for c in columns:
        if _is_rejected(c, IRIS_FYC_REJECT_SUBSTR):
            continue
        n = _norm(c)
        compact = n.replace(" ", "")
        if compact in {"mtdcompfyc", "mtdcompletionfyc"} or n in {
            "mtd comp fyc",
            "mtd completion fyc",
            "mtd completion",
        }:
            exact = c
            break
        if ("comp" in n and "fyc" in n) or ("completion" in n and "mtd" in n):
            soft.append(c)
    return exact or (soft[0] if soft else None)


def _load_excel_bytes(raw: bytes) -> pd.DataFrame:
    """Pick the sheet/header row that contains MTD_Comp_FYC when possible."""
    xl = pd.ExcelFile(io.BytesIO(raw))
    candidates: list[tuple[int, int, pd.DataFrame]] = []
    for sheet in xl.sheet_names:
        for header in (0, 1, 2):
            try:
                df = xl.parse(sheet, header=header)
            except Exception:
                continue
            if df is None or df.empty or len(df.columns) < 2:
                continue
            df = _flatten_columns(df)
            # Drop fully empty columns
            df = df.dropna(axis=1, how="all")
            cols = [str(c) for c in df.columns]
            score = 0
            if _pick_mtd_comp_column(cols):
                score += 100
            if _find_col(cols, IRIS_CODE_ALIASES):
                score += 25
            if _find_col(cols, IRIS_AGENT_ALIASES):
                score += 10
            # Prefer wider production tables
            score += min(len(cols), 30)
            candidates.append((score, len(df), df))
    if not candidates:
        return _flatten_columns(xl.parse(xl.sheet_names[0]))
    candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return candidates[0][2]


def load_iris_bytes(raw: bytes, filename: str) -> pd.DataFrame:
    """Load report bytes (.xlsx / .xls / .csv / .pdf) into a DataFrame."""
    name = (filename or "").lower()
    bio = io.BytesIO(raw)

    if name.endswith(".pdf"):
        df = _pdf_tables_to_df(raw)
        if df is not None and not df.empty:
            # If table headers don't include MDRT credit wording, try to map
            cols_l = {_norm(c): c for c in df.columns}
            has_credit = any("credit" in k or "mdrt" in k for k in cols_l)
            has_code = any("code" in k or "agent" in k for k in cols_l)
            if has_credit or has_code:
                return df
        # Fallback: text line parser tuned for MDRT Progress PDFs
        return _pdf_text_to_df(raw)

    if name.endswith(".csv"):
        for enc in ("utf-8-sig", "utf-8", "cp950", "big5", "latin-1"):
            try:
                bio.seek(0)
                return _flatten_columns(pd.read_csv(bio, encoding=enc))
            except Exception:
                continue
        bio.seek(0)
        return _flatten_columns(pd.read_csv(bio))

    return _load_excel_bytes(raw)


def load_iris_file(uploaded_file) -> pd.DataFrame:
    """Load Iris export from a Streamlit uploader / file-like object."""
    name = getattr(uploaded_file, "name", "upload.xlsx")
    if hasattr(uploaded_file, "getvalue"):
        raw = uploaded_file.getvalue()
    else:
        raw = uploaded_file.read()
    if not raw:
        raise ValueError("檔案係空嘅")
    # Soft cap — oversized uploads OOM Streamlit Cloud into sticky Oh-no
    if len(raw) > 8 * 1024 * 1024:
        raise ValueError("檔案太大（上限 8MB）。請壓縮或用 Drive 同步。")
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
    Detect report columns.
    - fyc / monthly: MTD_Comp_FYC only (never MTD_Sub_FYC / Submission)
    - mdrt_credit: Total Credit eligible for MDRT
    - ytd: optional legacy YTD Completion (not used for Leaderboard)
    """
    cols = [str(c) for c in df.columns]
    agent = _find_col(cols, IRIS_AGENT_ALIASES)
    code = _find_col(cols, IRIS_CODE_ALIASES)
    month = _find_col(cols, IRIS_MONTH_ALIASES)

    mdrt_credit = _find_col(cols, MDRT_CREDIT_ALIASES, reject=IRIS_FYC_REJECT_SUBSTR)

    # 1) Hard-prefer MTD_Comp_FYC
    monthly = _pick_mtd_comp_column(cols)
    # 2) Alias list (still rejects Sub/Submission)
    if not monthly:
        monthly = _find_col(
            cols,
            IRIS_MONTHLY_COMPLETION_ALIASES,
            reject=IRIS_FYC_REJECT_SUBSTR,
        )
    # 3) Fallback FYC aliases — never Sub
    if not monthly:
        monthly = _find_col(cols, IRIS_FYC_ALIASES, reject=IRIS_FYC_REJECT_SUBSTR)
    # Final safety: if somehow landed on a Sub column, drop it
    if monthly and _is_rejected(monthly, IRIS_FYC_REJECT_SUBSTR):
        monthly = None

    ytd = _find_col(
        cols,
        IRIS_YTD_COMPLETION_ALIASES,
        reject=IRIS_FYC_REJECT_SUBSTR,
    )
    if ytd and monthly and ytd == monthly:
        other_cols = [c for c in cols if c != monthly]
        ytd = _find_col(
            other_cols,
            IRIS_YTD_COMPLETION_ALIASES,
            reject=IRIS_FYC_REJECT_SUBSTR,
        )

    # Many exports put Agent Code in a "name"/first column.
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
        "fyc": monthly,  # MTD-COMPLETION → that month's FYC
        "mdrt_credit": mdrt_credit,  # Total Credit eligible for MDRT
        "ytd": ytd,
        "month": month,
    }


def detect_report_kind(df: pd.DataFrame, filename: str = "") -> str:
    """Return 'mdrt', 'daily', or 'unknown' from columns / filename hints."""
    detected = detect_columns(df)
    if detected.get("mdrt_credit"):
        return "mdrt"
    if detected.get("fyc"):
        return "daily"
    name = (filename or "").lower()
    if "mdrt" in name and "progress" in name:
        return "mdrt"
    if "daily" in name or "production" in name or "mtd" in name:
        return "daily"
    return "unknown"


def auto_build_preview(
    df: pd.DataFrame,
    default_month: str,
    *,
    filename: str = "",
    report_kind: str | None = None,
) -> tuple[pd.DataFrame, dict]:
    """Detect columns/report kind and build sync preview."""
    detected = detect_columns(df)
    kind = (report_kind or detect_report_kind(df, filename)).lower()
    detected["report_kind"] = kind

    if kind == "mdrt":
        if not detected.get("mdrt_credit"):
            raise ValueError(
                "搵唔到「Total Credit eligible for MDRT」欄。"
                "請確認呢份係 MDRT Progress Report。"
            )
        preview = build_mdrt_preview(
            df,
            detected.get("agent"),
            detected.get("code"),
            detected["mdrt_credit"],
        )
        return preview, detected

    # daily (default)
    if not detected.get("fyc"):
        raise ValueError(
            "搵唔到 MTD_Comp_FYC 欄（當月 FYC）。"
            "請確認呢份係 Daily production report；系統唔會用 MTD_Sub_FYC / Submission。"
        )
    preview = build_sync_preview(
        df,
        detected.get("agent"),
        detected.get("code"),
        detected["fyc"],
        detected.get("month"),
        default_month,
        col_ytd=None,  # Leaderboard MDRT progress comes from MDRT report, not YTD
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
    df = _read_data("iris_agent_map")
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
    _run_query_gs("INSERT", "iris_agent_map", payload)


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
    users = _get_clean_users()
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


def build_mdrt_preview(
    df: pd.DataFrame,
    col_agent: str | None,
    col_code: str | None,
    col_credit: str,
) -> pd.DataFrame:
    """Preview MDRT Progress Report → temporary progress amounts."""
    agent_map = get_agent_map()
    users = _get_clean_users()
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
        amount = parse_amount(r[col_credit]) if col_credit else 0.0
        username = resolve_username(agent, code, agent_map, users)
        rows.append(
            {
                "iris_name": agent,
                "iris_code": code,
                "username": username or "",
                "month": MDRT_PROGRESS_MONTH_KEY,
                "amount": amount,
                "ytd_amount": 0.0,
                "matched": bool(username),
                "report_kind": "mdrt",
            }
        )

    preview = pd.DataFrame(rows)
    if preview.empty:
        return preview

    grouped = (
        preview.groupby(
            ["iris_name", "iris_code", "username", "month", "matched", "report_kind"],
            dropna=False,
        )
        .agg(amount=("amount", "max"), ytd_amount=("ytd_amount", "max"))
        .reset_index()
    )
    return grouped.sort_values(by=["matched", "amount"], ascending=[False, False])


def apply_sync(preview: pd.DataFrame, synced_by: str, filename: str) -> dict[str, Any]:
    """
    Write Daily production MTD-COMPLETION → monthly_fyc[YYYY-MM].
    Does not touch Leaderboard MDRT progress or Team SC.
    """
    matched = preview[preview["matched"] & (preview["username"] != "")].copy()
    updated = 0
    for _, row in matched.iterrows():
        month = str(row.get("month") or "")
        if month == MDRT_PROGRESS_MONTH_KEY:
            continue
        _upd_fyc(row["username"], month, float(row["amount"]), source="daily_production")
        updated += 1

    months = sorted(
        m for m in matched["month"].astype(str).unique().tolist() if m != MDRT_PROGRESS_MONTH_KEY
    ) if not matched.empty else []
    note = f"kind=daily; months={','.join(months)}; col=MTD-COMPLETION"
    _run_query_gs(
        "INSERT",
        "iris_sync_log",
        {
            "synced_at": str(datetime.datetime.now()),
            "synced_by": synced_by,
            "month": months[0] if len(months) == 1 else ("multi" if months else ""),
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
        "ytd_updated": 0,
        "mdrt_updated": 0,
        "report_kind": "daily",
        "matched_users": int(matched["username"].nunique()) if not matched.empty else 0,
        "unmatched": int((~preview["matched"]).sum()) if not preview.empty else 0,
        "months": months,
    }


def apply_mdrt_sync(preview: pd.DataFrame, synced_by: str, filename: str) -> dict[str, Any]:
    """Write MDRT Total Credit eligible → monthly_fyc[MDRT_2027] (Leaderboard progress)."""
    matched = preview[preview["matched"] & (preview["username"] != "")].copy()
    updated = 0
    for _, row in matched.iterrows():
        _upd_fyc(
            row["username"],
            MDRT_PROGRESS_MONTH_KEY,
            float(row["amount"]),
            source="mdrt_progress",
        )
        updated += 1

    note = f"kind=mdrt; key={MDRT_PROGRESS_MONTH_KEY}; col=Total Credit eligible for MDRT"
    _run_query_gs(
        "INSERT",
        "iris_sync_log",
        {
            "synced_at": str(datetime.datetime.now()),
            "synced_by": synced_by,
            "month": MDRT_PROGRESS_MONTH_KEY,
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
        "ytd_updated": 0,
        "mdrt_updated": updated,
        "report_kind": "mdrt",
        "matched_users": int(matched["username"].nunique()) if not matched.empty else 0,
        "unmatched": int((~preview["matched"]).sum()) if not preview.empty else 0,
        "months": [MDRT_PROGRESS_MONTH_KEY] if updated else [],
    }


def apply_report_sync(
    preview: pd.DataFrame,
    synced_by: str,
    filename: str,
    report_kind: str | None = None,
) -> dict[str, Any]:
    """Dispatch sync by report kind."""
    kind = (report_kind or "").lower()
    if not kind and not preview.empty and "report_kind" in preview.columns:
        kind = str(preview.iloc[0].get("report_kind") or "").lower()
    if not kind and not preview.empty and "month" in preview.columns:
        if str(preview.iloc[0].get("month")) == MDRT_PROGRESS_MONTH_KEY:
            kind = "mdrt"
    if kind == "mdrt":
        return apply_mdrt_sync(preview, synced_by, filename)
    return apply_sync(preview, synced_by, filename)


def sample_template_csv() -> str:
    """Daily production template (MTD_Comp_FYC → monthly FYC)."""
    return (
        "Agent Name,Agent Code,MTD_Sub_FYC,MTD_Comp_FYC,Month\n"
        "Tim,30947,60000,52000,2026-10\n"
        "Oscar,59164,40000,10000,2026-10\n"
    )


def sample_mdrt_template_csv() -> str:
    """MDRT Progress template (Total Credit eligible for MDRT)."""
    return (
        "Agent Name,Agent Code,Total Credit eligible for MDRT\n"
        "Tim,30947,398944\n"
        "Oscar,59164,162848\n"
    )
