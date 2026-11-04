"""Sheets sync errors must never show a blank message; private_key \\n is fixed."""

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


def test_format_sheets_error_never_blank():
    tmp = tempfile.mkdtemp(prefix="polar-sheets-err-")
    os.environ["POLAR_DATA_DIR"] = tmp
    import importlib

    import app.sheets_sync as sheets_sync

    importlib.reload(sheets_sync)

    class EmptyExc(Exception):
        def __str__(self) -> str:
            return ""

    text = sheets_sync.format_sheets_error(EmptyExc())
    assert text
    assert "EmptyExc" in text

    class Nested(Exception):
        pass

    try:
        raise Nested("root") from EmptyExc()
    except Nested as exc:
        nested = sheets_sync.format_sheets_error(exc)
    assert "Nested" in nested
    assert "root" in nested


def test_normalize_double_escaped_private_key_newlines():
    tmp = tempfile.mkdtemp(prefix="polar-sheets-pk-")
    os.environ["POLAR_DATA_DIR"] = tmp
    import importlib

    import app.sheets_sync as sheets_sync

    importlib.reload(sheets_sync)

    # Simulate env paste where \\n stayed as two characters inside the PEM
    raw_key = (
        "-----BEGIN PRIVATE KEY-----\\n"
        "abc\\n"
        "-----END PRIVATE KEY-----\\n"
    )
    payload = {
        "type": "service_account",
        "client_email": "polar-sheets@polar-lounge-2019.iam.gserviceaccount.com",
        "private_key": raw_key,
    }
    # json.dumps will escape again → value in env looks like \\\n after load... 
    # Instead feed the parser a JSON string whose private_key value contains literal backslash-n
    env_json = (
        '{"type":"service_account",'
        '"client_email":"polar-sheets@polar-lounge-2019.iam.gserviceaccount.com",'
        '"private_key":"-----BEGIN PRIVATE KEY-----\\nabc\\n-----END PRIVATE KEY-----\\n"}'
    )
    # In the above Python string, \\n becomes \n in the JSON source, which json.loads
    # turns into real newlines — also OK. Force true double-escape:
    env_json = json.dumps(
        {
            "type": "service_account",
            "client_email": "polar-sheets@polar-lounge-2019.iam.gserviceaccount.com",
            "private_key": "-----BEGIN PRIVATE KEY-----\\nabc\\n-----END PRIVATE KEY-----\\n",
        }
    )
    data = sheets_sync._parse_credentials_json(env_json)
    pk = data["private_key"]
    assert "\n" in pk
    assert "\\n" not in pk
    assert pk.startswith("-----BEGIN PRIVATE KEY-----\n")
