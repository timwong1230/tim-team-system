"""Bank CSV parse + Nature inference (no Google Sheets required)."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

_ROOT = Path(__file__).resolve().parents[1]
_POLAR = _ROOT / "polar-order"
if str(_POLAR) not in sys.path:
    sys.path.insert(0, str(_POLAR))


def test_infer_nature_and_parse_amount_csv():
    from app.bank_import import infer_nature, parse_bank_csv

    assert infer_nature("HKE ELECTRICITY OCT") == "Electricity"
    assert infer_nature("Monthly rent Causeway Bay") == "Rent"
    assert infer_nature("Staff wages Sep") == "Wages"
    assert infer_nature("Random shop") == "Miscellaneous"

    csv_text = """Date,Description,Amount
01/10/2026,HKE Electricity,-1200.50
02/10/2026,FPS sales deposit,8000
03/10/2026,Unknown vendor,-50
"""
    rows = parse_bank_csv(csv_text, account="hsbc_ca")
    assert len(rows) == 3
    assert rows[0]["nature"] == "Electricity"
    assert rows[0]["hsbc_ca"] == -1200.5
    assert rows[0]["hsbc_sa"] == ""
    assert rows[1]["nature"] == "Sales"
    assert rows[1]["hsbc_ca"] == 8000.0
    assert rows[2]["nature"] == "Miscellaneous"


def test_parse_debit_credit_csv():
    from app.bank_import import parse_bank_csv

    csv_text = """Transaction Date,Narrative,Debit,Credit
2026-10-05,HKBN broadband,299,
2026-10-06,Partner cash in,,50000
"""
    rows = parse_bank_csv(csv_text, account="hsbc_sa")
    assert len(rows) == 2
    assert rows[0]["nature"] == "Internet"
    assert rows[0]["hsbc_sa"] == -299.0
    assert rows[1]["nature"] == "Partner cash in"
    assert rows[1]["hsbc_sa"] == 50000.0


def test_append_bank_entries_skips_duplicates():
    import os
    from app.sheets_sync import append_bank_entries

    ws = MagicMock()
    ws.title = "Bank_Entries"
    ws.row_values.side_effect = lambda r: (
        ["date", "memo", "chq_no", "hsbc_sa", "hsbc_ca", "nature", "account_code", "linked_sales_date", "notes"]
        if r == 1
        else []
    )
    ws.get_all_values.return_value = [
        ["date", "memo", "chq_no", "hsbc_sa", "hsbc_ca", "nature", "account_code", "linked_sales_date", "notes"],
        ["2026-10-01", "HKE Electricity", "", "", "-100.00", "Electricity", "6200", "", "imported"],
    ]

    entries = [
        {
            "date": "2026-10-01",
            "memo": "HKE Electricity",
            "chq_no": "",
            "hsbc_sa": "",
            "hsbc_ca": -100.0,
            "nature": "Electricity",
            "account_code": "6200",
            "linked_sales_date": "",
            "notes": "imported",
            "fingerprint": "2026-10-01|HKE Electricity|-100.00|hsbc_ca",
        },
        {
            "date": "2026-10-02",
            "memo": "Rent",
            "chq_no": "",
            "hsbc_sa": "",
            "hsbc_ca": -5000.0,
            "nature": "Rent",
            "account_code": "6000",
            "linked_sales_date": "",
            "notes": "imported",
            "fingerprint": "2026-10-02|Rent|-5000.00|hsbc_ca",
        },
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
        result = append_bank_entries(entries)

    assert result["skipped"] == 1
    assert result["added"] == 1
    ws.append_rows.assert_called_once()
