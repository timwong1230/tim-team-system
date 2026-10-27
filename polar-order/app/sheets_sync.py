"""Push nightly Daily_Sales rows to Google Sheets.

Env:
  POLAR_DAILY_SALES_SHEET_ID — spreadsheet id
  POLAR_DAILY_SALES_WORKSHEET — tab name (default Daily_Sales)
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

_SCOPES = (
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
)


class SheetsNotConfigured(RuntimeError):
    """Missing sheet id or service-account credentials."""


def sheets_configured() -> bool:
    return bool(_sheet_id() and _credentials_dict())


def _sheet_id() -> str:
    return (os.getenv("POLAR_DAILY_SALES_SHEET_ID") or "").strip()


def _worksheet_title() -> str:
    return (os.getenv("POLAR_DAILY_SALES_WORKSHEET") or "Daily_Sales").strip() or "Daily_Sales"


def _credentials_dict() -> dict[str, Any] | None:
    raw = (os.getenv("POLAR_GSPREAD_KEY") or os.getenv("GSPREAD_KEY") or "").strip()
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SheetsNotConfigured("POLAR_GSPREAD_KEY is not valid JSON") from exc
    if not isinstance(data, dict):
        raise SheetsNotConfigured("POLAR_GSPREAD_KEY must be a JSON object")
    return data


def _open_worksheet():
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
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key(sheet_id)
    title = _worksheet_title()

    worksheet = None
    try:
        worksheet = spreadsheet.worksheet(title)
    except gspread.WorksheetNotFound:
        for candidate in spreadsheet.worksheets():
            header = candidate.row_values(1)[:1]
            if header == ["business_date"]:
                worksheet = candidate
                break
        if worksheet is None:
            worksheet = spreadsheet.sheet1

    # Keep a stable tab name for future syncs / docs.
    if worksheet.title != title:
        try:
            worksheet.update_title(title)
        except Exception:
            pass
    return worksheet


def _ensure_headers(worksheet) -> None:
    current = worksheet.row_values(1)
    if current[: len(DAILY_SALES_HEADERS)] == list(DAILY_SALES_HEADERS):
        return
    worksheet.update(
        "A1",
        [list(DAILY_SALES_HEADERS)],
        value_input_option="RAW",
    )


def _row_values(row: dict[str, Any]) -> list[Any]:
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

    worksheet = _open_worksheet()
    _ensure_headers(worksheet)
    values = _row_values(row)

    # Column A holds business_date (skip header).
    dates = worksheet.col_values(1)[1:]
    if biz in dates:
        sheet_row = dates.index(biz) + 2  # 1-based; +1 header
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
        "worksheet": _worksheet_title(),
        "row": {h: values[i] for i, h in enumerate(DAILY_SALES_HEADERS)},
    }
