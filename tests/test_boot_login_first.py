"""Login form must paint before any Google Sheets / PWA work."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def test_app_defers_sheets_and_pwa_until_after_login():
    src = (_ROOT / "app.py").read_text(encoding="utf-8")
    # Boot block before auth must not call these
    boot = src[src.index("st.set_page_config") : src.index("# ─── Auth")]
    # Ignore comments that mention the deferred calls
    boot_code = "\n".join(
        ln for ln in boot.splitlines() if not ln.lstrip().startswith("#")
    )
    assert "init_db_gs()" not in boot_code
    assert "inject_pwa_head()" not in boot_code
    assert "CUSTOM_CSS" in boot

    # Login click may bootstrap schema
    login_fn = src[src.index("def _do_login") : src.index("if MOBILE:")]
    assert "init_db_gs()" in login_fn

    # Logged-in shell injects PWA + ensures schema
    logged = src[src.index("# ─── Logged-in shell") : src.index("# Drop legacy DataFrame")]
    assert "inject_pwa_head()" in logged
    assert "init_db_gs()" in logged


def test_warm_cache_has_time_budget():
    src = (_ROOT / "tt_core" / "db.py").read_text(encoding="utf-8")
    warm = src[src.index("def warm_cache") : src.index("def clear_cache")]
    assert "TIM_TEAM_WARM_BUDGET_SEC" in warm or "warm_budget" in warm
