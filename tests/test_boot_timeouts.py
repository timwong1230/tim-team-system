"""Boot must not hang forever on Google API / heavy icon work."""

from __future__ import annotations

import inspect
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def test_gs_client_sets_http_timeout():
    from tt_core import db

    src = inspect.getsource(db.get_gs_client)
    assert "set_timeout" in src
    assert "TIM_TEAM_GS_CONNECT_TIMEOUT" in db.__file__ or "_GS_CONNECT_TIMEOUT" in inspect.getsource(db)


def test_init_db_gs_does_not_prime_all_sheets():
    from tt_core.db import init_db_gs

    src = inspect.getsource(init_db_gs)
    assert "_fetch_sheet_from_gs" not in src
    assert "budget" in src
    assert "warm_cache" in src or "warm_cache" in inspect.getdoc(init_db_gs) or "warm_cache" in src


def test_page_icon_arg_avoids_pil_open():
    src = (_ROOT / "app.py").read_text(encoding="utf-8")
    fn = src[src.index("def page_icon_arg") : src.index("try:\n    import tt_core.branding")]
    assert "Image.open" not in fn
    assert "return str(path)" in fn
