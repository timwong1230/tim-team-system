"""Push Daily_Sales / Bank_Entries / Bank_Evidence rows to the Finance Google Sheet.

Env:
  POLAR_DAILY_SALES_SHEET_ID — Finance spreadsheet id
  POLAR_DAILY_SALES_WORKSHEET — tab name (default Daily_Sales)
  POLAR_BANK_ENTRIES_WORKSHEET — tab name (default Bank_Entries)
  POLAR_BANK_EVIDENCE_WORKSHEET — tab name (default Bank_Evidence)
  POLAR_BANK_EVIDENCE_FOLDER_ID — Drive folder for screenshot mirrors
  POLAR_GSPREAD_KEY or GSPREAD_KEY — service account JSON
"""

from __future__ import annotations

import json
import os
import re
from datetime import date, datetime, timedelta
from typing import Any

DAILY_SALES_HEADERS: tuple[str, ...] = (
    "business_date",
    "Cash",
    "Visa",
    "Master",
    "AE",
    "Alipay",
    "UnionPay",
    "WeChat pay",
    "Deposit",
    "Claim",
    "Daily Sales",
    "Cash Tilt",
    "Monthly Total",
    "synced_at",
)

BANK_ENTRY_HEADERS: tuple[str, ...] = (
    "date",
    "memo",
    "chq_no",
    "hsbc_sa",
    "hsbc_ca",
    "nature",
    "account_code",
    "linked_sales_date",
    "notes",
)

BANK_EVIDENCE_HEADERS: tuple[str, ...] = (
    "uploaded_at",
    "txn_date",
    "amount_hint",
    "note",
    "filename",
    "evidence_id",
    "drive_url",
    "file_id",
)

_SCOPES = (
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
)


class SheetsNotConfigured(RuntimeError):
    """Missing sheet id or service-account credentials."""


# Known Finance workbook — used when Render env forgot POLAR_DAILY_SALES_SHEET_ID.
DEFAULT_DAILY_SALES_SHEET_ID = "1WRTjFrzLXvL0OTWv-FE8uPF-UWBSFJe6gNuFnB9cF-I"


def sheets_configured() -> bool:
    try:
        return sheets_config_gap() is None
    except SheetsNotConfigured:
        return False


def format_sheets_error(exc: BaseException) -> str:
    """Human-readable Sheets/Google error — never return a blank string."""
    parts: list[str] = []
    cur: BaseException | None = exc
    for _ in range(5):
        if cur is None:
            break
        name = type(cur).__name__
        msg = (str(cur) or "").strip()
        resp = getattr(cur, "resp", None)
        status = getattr(resp, "status", None) if resp is not None else None
        reason = getattr(resp, "reason", None) if resp is not None else None
        content = getattr(cur, "content", None)
        bit = f"{name}"
        if status:
            bit += f" HTTP {status}"
        if reason:
            bit += f" ({reason})"
        if msg:
            bit += f": {msg}"
        parts.append(bit)
        if isinstance(content, (bytes, bytearray)):
            parts.append(content.decode("utf-8", errors="replace")[:400])
        elif isinstance(content, str) and content.strip():
            parts.append(content.strip()[:400])
        # gspread APIError often nests the response JSON in .args
        if not msg and getattr(cur, "args", None):
            parts.append(repr(cur.args)[:400])
        cur = cur.__cause__ or cur.__context__
    text = " | ".join(p for p in parts if p).strip()
    return text or f"{type(exc).__name__}: (no message — check Sheets API enabled + SA Editor share)"


