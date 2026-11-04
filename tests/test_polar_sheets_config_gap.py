"""Reports must explain why Google Sheet sync is off (no silent dead buttons)."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_POLAR = _ROOT / "polar-order"
sys.path = [str(_POLAR)] + [p for p in sys.path if Path(p).resolve() != _ROOT]
for _name in list(sys.modules):
    if _name == "app" or _name.startswith("app."):
        del sys.modules[_name]


def _reload():
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
    return sheets_sync, main


def test_sheets_config_gap_missing_key_and_reports_banner():
    tmp = tempfile.mkdtemp(prefix="polar-sheets-gap-")
    os.environ["POLAR_DATA_DIR"] = tmp
    os.environ["POLAR_STAFF_PIN"] = "polar2026"
    os.environ.pop("POLAR_DAILY_SALES_SHEET_ID", None)  # default workbook id kicks in
    os.environ.pop("POLAR_GSPREAD_KEY", None)
    os.environ.pop("GSPREAD_KEY", None)

    sheets_sync, main = _reload()
    gap = sheets_sync.sheets_config_gap()
    assert gap is not None
    assert "POLAR_GSPREAD_KEY" in gap
    assert sheets_sync.sheets_configured() is False
    assert sheets_sync._sheet_id() == sheets_sync.DEFAULT_DAILY_SALES_SHEET_ID

    from fastapi.testclient import TestClient

    with TestClient(main.app) as client:
        page = client.get("/staff/reports?pin=polar2026")
        assert page.status_code == 200
        html = page.content.decode("utf-8")
        assert "Sheet sync 而家關咗" in html
        assert "POLAR_GSPREAD_KEY" in html
        assert 'data-blocked="1"' in html
        assert "唔會自動更新" in html
        assert "檢查設定" in html

        status = client.get("/api/staff/sheets-status?pin=polar2026")
        assert status.status_code == 200
        body = status.json()
        assert body["ready"] is False
        assert body["has_sheet_id"] is True
        assert body["has_credentials_env"] is False


def test_sheets_config_gap_ready_when_key_present():
    os.environ["POLAR_DAILY_SALES_SHEET_ID"] = "sheet-id-demo"
    os.environ["POLAR_GSPREAD_KEY"] = json.dumps(
        {
            "type": "service_account",
            "client_email": "bot@x.iam.gserviceaccount.com",
            "private_key": "-----BEGIN PRIVATE KEY-----\\nabc\\n-----END PRIVATE KEY-----\\n",
        }
    )
    sheets_sync, _main = _reload()
    assert sheets_sync.sheets_config_gap() is None
    assert sheets_sync.sheets_configured() is True


def test_parse_credentials_tolerates_smart_quotes_and_double_encoding():
    sheets_sync, _main = _reload()
    payload = {
        "type": "service_account",
        "client_email": "bot@x.iam.gserviceaccount.com",
        "private_key": "-----BEGIN PRIVATE KEY-----\\nabc\\n-----END PRIVATE KEY-----\\n",
    }
    raw = json.dumps(payload)
    # Phone keyboards sometimes turn " into “
    smart = raw.replace('"', "\u201c")
    assert sheets_sync._parse_credentials_json(smart)["client_email"].startswith("bot@")
    # Double-encoded JSON string (Render paste quirk)
    wrapped = json.dumps(raw)
    assert sheets_sync._parse_credentials_json(wrapped)["client_email"].startswith("bot@")
