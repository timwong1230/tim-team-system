"""Bank CSV parse + Nature inference (no Google Sheets required)."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

_ROOT = Path(__file__).resolve().parents[1]
_POLAR = _ROOT / "polar-order"
sys.path = [p for p in sys.path if Path(p).resolve() != _POLAR.resolve()]
sys.path.insert(0, str(_POLAR))
if "app" in sys.modules and not getattr(sys.modules["app"], "__path__", None):
    del sys.modules["app"]


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


def test_parse_hsbc_business_withdraw_deposit_csv():
    """HSBC Business export: title row + Withdraw(HKD)/Deposit(HKD)."""
    from app.bank_import import parse_bank_csv

    csv_text = (
        "\ufeffBusiness Integrated HKD Savings 652-825423-838,,,,\n"
        "Date,Description,Withdraw(HKD),Deposit(HKD),Ledger Balance(HKD)\n"
        '12 Oct 2026\t,"Opening Balance", \t,,321415.13\n'
        '12 Oct 2026\t,"SUN LIFE T C L - R65     2160104",-250.00, \t,321165.13\n'
        '12 Oct 2026\t,"AILE TECHNOLOGY LIMI     HC126A1226695726   12OCT", \t,44348.85,364925.98\n'
        '28 Oct 2026\t,"CREDIT INTEREST", \t,0.29,431690.67\n'
        '09 Nov 2026\t,"Closing Balance", \t,,428246.60\n'
    )
    rows = parse_bank_csv(csv_text, account="hsbc_sa")
    assert len(rows) == 3
    assert rows[0]["date"] == "2026-10-12"
    assert rows[0]["hsbc_sa"] == -250.0
    assert rows[0]["hsbc_ca"] == ""
    assert "SUN LIFE" in rows[0]["memo"]
    assert rows[1]["hsbc_sa"] == 44348.85
    assert rows[2]["hsbc_sa"] == 0.29


def test_parse_uploaded_hsbc_savings_file():
    from pathlib import Path

    from app.bank_import import parse_bank_csv

    uploads = Path(
        "/home/ubuntu/.cursor/projects/agent-repos-tim-team-system/uploads"
    )
    matches = sorted(uploads.glob("652825423838*.csv"))
    if not matches:
        return  # cloud upload not present in CI
    text = matches[-1].read_text(encoding="utf-8")
    rows = parse_bank_csv(text, account="hsbc_sa")
    assert len(rows) >= 40
    assert all(r["hsbc_sa"] != "" for r in rows)
    assert all(r["date"] >= "2026-10-12" for r in rows)


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