def sheets_status(*, probe: bool = False) -> dict[str, Any]:
    """Staff-safe diagnostics (no secrets)."""
    gap = sheets_config_gap()
    raw = _raw_credentials_text()
    parsed_ok = False
    client_email = None
    private_key_ok = False
    if raw:
        try:
            data = _parse_credentials_json(raw)
            parsed_ok = isinstance(data, dict)
            if parsed_ok:
                client_email = str(data.get("client_email") or "") or None
                pk = str(data.get("private_key") or "")
                private_key_ok = (
                    "BEGIN PRIVATE KEY" in pk and "\n" in pk and "END PRIVATE KEY" in pk
                )
        except SheetsNotConfigured:
            parsed_ok = False
    out: dict[str, Any] = {
        "ready": gap is None,
        "gap": gap,
        "has_sheet_id": bool(_sheet_id()),
        "sheet_id_suffix": (_sheet_id()[-8:] if _sheet_id() else None),
        "has_credentials_env": bool(raw),
        "credentials_parse_ok": parsed_ok,
        "private_key_looks_ok": private_key_ok,
        "service_account_email": client_email,
    }
    if probe and gap is None:
        try:
            spreadsheet = _open_spreadsheet()
            titles = [ws.title for ws in spreadsheet.worksheets()[:12]]
            out["probe_ok"] = True
            out["spreadsheet_title"] = spreadsheet.title
            out["worksheets"] = titles
        except Exception as exc:  # noqa: BLE001
            out["probe_ok"] = False
            out["probe_error"] = format_sheets_error(exc)
    return out


def sheets_config_gap() -> str | None:
    """Why Google Sheet sync is off, or None when ready.

    Shown on Staff Reports so disabled Sync / bank upload is not a silent dead tap.
    """
    if not _sheet_id():
        return "缺少 POLAR_DAILY_SALES_SHEET_ID（Render Environment）"
    raw = _raw_credentials_text()
    if not raw:
        return (
            "缺少 POLAR_GSPREAD_KEY（Render → polar-order → Environment → Edit，"
            "Key 名要完全係 POLAR_GSPREAD_KEY，Value 貼成份 JSON，Save 後 Manual Deploy）"
        )
    try:
        data = _parse_credentials_json(raw)
    except SheetsNotConfigured as exc:
        return str(exc)
    if not (data.get("client_email") and data.get("private_key")):
        return "POLAR_GSPREAD_KEY 缺少 client_email / private_key"
    return None


def _sheet_id() -> str:
    return (
        (os.getenv("POLAR_DAILY_SALES_SHEET_ID") or "").strip()
        or DEFAULT_DAILY_SALES_SHEET_ID
    )


def _raw_credentials_text() -> str:
    return (os.getenv("POLAR_GSPREAD_KEY") or os.getenv("GSPREAD_KEY") or "").strip()


def _parse_credentials_json(raw: str) -> dict[str, Any]:
    """Parse service-account JSON; tolerate common Render paste issues."""
    text = (raw or "").strip()
    if not text:
        raise SheetsNotConfigured("POLAR_GSPREAD_KEY is empty")
    # Smart quotes / BOM from phone copy-paste
    text = (
        text.replace("\ufeff", "")
        .replace("“", '"')
        .replace("”", '"')
        .replace("‘", "'")
        .replace("’", "'")
    )
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Sometimes the whole JSON is stored as a quoted string.
        try:
            data = json.loads(json.loads(text))
        except json.JSONDecodeError as exc:
            raise SheetsNotConfigured(
                "POLAR_GSPREAD_KEY 唔係有效 JSON（可能被截斷，或唔係由 { 開始到 }）"
            ) from exc
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError as exc:
            raise SheetsNotConfigured(
                "POLAR_GSPREAD_KEY 唔係有效 JSON object"
            ) from exc
    if not isinstance(data, dict):
        raise SheetsNotConfigured("POLAR_GSPREAD_KEY 必須係 JSON object")
    return _normalize_service_account(data)


def _normalize_service_account(data: dict[str, Any]) -> dict[str, Any]:
    """Fix private_key newlines mangled by env-var paste."""
    pk = data.get("private_key")
    if not isinstance(pk, str) or "BEGIN" not in pk:
        return data
    fixed = pk
    # Double-escaped \\n left as two chars breaks Google auth.
    if "\\n" in fixed:
        fixed = fixed.replace("\\n", "\n")
    # Some pastes use literal "\n" with spaces removed incorrectly.
    if "-----BEGIN" in fixed and "\n" not in fixed and " " in fixed:
        fixed = fixed.replace("-----BEGIN PRIVATE KEY----- ", "-----BEGIN PRIVATE KEY-----\n")
        fixed = fixed.replace(" -----END PRIVATE KEY-----", "\n-----END PRIVATE KEY-----\n")
    if fixed != pk:
        data = {**data, "private_key": fixed}
    return data


