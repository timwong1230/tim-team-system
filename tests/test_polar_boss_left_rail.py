"""Boss personal tab: category left rail (same shell as staff order)."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_POLAR = _ROOT / "polar-order"
if str(_POLAR) not in sys.path:
    sys.path.insert(0, str(_POLAR))


def test_boss_order_left_category_rail():
    tmp = tempfile.mkdtemp(prefix="polar-boss-rail-")
    os.environ["POLAR_DATA_DIR"] = tmp
    os.environ["POLAR_STAFF_PIN"] = "polar2026"

    import importlib

    import app.paths as paths
    import app.db as db
    import app.main as main

    importlib.reload(paths)
    importlib.reload(db)
    importlib.reload(main)

    from fastapi.testclient import TestClient

    from app.seats import BOSSES

    boss = BOSSES[0]
    with TestClient(main.app) as client:
        page = client.get(f"/boss/{boss['id']}")
        assert page.status_code == 200
        html = page.content
        assert b"staff-order-shell" in html
        assert b'id="bossOrderShell"' in html
        assert b'id="bossCatRail"' in html
        assert b'id="bossOrderMain"' in html
        assert b"guest-cat-rail" in html
        assert b"guest-shell" in html
        # Left rail before product main
        assert html.index(b"bossCatRail") < html.index(b"bossOrderMain")
        # Free Flow still available on boss tab (staff-only personal)
        assert b"Free Flow" in html
        assert b'id="cat-free-flow"' in html
        # First section visible; later ones start hidden
        assert b"section-products" in html

    js = (_POLAR / "static/js/boss.js").read_text(encoding="utf-8")
    assert "openBossCategory" in js
    assert "bossOrderMain" in js
    assert "is-nav-hidden" in js

    tpl = (_POLAR / "templates/boss_order.html").read_text(encoding="utf-8")
    assert 'id="bossCatRail"' in tpl
    assert "guest-cat-rail" in tpl
    assert tpl.index("bossCatRail") < tpl.index("bossOrderMain")
