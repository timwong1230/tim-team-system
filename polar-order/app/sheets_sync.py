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


def sheets_status() -> dict[str, Any]:
    """Staff-safe diagnostics (no secrets)."""
    gap = sheets_config_gap()
    raw = _raw_credentials_text()
    parsed_ok = False
    client_email = None
    if raw:
        try:
            data = _parse_credentials_json(raw)
            parsed_ok = isinstance(data, dict)
            if parsed_ok:
                client_email = str(data.get("client_email") or "") or None
        except SheetsNotConfigured:
            parsed_ok = False
    return {
        "ready": gap is None,
        "gap": gap,
        "has_sheet_id": bool(_sheet_id()),
        "sheet_id_suffix": (_sheet_id()[-8:] if _sheet_id() else None),
        "has_credentials_env": bool(raw),
        "credentials_parse_ok": parsed_ok,
        "service_account_email": client_email,
    }


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


def upsert_daily_sales_row(row: dict[str, Any]) -> dict[str, Any]:
    """Insert or update the Daily_Sales row for row['business_date']."""
    biz = str(row.get("business_date") or "").strip()
    if not biz:
        raise ValueError("business_date is required")

    worksheet = _open_named_worksheet(_daily_worksheet_title(), "business_date")
    header_row = _ensure_headers(worksheet, DAILY_SALES_HEADERS)
    values = _daily_row_values(row)

    # Column A from the row under headers.
    col_a = worksheet.col_values(1)
    dates = col_a[header_row:]  # after header row
    if biz in dates:
        sheet_row = header_row + dates.index(biz) + 1
        worksheet.update(
            f"A{sheet_row}",
            [values],
            value_input_option="RAW",
        )
        action = "updated"
    else:
        worksheet.append_row(values, value_input_option="RAW")
        action = "appended"

    return {
        "ok": True,
        "action": action,
        "business_date": biz,
        "sheet_id": _sheet_id(),
        "worksheet": _daily_worksheet_title(),
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