def _daily_worksheet_title() -> str:
    return (os.getenv("POLAR_DAILY_SALES_WORKSHEET") or "Daily_Sales").strip() or "Daily_Sales"


def _bank_worksheet_title() -> str:
    return (os.getenv("POLAR_BANK_ENTRIES_WORKSHEET") or "Bank_Entries").strip() or "Bank_Entries"


def _evidence_worksheet_title() -> str:
    return (
        (os.getenv("POLAR_BANK_EVIDENCE_WORKSHEET") or "Bank_Evidence").strip()
        or "Bank_Evidence"
    )


def evidence_folder_id() -> str:
    return (os.getenv("POLAR_BANK_EVIDENCE_FOLDER_ID") or "").strip()


def _credentials_dict() -> dict[str, Any] | None:
    raw = _raw_credentials_text()
    if not raw:
        return None
    return _parse_credentials_json(raw)


def _gspread_client():
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError as exc:
        raise SheetsNotConfigured(
            "gspread/google-auth not installed on this server"
        ) from exc

    key = _credentials_dict()
    sheet_id = _sheet_id()
    if not key or not sheet_id:
        raise SheetsNotConfigured(
            "Set POLAR_DAILY_SALES_SHEET_ID and POLAR_GSPREAD_KEY "
            "(Google service account JSON)"
        )

    creds = Credentials.from_service_account_info(key, scopes=list(_SCOPES))
    return gspread.authorize(creds), sheet_id


def _open_spreadsheet():
    client, sheet_id = _gspread_client()
    return client.open_by_key(sheet_id)


def _open_named_worksheet(title: str, header_first: str):
    import gspread

    spreadsheet = _open_spreadsheet()
    worksheet = None
    try:
        worksheet = spreadsheet.worksheet(title)
    except gspread.WorksheetNotFound:
        for candidate in spreadsheet.worksheets():
            row = candidate.row_values(1)
            if row and row[0].strip() == header_first:
                worksheet = candidate
                break
            # Template put headers below a title block — scan early rows.
            for r in range(1, 12):
                vals = candidate.row_values(r)
                if vals and vals[0].strip() == header_first:
                    worksheet = candidate
                    break
            if worksheet is not None:
                break
        if worksheet is None:
            worksheet = spreadsheet.sheet1

    if worksheet.title != title:
        try:
            worksheet.update_title(title)
        except Exception:
            pass
    return worksheet


def _header_row_index(worksheet, expected_headers: tuple[str, ...]) -> int:
    """1-based row where the header starts (first cell matches expected[0])."""
    needle = expected_headers[0]
    for r in range(1, 16):
        vals = worksheet.row_values(r)
        if not vals:
            continue
        if vals[0].strip() == needle:
            # Prefer exact header match when possible.
            if [v.strip() for v in vals[: len(expected_headers)]] == list(expected_headers):
                return r
            return r
    return 1


def _ensure_headers(worksheet, expected_headers: tuple[str, ...]) -> int:
    row = _header_row_index(worksheet, expected_headers)
    current = worksheet.row_values(row)
    if [c.strip() for c in current[: len(expected_headers)]] == list(expected_headers):
        return row
    worksheet.update(
        f"A{row}",
        [list(expected_headers)],
        value_input_option="RAW",
    )
    return row


def _daily_row_values(row: dict[str, Any]) -> list[Any]:
    out: list[Any] = []
    for key in DAILY_SALES_HEADERS:
        val = row.get(key, "")
        if key == "business_date" or key == "synced_at":
            out.append(str(val or ""))
        else:
            try:
                out.append(float(val or 0))
            except (TypeError, ValueError):
                out.append(0)
    return out


