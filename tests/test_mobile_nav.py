"""Mobile top nav must sync with programmatic Home button jumps."""

from __future__ import annotations

import inspect
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def test_go_menu_exported():
    from tt_core.mobile import go_menu, mobile_top_nav

    assert callable(go_menu)
    assert callable(mobile_top_nav)


def test_go_menu_does_not_set_widget_key():
    """go_menu must not assign mobile_top_nav — widget may already exist."""
    from tt_core.mobile import go_menu

    src = inspect.getsource(go_menu)
    assert '["_menu_choice"]' in src or "['_menu_choice']" in src
    assert '["mobile_top_nav"]' not in src and "['mobile_top_nav']" not in src
    assert "rerun" in src


def test_force_home_once_syncs_mobile_nav():
    src = (_ROOT / "app.py").read_text(encoding="utf-8")
    assert '_force_home_once' in src
    # Consumer path must sync mobile_top_nav before the selectbox exists
    assert 'st.session_state["mobile_top_nav"] = "🏠 我的主頁"' in src


def test_app_uses_go_menu_on_home_buttons():
    src = (_ROOT / "app.py").read_text(encoding="utf-8")
    assert "from tt_core.mobile import" in src
    assert "go_menu" in src
    assert 'go_menu("📝 打卡 Check-in")' in src
    assert 'go_menu("📋 準客戶名單")' in src
    assert 'go_menu("🧠 Coach Tim"' in src
    mob = (_ROOT / "tt_core" / "mobile.py").read_text(encoding="utf-8")
    assert "mobile_top_nav" in mob
    assert "go_menu" in mob
    assert "StreamlitWidgetAlreadyInstantiatedError" in mob


if __name__ == "__main__":
    test_go_menu_exported()
    test_go_menu_does_not_set_widget_key()
    test_force_home_once_syncs_mobile_nav()
    test_app_uses_go_menu_on_home_buttons()
    print("mobile nav ok")
