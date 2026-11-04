"""Finance workbook repair formulas + Chart restore (mocked gspread)."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

_ROOT = Path(__file__).resolve().parents[1]
_POLAR = _ROOT / "polar-order"
sys.path = [p for p in sys.path if Path(p).resolve() != _POLAR.resolve()]
sys.path.insert(0, str(_POLAR))
if "app" in sys.modules and not getattr(sys.modules["app"], "__path__", None):
    del sys.modules["app"]


def test_kpi_formulas_quote_pl_sheet_name():
    from app.sheets_sync import KPI_FORMULAS

    for cell in ("B4", "B5", "B7", "B8", "B9", "B10", "B12"):
        assert "'P&L_Monthly'" in KPI_FORMULAS[cell]
    assert "#NAME?" not in KPI_FORMULAS["B4"]
    assert KPI_FORMULAS["B4"].startswith("='P&L_Monthly'")


def test_helper_formulas_use_text_iso_keys():
    from app.sheets_sync import DAILY_SALES_HELPER_FORMULAS

    assert "SUMPRODUCT" in DAILY_SALES_HELPER_FORMULAS["Q6"]
    assert 'TEXT(Q4,"0000")' in DAILY_SALES_HELPER_FORMULAS["Q6"]
    assert "LEFT($A$5:$A$1000,7)" in DAILY_SALES_HELPER_FORMULAS["Q6"]
    assert "COUNTA" in DAILY_SALES_HELPER_FORMULAS["Q10"]


def test_chart_of_accounts_rows_cover_natures():
    from app.sheets_sync import CHART_OF_ACCOUNTS_ROWS

    natures = {row[1] for row in CHART_OF_ACCOUNTS_ROWS if row[0] and row[0][0].isdigit()}
    for need in ("Sales", "Wages", "Rent", "HSBC SA", "Partner cash in"):
        assert need in natures


def test_repair_finance_workbook_updates_tabs():
    from app.sheets_sync import (
        CHART_OF_ACCOUNTS_ROWS,
        DAILY_SALES_HELPER_FORMULAS,
        KPI_FORMULAS,
        repair_finance_workbook,
    )

    ss = MagicMock()
    chart = MagicMock()
    daily = MagicMock()
    kpi = MagicMock()
    pl = MagicMock()
    bs = MagicMock()
    setup = MagicMock()
    chart.get_all_values.return_value = []
    ss.worksheet.side_effect = lambda title: {
        "Chart_of_Accounts": chart,
        "Daily_Sales": daily,
        "KPI": kpi,
        "P&L_Monthly": pl,
        "Balance_Sheet": bs,
        "Setup": setup,
    }[title]
    ss.title = "Polar Lounge — Finance"

    with patch("app.sheets_sync._open_spreadsheet", return_value=ss):
        with patch("app.sheets_sync._sheet_id", return_value="sheet123"):
            result = repair_finance_workbook(
                report_month=11, as_of=date(2026, 11, 4)
            )

    assert result["ok"] is True
    assert result["report_month"] == 11
    assert "restored Chart_of_Accounts" in result["actions"]
    assert "fixed KPI formulas (quoted P&L_Monthly)" in result["actions"]

    chart.update.assert_any_call(
        "A1",
        [list(r) for r in CHART_OF_ACCOUNTS_ROWS],
        value_input_option="RAW",
    )
    daily.update.assert_any_call(
        "Q6",
        [[DAILY_SALES_HELPER_FORMULAS["Q6"]]],
        value_input_option="USER_ENTERED",
    )
    kpi.update.assert_any_call(
        "B4",
        [[KPI_FORMULAS["B4"]]],
        value_input_option="USER_ENTERED",
    )
    pl.update.assert_any_call("B5", [[11]], value_input_option="USER_ENTERED")
    pl.update.assert_any_call("B4", [[2026]], value_input_option="USER_ENTERED")
    daily.update.assert_any_call(
        "Q5",
        [["='P&L_Monthly'!B5"]],
        value_input_option="USER_ENTERED",
    )
    daily.update.assert_any_call(
        "Q4",
        [["='P&L_Monthly'!B4"]],
        value_input_option="USER_ENTERED",
    )
    assert pl.add_validation.call_count >= 2
    bs.update.assert_any_call(
        "B4", [["2026-11-04"]], value_input_option="USER_ENTERED"
    )
    daily.update.assert_any_call(
        "P11:AC50",
        [[""] * 14 for _ in range(40)],
        value_input_option="RAW",
    )
    assert "P&L_Monthly Year/Month dropdowns (pick, don't type)" in result["actions"]


def test_apply_year_month_dropdowns_lists():
    from gspread.utils import ValidationConditionType

    from app.sheets_sync import _apply_year_month_dropdowns

    pl = MagicMock()
    _apply_year_month_dropdowns(pl, year=2026, month=11)
    assert pl.add_validation.call_count == 2
    year_call, month_call = pl.add_validation.call_args_list
    assert year_call.args[0] == "B4"
    assert year_call.args[1] == ValidationConditionType.one_of_list
    assert "2026" in year_call.args[2]
    assert month_call.args[0] == "B5"
    assert month_call.args[2] == [str(m) for m in range(1, 13)]
    assert month_call.kwargs.get("showCustomUi") is True