def _biz_date_candidates(val: Any) -> set[str]:
    """Possible YYYY-MM-DD readings of a sheet date cell (locale-safe)."""
    out: set[str] = set()
    if val is None:
        return out
    if isinstance(val, datetime):
        out.add(val.date().isoformat())
        return out
    if isinstance(val, date):
        out.add(val.isoformat())
        return out
    s = str(val).strip()
    if not s:
        return out
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y"):
        try:
            out.add(datetime.strptime(s[:10], fmt).date().isoformat())
        except ValueError:
            pass
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", s)
    if m:
        a, b, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        for month, day in ((a, b), (b, a)):  # m/d/y and d/m/y
            try:
                out.add(date(y, month, day).isoformat())
            except ValueError:
                pass
    try:
        n = float(s)
        if 20000 < n < 80000:
            out.add((date(1899, 12, 30) + timedelta(days=int(n))).isoformat())
    except ValueError:
        pass
    m2 = re.match(r"^(\d{4}-\d{2}-\d{2})", s)
    if m2:
        out.add(m2.group(1))
    return out


def _find_biz_date_row(worksheet, header_row: int, biz: str) -> int | None:
    """1-based sheet row of an existing business_date under the header, else None."""
    col_a = worksheet.col_values(1)
    for idx in range(header_row, len(col_a)):
        if biz in _biz_date_candidates(col_a[idx]):
            return idx + 1
    return None


def _next_daily_sales_row(worksheet, header_row: int) -> int:
    """First empty row under Daily_Sales headers (do not use append_row)."""
    col_a = worksheet.col_values(1)
    last = header_row
    for idx in range(header_row, len(col_a)):
        if str(col_a[idx] or "").strip():
            last = idx + 1
    return last + 1


def upsert_daily_sales_row(row: dict[str, Any]) -> dict[str, Any]:
    """Insert or update the Daily_Sales row for row['business_date'].

    Finance template has title rows then headers on row 4 — never use bare
    append_row (it can land far below helper columns / miss date matching).
    """
    biz = str(row.get("business_date") or "").strip()
    if not biz:
        raise ValueError("business_date is required")

    worksheet = _open_named_worksheet(_daily_worksheet_title(), "business_date")
    header_row = _ensure_headers(worksheet, DAILY_SALES_HEADERS)
    values = _daily_row_values(row)

    existing = _find_biz_date_row(worksheet, header_row, biz)
    if existing:
        sheet_row = existing
        action = "updated"
    else:
        sheet_row = _next_daily_sales_row(worksheet, header_row)
        action = "appended"

    worksheet.update(
        f"A{sheet_row}",
        [values],
        value_input_option="RAW",
    )

    return {
        "ok": True,
        "action": action,
        "business_date": biz,
        "sheet_id": _sheet_id(),
        "worksheet": worksheet.title,
        "header_row": header_row,
        "sheet_row": sheet_row,
        "row": {h: values[i] for i, h in enumerate(DAILY_SALES_HEADERS)},
    }


