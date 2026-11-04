"""Daily_Sales row builder + Google Sheet upsert (mocked)."""

from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

_ROOT = Path(__file__).resolve().parents[1]
_POLAR = _ROOT / "polar-order"
sys.path = [p for p in sys.path if Path(p).resolve() != _POLAR.resolve()]
sys.path.insert(0, str(_POLAR))
# Drop a wrongly-imported repo-root app.py if present.
if "app" in sys.modules and not getattr(sys.modules["app"], "__path__", None):
    del sys.modules["app"]


def test_build_daily_sales_sheet_row_matches_whatsapp_fields():
    from app.reports import build_daily_sales_sheet_row, format_whatsapp_sales_report
    from app.sheets_sync import DAILY_SALES_HEADERS

    row = build_daily_sales_sheet_row(
        business_date=date(2026, 10, 25),
        by_payment_method=[
            {"method": "Cash", "total": 1000},
            {"method": "Visa", "total": 500},
            {"method": "Mastercard", "total": 200},
            {"method": "American Express", "total": 100},
            {"method": "AlipayHK", "total": 80},
            {"method": "UnionPay", "total": 50},
            {"method": "WeChat pay", "total": 40},
            {"method": "Deposit", "total": 30},
        ],
        claims_total=120,
        daily_sales=2000,
        cash_tilt=15,
        monthly_total=45000,
        synced_at="2026-10-26T12:00:00Z",
    )
    assert list(row.keys()) == list(DAILY_SALES_HEADERS)
    assert row["business_date"] == "2026-10-25"
    assert row["Cash"] == 1000
    assert row["Master"] == 200
    assert row["AE"] == 100
    assert row["Alipay"] == 80
    assert row["Claim"] == 120
    assert row["Daily Sales"] == 2000
    assert row["Cash Tilt"] == 15
    assert row["Monthly Total"] == 45000

    wa = format_whatsapp_sales_report(
        business_date=date(2026, 10, 25),
        by_payment_method=[
            {"method": "Cash", "total": 1000},
            {"method": "Mastercard", "total": 200},
        ],
        claims_total=120,
        daily_sales=2000,
        cash_tilt=15,
        monthly_total=45000,
    )
    assert "Cash: $1000" in wa
    assert "Master: $200" in wa


def _daily_headers():
    from app.sheets_sync import DAILY_SALES_HEADERS

    return list(DAILY_SALES_HEADERS)


def test_upsert_updates_existing_business_date():
    from app.sheets_sync import upsert_daily_sales_row

    ws = MagicMock()
    ws.col_values.return_value = ["business_date", "2026-10-25"]
    ws.title = "Daily_Sales"
    ws.row_values.return_value = _daily_headers()

    with (
        patch.dict(
            os.environ,
            {
                "POLAR_DAILY_SALES_SHEET_ID": "sheet123",
                "POLAR_GSPREAD_KEY": '{"type":"service_account","client_email":"x@y.iam.gserviceaccount.com"}',
            },
            clear=False,
        ),
        patch("app.sheets_sync._open_named_worksheet", return_value=ws),
    ):
        result = upsert_daily_sales_row(
            {
                "business_date": "2026-10-25",
                "Cash": 10,
                "Visa": 0,
                "Master": 0,
                "AE": 0,
                "Alipay": 0,
                "UnionPay": 0,
                "WeChat pay": 0,
                "Deposit": 0,
                "Claim": 1,
                "Daily Sales": 10,
                "Cash Tilt": 2,
                "Monthly Total": 10,
                "synced_at": "2026-10-26T12:00:00Z",
            }
        )

    assert result["action"] == "updated"
    assert result["sheet_row"] == 2
    assert result["header_row"] == 1
    ws.update.assert_called()
    # Must target an explicit row — never rely on append_row
    assert ws.append_row.call_count == 0


def test_upsert_finance_template_header_row_4_and_date_formats():
    """Live Finance workbook: title rows 1–3, headers on row 4."""
    from app.sheets_sync import upsert_daily_sales_row

    headers = _daily_headers()
    ws = MagicMock()
    ws.title = "Daily_Sales"

    def row_values(r):
        if r == 4:
            return headers
        if r < 4:
            return ["Daily_Sales — auto from Polar Order"]
        return []

    ws.row_values.side_effect = row_values
    # Row4 header + existing night stored as locale / serial-ish string
    ws.col_values.return_value = [
        "title",
        "note",
        "bridge",
        "business_date",
        "11/03/2026",
    ]

    with (
        patch.dict(
            os.environ,
            {
                "POLAR_DAILY_SALES_SHEET_ID": "sheet123",
                "POLAR_GSPREAD_KEY": '{"type":"service_account","client_email":"x@y.iam.gserviceaccount.com"}',
            },
            clear=False,
        ),
        patch("app.sheets_sync._open_named_worksheet", return_value=ws),
    ):
        result = upsert_daily_sales_row(
            {
                "business_date": "2026-11-03",
                "Cash": 0,
                "Visa": 100,
                "Master": 0,
                "AE": 0,
                "Alipay": 0,
                "UnionPay": 0,
                "WeChat pay": 0,
                "Deposit": 0,
                "Claim": 0,
                "Daily Sales": 100,
                "Cash Tilt": 0,
                "Monthly Total": 100,
                "synced_at": "2026-11-04T01:00:00Z",
            }
        )

    assert result["header_row"] == 4
    assert result["action"] == "updated"
    assert result["sheet_row"] == 5
    assert ws.update.call_args.args[0] == "A5"


def test_sync_endpoint_requires_config():
    tmp = __import__("tempfile").mkdtemp(prefix="polar-sheet-sync-")
    os.environ["POLAR_DATA_DIR"] = tmp
    os.environ["POLAR_STAFF_PIN"] = "polar2026"
    os.environ.pop("POLAR_DAILY_SALES_SHEET_ID", None)
    os.environ.pop("POLAR_GSPREAD_KEY", None)
    os.environ.pop("GSPREAD_KEY", None)

    import importlib

    import app.paths as paths
    import app.db as db
    import app.main as main
    import app.reports as reports
    import app.sheets_sync as sheets_sync

    importlib.reload(paths)
    importlib.reload(db)
    importlib.reload(reports)
    importlib.reload(sheets_sync)
    importlib.reload(main)

    from fastapi.testclient import TestClient

    with TestClient(main.app) as client:
        page = client.get("/staff/reports?pin=polar2026")
        assert page.status_code == 200
        assert b"Google Sheet" in page.content
        assert b"Sync now (backup)" in page.content
        assert b"Upload bank CSV" in page.content
        # Missing credentials must be visible — not a silent disabled tap
        assert "Sheet sync 而家關咗".encode("utf-8") in page.content
        assert b'data-blocked="1"' in page.content

        res = client.post(
            "/api/staff/sync-daily-sales",
            data={"pin": "polar2026", "day": "2026-10-25"},
        )
        assert res.status_code == 503
