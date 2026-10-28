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


def test_upsert_updates_existing_business_date():
    from app.sheets_sync import upsert_daily_sales_row

    ws = MagicMock()
    ws.col_values.return_value = ["business_date", "2026-10-25"]
    ws.title = "Daily_Sales"
    ws.row_values.return_value = [
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
    ws.update.assert_called()
    ws.append_row.assert_not_called()


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

        res = client.post(
            "/api/staff/sync-daily-sales",
            data={"pin": "polar2026", "day": "2026-10-25"},
        )
        assert res.status_code == 503