def append_bank_entries(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """Append bank rows; skip fingerprints already present in notes/memo+date+amount."""
    from .bank_import import rows_for_sheet

    if not entries:
        return {"ok": True, "added": 0, "skipped": 0, "worksheet": _bank_worksheet_title()}

    worksheet = _open_named_worksheet(_bank_worksheet_title(), "date")
    header_row = _ensure_headers(worksheet, BANK_ENTRY_HEADERS)

    # Build existing fingerprints from date|memo|sa|ca
    existing: set[str] = set()
    all_vals = worksheet.get_all_values()
    data_rows = all_vals[header_row:] if len(all_vals) >= header_row else []
    for r in data_rows:
        if len(r) < 6:
            continue
        d, memo = (r[0] or "").strip(), (r[1] or "").strip()
        sa, ca = (r[3] or "").strip(), (r[4] or "").strip()
        if not d or not memo:
            continue
        amt = sa or ca or "0"
        acct = "hsbc_sa" if sa else "hsbc_ca"
        try:
            amt_f = float(amt)
        except ValueError:
            amt_f = 0.0
        existing.add(f"{d}|{memo}|{amt_f:.2f}|{acct}")

    to_add: list[dict[str, Any]] = []
    skipped = 0
    for e in entries:
        fp = e.get("fingerprint") or ""
        if fp and fp in existing:
            skipped += 1
            continue
        to_add.append(e)
        if fp:
            existing.add(fp)

    if to_add:
        worksheet.append_rows(rows_for_sheet(to_add), value_input_option="USER_ENTERED")

    return {
        "ok": True,
        "added": len(to_add),
        "skipped": skipped,
        "sheet_id": _sheet_id(),
        "worksheet": _bank_worksheet_title(),
    }


def append_bank_evidence(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Append Bank_Evidence metadata rows (create tab/headers if needed)."""
    if not rows:
        return {
            "ok": True,
            "added": 0,
            "worksheet": _evidence_worksheet_title(),
        }

    title = _evidence_worksheet_title()
    spreadsheet = _open_spreadsheet()
    import gspread

    try:
        worksheet = spreadsheet.worksheet(title)
    except gspread.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(title=title, rows=2000, cols=len(BANK_EVIDENCE_HEADERS))

    header_row = _ensure_headers(worksheet, BANK_EVIDENCE_HEADERS)
    values = [
        [str(r.get(h, "") or "") for h in BANK_EVIDENCE_HEADERS]
        for r in rows
    ]
    # Prefer append below last used row.
    worksheet.append_rows(values, value_input_option="USER_ENTERED")
    return {
        "ok": True,
        "added": len(values),
        "header_row": header_row,
        "sheet_id": _sheet_id(),
        "worksheet": title,
    }


CHART_OF_ACCOUNTS_ROWS: tuple[tuple[Any, ...], ...] = (
    ("Chart of Accounts", "", "", "", "", ""),
    ("Bank_Entries 嘅 Nature 必須用呢度嘅名稱（下拉），先會入到 P&L / BS。", "", "", "", "", ""),
    ("", "", "", "", "", ""),
    ("account_code", "nature", "type", "pl_section", "bs_section", "notes"),
    ("1000", "HSBC SA", "Asset", "", "Current assets", "Savings"),
    ("1010", "HSBC CA", "Asset", "", "Current assets", "Current account"),
    ("1100", "Cash on hand", "Asset", "", "Current assets", "Till / float（參考 Cash Tilt）"),
    ("1200", "Deposits held", "Asset", "", "Non-current assets", "租約／水電按金"),
    ("3000", "Partner capital", "Equity", "", "Equity", "開業資本"),
    ("3100", "Partner drawings", "Equity", "", "Equity", "股東提取"),
    ("3200", "Partner cash in", "Equity", "", "Equity", "股東注資（銀行入數）"),
    ("4000", "Sales", "Revenue", "Sales", "", "銀行入數標 Sales；日銷售亦由 Daily_Sales 計"),
    ("5000", "Drink / Alcohol", "COGS", "COGS", "", "酒水採購"),
    ("5010", "Shisha stock", "COGS", "COGS", "", "水煙原料"),
    ("5020", "Nuts / snacks", "COGS", "COGS", "", "小食"),
    ("5030", "Wine cost", "COGS", "COGS", "", "葡萄酒進貨"),
    ("5090", "Other COGS", "COGS", "COGS", "", "其他進貨"),
    ("6000", "Rent", "Expense", "Operating expenses", "", ""),
    ("6010", "Management fee", "Expense", "Operating expenses", "", ""),
    ("6020", "Rates (差餉)", "Expense", "Operating expenses", "", ""),
    ("6100", "Wages", "Expense", "Staff costs", "", "人工／外勞"),
    ("6200", "Electricity", "Expense", "Utilities", "", "HKE"),
    ("6210", "Water", "Expense", "Utilities", "", ""),
    ("6220", "Internet", "Expense", "Utilities", "", "HKBN"),
    ("6300", "Marketing fee", "Expense", "Operating expenses", "", ""),
    ("6400", "Claim", "Expense", "Claims", "", "員工墊支報銷（銀行／現金）"),
    ("6500", "Repairs & maintenance", "Expense", "Operating expenses", "", ""),
    ("6900", "Miscellaneous", "Expense", "Operating expenses", "", ""),
    ("6910", "Membership / BNI", "Expense", "Operating expenses", "", ""),
)

# ISO text dates in Daily_Sales!A — avoid locale TEXT(date) formats that break SUMIFS.
_HELPER_MONTH = 'TEXT(Q4,"0000")&"-"&TEXT(Q5,"00")'
_HELPER_YEAR = 'TEXT(Q4,"0000")'
_PL_MONTH = 'TEXT(YEAR($D$4),"0000")&"-"&TEXT(MONTH($D$4),"00")'

DAILY_SALES_HELPER_FORMULAS: dict[str, str] = {
    "Q6": f'=SUMPRODUCT((LEFT($A$5:$A$1000,7)={_HELPER_MONTH})*($K$5:$K$1000))',
    "Q7": f'=SUMPRODUCT((LEFT($A$5:$A$1000,7)={_HELPER_MONTH})*($J$5:$J$1000))',
    "Q8": f'=SUMPRODUCT((LEFT($A$5:$A$1000,7)={_HELPER_MONTH})*($L$5:$L$1000))',
    "Q9": f'=SUMPRODUCT((LEFT($A$5:$A$1000,4)={_HELPER_YEAR})*($K$5:$K$1000))',
    "Q10": '=IFERROR(INDEX($L$5:$L$1000,COUNTA($A$5:$A$1000)),0)',
}

KPI_FORMULAS: dict[str, str] = {
    "B4": "='P&L_Monthly'!B4",
    "B5": "='P&L_Monthly'!B5",
    "B7": "='P&L_Monthly'!B10",
    "B8": "='P&L_Monthly'!B20",
    "B9": "='P&L_Monthly'!B38",
    "B10": "='P&L_Monthly'!B35",
    "B11": (
        '=IF(B7=0,0,ABS(SUMIFS(Bank_Entries!D:D,Bank_Entries!F:F,"Wages",'
        "Bank_Entries!A:A,\">=\"&'P&L_Monthly'!D4,Bank_Entries!A:A,\"<=\"&'P&L_Monthly'!D5)+"
        'SUMIFS(Bank_Entries!E:E,Bank_Entries!F:F,"Wages",'
        "Bank_Entries!A:A,\">=\"&'P&L_Monthly'!D4,Bank_Entries!A:A,\"<=\"&'P&L_Monthly'!D5))/B7)"
    ),
    "B12": "=IF(B7=0,0,'P&L_Monthly'!B36/B7)",
}


def repair_finance_workbook(
    *,
    report_month: int | None = None,
    as_of: date | None = None,
) -> dict[str, Any]:
    """Fix KPI #NAME?, Helpers $0, empty Chart_of_Accounts, and Daily_Sales junk cols.

    Safe to re-run. Does not touch Daily_Sales A5:N data rows.
    """
    spreadsheet = _open_spreadsheet()
    actions: list[str] = []
    today = as_of or date.today()
    month = int(report_month) if report_month else today.month

    # --- Chart_of_Accounts ---
    try:
        chart = spreadsheet.worksheet("Chart_of_Accounts")
    except Exception:
        chart = spreadsheet.add_worksheet("Chart_of_Accounts", rows=40, cols=8)
        actions.append("created Chart_of_Accounts")
    existing = chart.get_all_values()
    needs_chart = True
    if existing:
        flat = " ".join(c for row in existing for c in row)
        if "HSBC SA" in flat and "account_code" in flat:
            needs_chart = False
    if needs_chart:
        chart.clear()
        chart.update(
            "A1",
            [list(r) for r in CHART_OF_ACCOUNTS_ROWS],
            value_input_option="RAW",
        )
        actions.append("restored Chart_of_Accounts")

    # --- Daily_Sales helpers + junk clear + bridge note ---
    daily = spreadsheet.worksheet("Daily_Sales")
    daily.update("A3", [[
        "Sync writes under this header (row 4). Do not edit A–N number columns. "
        "Helpers on the right auto-sum by Report year/month."
    ]], value_input_option="RAW")
    # Report year/month controls
    daily.update("P3", [["Helpers (auto)"]], value_input_option="RAW")
    daily.update("P4", [["Report year"]], value_input_option="RAW")
    daily.update("Q4", [[today.year]], value_input_option="USER_ENTERED")
    daily.update("P5", [["Report month (1-12)"]], value_input_option="RAW")
    daily.update("Q5", [[month]], value_input_option="USER_ENTERED")
    daily.update("P6", [["Month sales (Daily Sales col)"]], value_input_option="RAW")
    daily.update("P7", [["Month claims (sheet)"]], value_input_option="RAW")
    daily.update(
        "P8",
        [["Month cash tilt (last nonblank approx = sum)"]],
        value_input_option="RAW",
    )
    daily.update("P9", [["YTD sales"]], value_input_option="RAW")
    daily.update("P10", [["Latest Cash Tilt"]], value_input_option="RAW")
    for cell, formula in DAILY_SALES_HELPER_FORMULAS.items():
        daily.update(cell, [[formula]], value_input_option="USER_ENTERED")
    actions.append("fixed Daily_Sales Helpers formulas")

    # Clear old mis-append junk (far-right columns from broken append_row)
    blank = [[""] * 14 for _ in range(40)]
    daily.update("P11:AC50", blank, value_input_option="RAW")
    actions.append("cleared Daily_Sales P11:AC50 junk")

    # --- KPI quoted sheet refs ---
    kpi = spreadsheet.worksheet("KPI")
    for cell, formula in KPI_FORMULAS.items():
        kpi.update(cell, [[formula]], value_input_option="USER_ENTERED")
    actions.append("fixed KPI formulas (quoted P&L_Monthly)")

    # --- P&L month + text-date sales formulas ---
    pl = spreadsheet.worksheet("P&L_Monthly")
    pl.update("B5", [[month]], value_input_option="USER_ENTERED")
    pl.update(
        "B8",
        [[
            f'=SUMPRODUCT((LEFT(Daily_Sales!$A$5:$A$1000,7)={_PL_MONTH})'
            f'*(Daily_Sales!$K$5:$K$1000))'
        ]],
        value_input_option="USER_ENTERED",
    )
    pl.update(
        "B35",
        [[
            f'=SUMPRODUCT((LEFT(Daily_Sales!$A$5:$A$1000,7)={_PL_MONTH})'
            f'*(Daily_Sales!$J$5:$J$1000))'
        ]],
        value_input_option="USER_ENTERED",
    )
    actions.append(f"P&L_Monthly month→{month} + sales/claims formulas")

    # --- Balance Sheet as-of ---
    bs = spreadsheet.worksheet("Balance_Sheet")
    bs.update("B4", [[today.isoformat()]], value_input_option="USER_ENTERED")
    actions.append(f"Balance_Sheet as-of→{today.isoformat()}")

    # Setup note: bridge sheet id no longer needed
    try:
        setup = spreadsheet.worksheet("Setup")
        setup.update(
            "A7",
            [[
                "7. Daily_Sales sync targets THIS workbook "
                f"(id {_sheet_id()}) — no IMPORTRANGE bridge."
            ]],
            value_input_option="RAW",
        )
        actions.append("updated Setup bridge note")
    except Exception:
        pass

    return {
        "ok": True,
        "sheet_id": _sheet_id(),
        "spreadsheet_title": spreadsheet.title,
        "actions": actions,
        "report_month": month,
        "as_of": today.isoformat(),
    }
