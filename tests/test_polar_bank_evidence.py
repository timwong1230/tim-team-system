"""Bank transaction evidence upload (local disk + sheet metadata)."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

_ROOT = Path(__file__).resolve().parents[1]
_POLAR = _ROOT / "polar-order"
sys.path = [p for p in sys.path if Path(p).resolve() != _POLAR.resolve()]
sys.path.insert(0, str(_POLAR))
if "app" in sys.modules and not getattr(sys.modules["app"], "__path__", None):
    del sys.modules["app"]


def test_save_and_register_local_and_sheet():
    from app.bank_evidence import resolve_evidence_path, save_and_register

    tmp = tempfile.mkdtemp(prefix="polar-evidence-")
    png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
        b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
    )

    import importlib

    import app.paths as paths
    import app.bank_evidence as be

    with patch.dict(
        os.environ,
        {
            "POLAR_DATA_DIR": tmp,
            "POLAR_DAILY_SALES_SHEET_ID": "sheet123",
            "POLAR_GSPREAD_KEY": '{"type":"service_account","client_email":"x@y.iam.gserviceaccount.com"}',
            "POLAR_BANK_EVIDENCE_FOLDER_ID": "",
        },
        clear=False,
    ):
        importlib.reload(paths)
        importlib.reload(be)
        with (
            patch.object(be, "append_bank_evidence", return_value={"ok": True, "added": 1}) as append_mock,
            patch.object(be, "sheets_configured", return_value=True),
        ):
            result = be.save_and_register(
                [{"filename": "fps.png", "content": png, "content_type": "image/png"}],
                note="公司→私人→供應商",
                txn_date="2026-10-20",
                amount_hint="8500",
            )

            assert result["ok"] is True
            assert result["uploaded"] == 1
            eid = result["files"][0]["evidence_id"]
            path = be.resolve_evidence_path(eid)
            assert path is not None and path.is_file()
            append_mock.assert_called_once()
            row = append_mock.call_args[0][0][0]
            assert row["note"] == "公司→私人→供應商"
            assert row["txn_date"] == "2026-10-20"
            assert row["amount_hint"] == "8500"


def test_append_bank_evidence_creates_headers():
    from app.sheets_sync import BANK_EVIDENCE_HEADERS, append_bank_evidence

    ws = MagicMock()
    ws.title = "Bank_Evidence"
    ws.row_values.side_effect = lambda r: [] if r == 1 else []

    spreadsheet = MagicMock()
    spreadsheet.worksheet.side_effect = Exception("not found")  # will be caught as WorksheetNotFound

    import gspread

    with (
        patch.dict(
            os.environ,
            {
                "POLAR_DAILY_SALES_SHEET_ID": "sheet123",
                "POLAR_GSPREAD_KEY": '{"type":"service_account","client_email":"x@y.iam.gserviceaccount.com"}',
            },
            clear=False,
        ),
        patch("app.sheets_sync._open_spreadsheet", return_value=spreadsheet),
        patch("gspread.WorksheetNotFound", Exception),
    ):
        # Simulate WorksheetNotFound properly
        spreadsheet.worksheet.side_effect = gspread.WorksheetNotFound("Bank_Evidence")
        spreadsheet.add_worksheet.return_value = ws
        ws.row_values.return_value = []

        result = append_bank_evidence(
            [
                {
                    "uploaded_at": "2026-10-28 18:00:00",
                    "txn_date": "2026-10-20",
                    "amount_hint": "100",
                    "note": "test",
                    "filename": "a.png",
                    "evidence_id": "a" * 32,
                    "drive_url": "",
                    "file_id": "",
                }
            ]
        )

    assert result["added"] == 1
    spreadsheet.add_worksheet.assert_called()
    ws.append_rows.assert_called_once()
    written = ws.append_rows.call_args[0][0][0]
    assert written[0] == "2026-10-28 18:00:00"
    assert len(written) == len(BANK_EVIDENCE_HEADERS)


def test_evidence_endpoint_on_reports_page():
    tmp = tempfile.mkdtemp(prefix="polar-evidence-page-")
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
    import app.bank_evidence as bank_evidence

    importlib.reload(paths)
    importlib.reload(db)
    importlib.reload(reports)
    importlib.reload(sheets_sync)
    importlib.reload(bank_evidence)
    importlib.reload(main)

    from fastapi.testclient import TestClient

    png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
        b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
    )

    with TestClient(main.app) as client:
        page = client.get("/staff/reports?pin=polar2026")
        assert page.status_code == 200
        assert "Upload 截圖".encode() in page.content or b"import-bank-evidence" in page.content
        assert b"Bank" in page.content

        res = client.post(
            "/api/staff/import-bank-evidence",
            data={
                "pin": "polar2026",
                "note": "transit via personal",
                "txn_date": "2026-10-21",
                "amount_hint": "1200",
            },
            files=[("files", ("shot.png", png, "image/png"))],
        )
        assert res.status_code == 200, res.text
        data = res.json()
        assert data["uploaded"] == 1
        eid = data["files"][0]["evidence_id"]

        get_res = client.get(f"/api/staff/bank-evidence/{eid}?pin=polar2026")
        assert get_res.status_code == 200
        assert get_res.content.startswith(b"\x89PNG")
