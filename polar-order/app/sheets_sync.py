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


def _looks_like_bank_date(val: Any) -> bool:
    return bool(_biz_date_candidates(val))


def _bank_fingerprint_from_cells(
    d: str,
    memo: str,
    sa: str,
    ca: str,
) -> str | None:
    d = (d or "").strip()
    memo = (memo or "").strip()
    if not d or not memo or not _looks_like_bank_date(d):
        return None
    sa_s = (sa or "").strip()
    ca_s = (ca or "").strip()
    amt = sa_s or ca_s or "0"
    acct = "hsbc_sa" if sa_s else "hsbc_ca"
    try:
        amt_f = float(str(amt).replace(",", ""))
    except ValueError:
        amt_f = 0.0
    # Normalize date to ISO when possible so CSV re-uploads match sheet cells.
    dates = _biz_date_candidates(d)
    d_norm = sorted(dates)[0] if dates else d
    return f"{d_norm}|{memo}|{amt_f:.2f}|{acct}"


def _bank_entry_from_slice(row: list[Any], start: int = 0) -> dict[str, Any] | None:
    """Parse a 9-cell Bank_Entries window starting at ``start`` (0-based)."""
    need = start + len(BANK_ENTRY_HEADERS)
    if len(row) < need:
        return None
    cells = [(row[start + i] if start + i < len(row) else "") for i in range(9)]
    d = str(cells[0] or "").strip()
    memo = str(cells[1] or "").strip()
    if not d or not memo or not _looks_like_bank_date(d):
        return None
    sa_raw = str(cells[3] or "").strip()
    ca_raw = str(cells[4] or "").strip()
    nature = str(cells[5] or "").strip() or "Miscellaneous"
    code = str(cells[6] or "").strip()
    notes = str(cells[8] or "").strip()

    def _num(raw: str) -> float | str:
        if not raw:
            return ""
        try:
            return float(raw.replace(",", ""))
        except ValueError:
            return raw

    sa = _num(sa_raw)
    ca = _num(ca_raw)
    dates = _biz_date_candidates(d)
    d_norm = sorted(dates)[0] if dates else d
    amt = sa if sa != "" else ca
    try:
        amt_f = float(amt) if amt != "" else 0.0
    except (TypeError, ValueError):
        amt_f = 0.0
    acct = "hsbc_sa" if sa != "" else "hsbc_ca"
    return {
        "date": d_norm,
        "memo": memo,
        "chq_no": str(cells[2] or "").strip(),
        "hsbc_sa": sa,
        "hsbc_ca": ca,
        "nature": nature,
        "account_code": code,
        "linked_sales_date": str(cells[7] or "").strip(),
        "notes": notes,
        "fingerprint": f"{d_norm}|{memo}|{amt_f:.2f}|{acct}",
    }


def _collect_bank_fingerprints(all_vals: list[list[Any]], header_row: int) -> set[str]:
    """Fingerprints from A–I and any mis-appended windows further right."""
    existing: set[str] = set()
    data_rows = all_vals[header_row:] if len(all_vals) >= header_row else []
    for r in data_rows:
        if not r:
            continue
        # Scan every possible 9-col window — catches column-shifted appends.
        max_start = max(0, len(r) - 6)
        for start in range(0, max_start + 1):
            parsed = _bank_entry_from_slice(r, start)
            if parsed and parsed.get("fingerprint"):
                existing.add(str(parsed["fingerprint"]))
    return existing


def _next_bank_entries_row(worksheet, header_row: int) -> int:
    """First empty row under Bank_Entries headers (column A). Never use append_rows."""
    col_a = worksheet.col_values(1)
    last = header_row
    for idx in range(header_row, len(col_a)):
        if str(col_a[idx] or "").strip():
            last = idx + 1
    return last + 1


def append_bank_entries(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """Append bank rows into columns A–I under the header (never Sheets append_rows).

    ``append_rows`` lands to the right of helper columns on this template — Tim
    then sees \"uploaded\" with no visible data in the yellow A–I grid.
    """
    from .bank_import import rows_for_sheet

    if not entries:
        return {"ok": True, "added": 0, "skipped": 0, "worksheet": _bank_worksheet_title()}

    worksheet = _open_named_worksheet(_bank_worksheet_title(), "date")
    header_row = _ensure_headers(worksheet, BANK_ENTRY_HEADERS)

    all_vals = worksheet.get_all_values()
    existing = _collect_bank_fingerprints(all_vals, header_row)

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

    start_row = None
    if to_add:
        start_row = _next_bank_entries_row(worksheet, header_row)
        values = rows_for_sheet(to_add, start_row=start_row)
        worksheet.update(
            f"A{start_row}",
            values,
            value_input_option="USER_ENTERED",
        )
        # Keep helper SUM formulas in sync after large imports.
        restore_bank_entry_helpers(worksheet, header_row)

    return {
        "ok": True,
        "added": len(to_add),
        "skipped": skipped,
        "sheet_id": _sheet_id(),
        "worksheet": worksheet.title,
        "header_row": header_row,
        "start_row": start_row,
    }


def restore_bank_entry_helpers(worksheet, header_row: int) -> None:
    """Rewrite Bank helpers with live SUM formulas (never paste cached numbers)."""
    first = header_row + 1
    sa_row = header_row
    ca_row = header_row + 1
    labels_formulas = [
        ("HSBC SA balance (sum)", f"=SUM(D{first}:D2000)"),
        ("HSBC CA balance (sum)", f"=SUM(E{first}:E2000)"),
        ("Total bank", f"=L{sa_row}+L{ca_row}"),
        ("Selected month bank outflows (expenses/cogs)", "(see P&L)"),
    ]
    # Labels in K, formulas/values in L — aligned to header row block.
    for offset, (label, formula) in enumerate(labels_formulas):
        r = header_row + offset
        worksheet.update(
            f"K{r}",
            [[label, formula]],
            value_input_option="USER_ENTERED",
        )
    # Keep a small title above helpers when the template had one.
    if header_row >= 2:
        worksheet.update(
            f"K{header_row - 1}",
            [["Bank helpers"]],
            value_input_option="RAW",
        )


def restore_bank_account_code_formulas(
    worksheet,
    header_row: int,
    *,
    row_count: int,
) -> int:
    """Fill G with Nature→account_code formulas for each data row (+ buffer)."""
    from .bank_import import account_code_formula

    first = header_row + 1
    last = header_row + max(row_count, 0) + 50  # spare rows for Tim to type
    formulas = [[account_code_formula(r)] for r in range(first, last + 1)]
    worksheet.update(
        f"G{first}:G{last}",
        formulas,
        value_input_option="USER_ENTERED",
    )
    return len(formulas)


def realign_bank_entries(worksheet=None) -> dict[str, Any]:
    """Pull mis-appended CSV rows back into A–I and clear right-side junk.

    Keeps manual A–I rows and unique imported windows found anywhere on the tab.
    Restores Bank helper SUM formulas and Nature→account_code formulas.
    """
    from .bank_import import rows_for_sheet

    if worksheet is None:
        worksheet = _open_named_worksheet(_bank_worksheet_title(), "date")
    header_row = _ensure_headers(worksheet, BANK_ENTRY_HEADERS)
    all_vals = worksheet.get_all_values()

    kept: list[dict[str, Any]] = []
    seen: set[str] = set()

    data_rows = all_vals[header_row:] if len(all_vals) >= header_row else []
    for r in data_rows:
        if not r:
            continue
        # Prefer the proper A–I window when it is a real entry.
        primary = _bank_entry_from_slice(r, 0)
        windows: list[dict[str, Any]] = []
        if primary:
            windows.append(primary)
        max_start = max(0, len(r) - 6)
        for start in range(1, max_start + 1):
            parsed = _bank_entry_from_slice(r, start)
            if parsed:
                windows.append(parsed)
        for parsed in windows:
            fp = str(parsed.get("fingerprint") or "")
            if not fp or fp in seen:
                continue
            seen.add(fp)
            kept.append(parsed)

    # Clear a wide block (data + old shifted junk), then rewrite A–I + formulas.
    clear_rows = max(len(kept) + 5, len(data_rows) + 5, 80)
    clear_cols = 40  # A–AN
    blank = [[""] * clear_cols for _ in range(clear_rows)]
    start = header_row + 1
    end = header_row + clear_rows
    worksheet.update(
        f"A{start}:AN{end}",
        blank,
        value_input_option="RAW",
    )
    if kept:
        values = rows_for_sheet(kept, start_row=start)
        worksheet.update(
            f"A{start}",
            values,
            value_input_option="USER_ENTERED",
        )
    # Extra blank rows still get account_code formulas so Tim can add lines.
    formulas_written = restore_bank_account_code_formulas(
        worksheet, header_row, row_count=len(kept)
    )
    restore_bank_entry_helpers(worksheet, header_row)

    return {
        "ok": True,
        "worksheet": worksheet.title,
        "header_row": header_row,
        "rows_kept": len(kept),
        "start_row": start,
        "account_code_formulas": formulas_written,
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
    (
        "2000",
        "Loan",
        "Expense",
        "Operating expenses",
        "",
        "每月還款入 P&L；本金大數喺 Balance Sheet 黃色格填",
    ),
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
    (
        "6310",
        "Barry Smokiebear",
        "Expense",
        "Operating expenses",
        "",
        "Polar 代收再付返 Smokiebear",
    ),
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
    # Row map with Loan + Barry above Total opex (template / post-repair).
    "B9": "='P&L_Monthly'!B40",
    "B10": "='P&L_Monthly'!B35",
    "B11": (
        '=IF(B7=0,0,ABS(SUMIFS(Bank_Entries!D:D,Bank_Entries!F:F,"Wages",'
        "Bank_Entries!A:A,\">=\"&'P&L_Monthly'!D4,Bank_Entries!A:A,\"<=\"&'P&L_Monthly'!D5)+"
        'SUMIFS(Bank_Entries!E:E,Bank_Entries!F:F,"Wages",'
        "Bank_Entries!A:A,\">=\"&'P&L_Monthly'!D4,Bank_Entries!A:A,\"<=\"&'P&L_Monthly'!D5))/B7)"
    ),
    "B12": "=IF(B7=0,0,'P&L_Monthly'!B38/B7)",
}


def _pl_bank_nature_expense_formula(row: int) -> str:
    """ABS(SUMIFS SA+CA) for P&L expense row whose label is in column A."""
    return (
        f'=ABS(SUMIFS(Bank_Entries!D:D,Bank_Entries!F:F,A{row},'
        f'Bank_Entries!A:A,">="&$D$4,Bank_Entries!A:A,"<="&$D$5)'
        f'+SUMIFS(Bank_Entries!E:E,Bank_Entries!F:F,A{row},'
        f'Bank_Entries!A:A,">="&$D$4,Bank_Entries!A:A,"<="&$D$5))'
    )


def _pl_row_for_label(col_a: list[str], label: str) -> int | None:
    for i, raw in enumerate(col_a):
        if (raw or "").strip() == label:
            return i + 1
    return None


def sync_pl_expense_totals_and_kpi(pl_worksheet, kpi_worksheet=None) -> list[str]:
    """Rebind Total / Net profit / ratio formulas and KPI absolute row refs."""
    notes: list[str] = []
    col_a = pl_worksheet.col_values(1)
    rent_row = _pl_row_for_label(col_a, "Rent") or 23
    total_row = _pl_row_for_label(col_a, "Total operating expenses")
    net_row = _pl_row_for_label(col_a, "Net profit / (loss)")
    claims_row = _pl_row_for_label(col_a, "Claims recorded in Order (Daily_Sales)")
    if total_row:
        pl_worksheet.update(
            f"B{total_row}",
            [[f"=SUM(B{rent_row}:B{total_row - 1})"]],
            value_input_option="USER_ENTERED",
        )
        notes.append(f"P&L Total opex → SUM(B{rent_row}:B{total_row - 1})")
    if net_row and total_row:
        pl_worksheet.update(
            f"B{net_row}",
            [[f"=B20-B{total_row}"]],
            value_input_option="USER_ENTERED",
        )
        notes.append(f"P&L Net profit → B20-B{total_row}")
    # Ratio block sits under Net profit; update by label when present.
    ratio_expense_row = _pl_row_for_label(col_a, "Total expenses / Net sales")
    ratio_margin_row = _pl_row_for_label(col_a, "Net margin")
    if ratio_expense_row and total_row:
        pl_worksheet.update(
            f"B{ratio_expense_row}",
            [[f"=IF(B10=0,0,B{total_row}/B10)"]],
            value_input_option="USER_ENTERED",
        )
    if ratio_margin_row and net_row:
        pl_worksheet.update(
            f"B{ratio_margin_row}",
            [[f"=IF(B10=0,0,B{net_row}/B10)"]],
            value_input_option="USER_ENTERED",
        )
    if kpi_worksheet is not None:
        if net_row:
            kpi_worksheet.update(
                "B9",
                [[f"='P&L_Monthly'!B{net_row}"]],
                value_input_option="USER_ENTERED",
            )
        if claims_row:
            kpi_worksheet.update(
                "B10",
                [[f"='P&L_Monthly'!B{claims_row}"]],
                value_input_option="USER_ENTERED",
            )
        if total_row:
            kpi_worksheet.update(
                "B12",
                [[f"=IF(B7=0,0,'P&L_Monthly'!B{total_row}/B7)"]],
                value_input_option="USER_ENTERED",
            )
        notes.append("KPI Net profit / Claims / Expense% row refs synced")
    return notes


BS_LOAN_PRINCIPAL_LABEL = "Loan principal (大數 — 黃色格人手填)"
_BS_LOAN_LEGACY_LABELS = (
    "Loans payable (bank Nature Loan)",
    "Loans payable",
    "Loan principal",
    BS_LOAN_PRINCIPAL_LABEL,
)


def ensure_bs_loan_principal(bs_worksheet) -> str:
    """Show Loan principal as a manual yellow cell — never SUMIFS of monthly Loan rows.

    Monthly Loan Nature bank outflows belong on P&L. Balance Sheet keeps the
    outstanding / original big amount Tim types in.
    """
    col_a = bs_worksheet.col_values(1)
    row = None
    for label in _BS_LOAN_LEGACY_LABELS:
        row = _pl_row_for_label(col_a, label)
        if row:
            break
    if row is None:
        # Prefer slot between Total assets and Equity (template A12).
        total_assets = _pl_row_for_label(col_a, "Total assets")
        equity = _pl_row_for_label(col_a, "Equity")
        if total_assets and equity and equity == total_assets + 2:
            row = total_assets + 1
        else:
            row = 12
        bs_worksheet.update(
            f"A{row}",
            [[BS_LOAN_PRINCIPAL_LABEL]],
            value_input_option="RAW",
        )
        bs_worksheet.update(f"B{row}", [[""]], value_input_option="RAW")
        return f"Balance_Sheet added {BS_LOAN_PRINCIPAL_LABEL} at B{row} (manual)"

    bs_worksheet.update(
        f"A{row}",
        [[BS_LOAN_PRINCIPAL_LABEL]],
        value_input_option="RAW",
    )
    # Drop auto SUMIFS of Nature Loan (monthly repayments) — keep a typed number.
    try:
        b_val = bs_worksheet.acell(f"B{row}", value_render_option="FORMULA").value
    except Exception:
        b_val = bs_worksheet.acell(f"B{row}").value
    formula = str(b_val or "")
    if "SUMIFS" in formula.upper() and "Loan" in formula:
        bs_worksheet.update(f"B{row}", [[""]], value_input_option="RAW")
        return (
            f"Balance_Sheet B{row} cleared SUMIFS(Loan) → yellow principal cell"
        )
    return f"Balance_Sheet Loan principal ready at B{row} (manual, not monthly repayments)"


def ensure_pl_expense_nature(pl_worksheet, nature: str) -> str:
    """Insert a P&L operating-expense line for ``nature`` if missing.

    Inserts just above ``Total operating expenses`` so KPI refs to Claims
    (Daily_Sales) stay on their existing row when possible.

    Uses gspread 6 ``insert_rows(values, row=…)`` — passing a bare int as the
    first arg raises ``TypeError: object of type 'int' has no len()``.
    """
    col_a = pl_worksheet.col_values(1)
    if _pl_row_for_label(col_a, nature) is not None:
        return f"P&L already has {nature}"

    total_row = _pl_row_for_label(col_a, "Total operating expenses")
    if total_row is None:
        return f"P&L missing Total operating expenses — skip {nature}"

    insert_at = total_row  # 1-based: new row lands where Total currently is
    formula = _pl_bank_nature_expense_formula(insert_at)
    # gspread 6.x: first argument is values (list of rows), not the row index.
    pl_worksheet.insert_rows(
        [[nature, formula]],
        row=insert_at,
        value_input_option="USER_ENTERED",
    )
    return f"P&L added expense {nature} at row {insert_at}"


def _apply_year_month_dropdowns(pl_worksheet, *, year: int, month: int) -> None:
    """P&L yellow Year/Month cells: pick from a list instead of typing."""
    from gspread.utils import ValidationConditionType

    years = [str(y) for y in range(int(year) - 1, int(year) + 3)]
    months = [str(m) for m in range(1, 13)]
    # Ensure current values stay in the lists even if clock skew.
    if str(year) not in years:
        years = sorted({*years, str(year)}, key=int)
    if str(month) not in months:
        months = [str(m) for m in range(1, 13)]
    pl_worksheet.add_validation(
        "B4",
        ValidationConditionType.one_of_list,
        years,
        strict=True,
        showCustomUi=True,
        inputMessage="揀年份（下拉）",
    )
    pl_worksheet.add_validation(
        "B5",
        ValidationConditionType.one_of_list,
        months,
        strict=True,
        showCustomUi=True,
        inputMessage="揀月份 1–12（下拉）",
    )


def repair_finance_workbook(
    *,
    report_month: int | None = None,
    as_of: date | None = None,
) -> dict[str, Any]:
    """Fix KPI #NAME?, Helpers $0, Chart_of_Accounts, Daily_Sales junk, Bank_Entries shift.

    Safe to re-run. Does not wipe Daily_Sales A5:N number columns.
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
    flat = " ".join(c for row in existing for c in row) if existing else ""
    # Force rewrite when Loan is still the old Liability / BS-only model.
    needs_chart = (
        ("HSBC SA" not in flat)
        or ("account_code" not in flat)
        or ("Loan" not in flat)
        or ("Barry Smokiebear" not in flat)
        or ("唔入 P&L expense" in flat)
        or ("每月還款入 P&L" not in flat)
    )
    if needs_chart:
        chart.clear()
        chart.update(
            "A1",
            [list(r) for r in CHART_OF_ACCOUNTS_ROWS],
            value_input_option="RAW",
        )
        actions.append("restored Chart_of_Accounts (incl. Loan / Barry Smokiebear)")
    # Nature dropdown list (column H) — always refresh so new natures appear.
    nature_names = [
        str(r[1])
        for r in CHART_OF_ACCOUNTS_ROWS
        if len(r) > 1 and str(r[0]).isdigit()
    ]
    chart.update(
        "H4",
        [["Nature list (for dropdown)"]] + [[n] for n in nature_names],
        value_input_option="RAW",
    )
    actions.append(f"Chart Nature dropdown list ({len(nature_names)})")
    # Bank_Entries Nature dropdown → Chart H list (covers Loan + future natures).
    try:
        from gspread.utils import ValidationConditionType

        bank_dv = spreadsheet.worksheet("Bank_Entries")
        bank_dv.add_validation(
            "F6:F2000",
            ValidationConditionType.one_of_range,
            ["=Chart_of_Accounts!$H$5:$H$40"],
            strict=False,
            showCustomUi=True,
            inputMessage="揀 Nature（含 Loan / Barry Smokiebear）",
        )
        actions.append("Bank_Entries Nature dropdown → Chart H5:H40")
    except Exception as exc:  # noqa: BLE001 — non-fatal
        actions.append(f"Bank_Entries Nature dropdown skipped: {exc}")

    # --- Daily_Sales helpers + junk clear + bridge note ---
    daily = spreadsheet.worksheet("Daily_Sales")
    daily.update("A3", [[
        "Sync writes under this header (row 4). Do not edit A–N number columns. "
        "Helpers on the right follow P&L_Monthly Year/Month dropdowns."
    ]], value_input_option="RAW")
    # Report year/month — linked to P&L yellow dropdowns (pick once there)
    daily.update("P3", [["Helpers (auto)"]], value_input_option="RAW")
    daily.update("P4", [["Report year (= P&L)"]], value_input_option="RAW")
    daily.update("Q4", [["='P&L_Monthly'!B4"]], value_input_option="USER_ENTERED")
    daily.update("P5", [["Report month (= P&L)"]], value_input_option="RAW")
    daily.update("Q5", [["='P&L_Monthly'!B5"]], value_input_option="USER_ENTERED")
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

    # --- Bank_Entries: pull column-shifted CSV imports back into A–I ---
    try:
        bank = spreadsheet.worksheet("Bank_Entries")
    except Exception:
        bank = _open_named_worksheet(_bank_worksheet_title(), "date")
    bank_fix = realign_bank_entries(bank)
    actions.append(
        f"realigned Bank_Entries → {bank_fix.get('rows_kept', 0)} rows in A–I; "
        f"helpers SUM + account_code×{bank_fix.get('account_code_formulas', 0)}"
    )

    # --- KPI quoted sheet refs ---
    kpi = spreadsheet.worksheet("KPI")
    kpi.update(
        "A2",
        [[
            "跟 P&L_Monthly 同一個 Year/Month（喺 P&L 頁黃色格用下拉揀；呢頁讀返）。"
        ]],
        value_input_option="RAW",
    )
    for cell, formula in KPI_FORMULAS.items():
        kpi.update(cell, [[formula]], value_input_option="USER_ENTERED")
    actions.append("fixed KPI formulas (quoted P&L_Monthly)")

    # --- P&L year/month dropdowns + text-date sales formulas ---
    pl = spreadsheet.worksheet("P&L_Monthly")
    pl.update("B4", [[today.year]], value_input_option="USER_ENTERED")
    pl.update("B5", [[month]], value_input_option="USER_ENTERED")
    _apply_year_month_dropdowns(pl, year=today.year, month=month)
    actions.append("P&L_Monthly Year/Month dropdowns (pick, don't type)")
    actions.append(ensure_pl_expense_nature(pl, "Loan"))
    actions.append(ensure_pl_expense_nature(pl, "Barry Smokiebear"))
    actions.extend(sync_pl_expense_totals_and_kpi(pl, kpi))
    pl.update(
        "B8",
        [[
            f'=SUMPRODUCT((LEFT(Daily_Sales!$A$5:$A$1000,7)={_PL_MONTH})'
            f'*(Daily_Sales!$K$5:$K$1000))'
        ]],
        value_input_option="USER_ENTERED",
    )
    # Claims-from-Order row label may have shifted after expense inserts.
    claims_row = _pl_row_for_label(
        pl.col_values(1), "Claims recorded in Order (Daily_Sales)"
    )
    if claims_row:
        pl.update(
            f"B{claims_row}",
            [[
                f'=SUMPRODUCT((LEFT(Daily_Sales!$A$5:$A$1000,7)={_PL_MONTH})'
                f'*(Daily_Sales!$J$5:$J$1000))'
            ]],
            value_input_option="USER_ENTERED",
        )
        try:
            kpi.update("B10", [[f"='P&L_Monthly'!B{claims_row}"]], value_input_option="USER_ENTERED")
        except Exception:
            pass
    actions.append(f"P&L_Monthly month→{month} + sales/claims formulas")

    # --- Balance Sheet as-of + Loan principal (manual big amount) ---
    bs = spreadsheet.worksheet("Balance_Sheet")
    bs.update("B4", [[today.isoformat()]], value_input_option="USER_ENTERED")
    actions.append(ensure_bs_loan_principal(bs))
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
