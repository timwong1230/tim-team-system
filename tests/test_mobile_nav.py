"""Mobile top nav must sync with programmatic Home button jumps — once."""

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


def test_go_menu_sets_nav_pending_not_widget_key():
    """go_menu must not assign mobile_top_nav — widget may already exist."""
    from tt_core.mobile import go_menu

    src = inspect.getsource(go_menu)
    assert '["_menu_choice"]' in src or "['_menu_choice']" in src
    assert '["_nav_pending"]' in src or "['_nav_pending']" in src
    assert '["mobile_top_nav"]' not in src and "['mobile_top_nav']" not in src
    assert "rerun" in src


def test_mobile_top_nav_only_forces_on_pending():
    """Must not overwrite selectbox from _menu_choice every run (locks page)."""
    from tt_core.mobile import mobile_top_nav

    src = inspect.getsource(mobile_top_nav)
    assert "_nav_pending" in src
    # Must not blindly sync current/_menu_choice over user selectbox changes
    assert "if target is not None and existing != target" not in src


def test_nav_pending_roundtrip_simulation():
    """Programmatic jump syncs once; later user select is not overwritten."""
    from tt_core import mobile as mob

    class FakeSS(dict):
        def pop(self, key, default=None):
            if key in self:
                return dict.pop(self, key)
            return default

    ss = FakeSS()
    ss["_menu_choice"] = "🏠 我的主頁"
    ss["mobile_top_nav"] = "🏠 我的主頁"
    reruns = []

    class FakeSt:
        session_state = ss

        @staticmethod
        def rerun():
            reruns.append(True)

        @staticmethod
        def selectbox(label, options, key=None, label_visibility=None):
            return ss.get(key) or options[0]

    mob.st = FakeSt()

    mob.go_menu("📝 打卡 Check-in")
    assert ss["_menu_choice"] == "📝 打卡 Check-in"
    assert ss["_nav_pending"] == "📝 打卡 Check-in"
    assert reruns == [True]

    # Next run: pending applied, selectbox shows check-in
    items = ["🏠 我的主頁", "📝 打卡 Check-in", "📋 準客戶名單"]
    menu = mob.mobile_top_nav(items, ss.get("_menu_choice"))
    assert menu == "📝 打卡 Check-in"
    assert "_nav_pending" not in ss

    # User picks Home via selectbox — must NOT be forced back to check-in
    ss["mobile_top_nav"] = "🏠 我的主頁"
    ss["_menu_choice"] = "📝 打卡 Check-in"  # stale until after selectbox
    menu2 = mob.mobile_top_nav(items, ss.get("_menu_choice"))
    assert menu2 == "🏠 我的主頁"
    assert ss["mobile_top_nav"] == "🏠 我的主頁"


def test_force_home_once_sets_nav_pending():
    src = (_ROOT / "app.py").read_text(encoding="utf-8")
    assert "_force_home_once" in src
    assert 'st.session_state["_nav_pending"] = "🏠 我的主頁"' in src


def test_app_uses_go_menu_on_home_buttons():
    src = (_ROOT / "app.py").read_text(encoding="utf-8")
    assert "from tt_core.mobile import" in src
    assert "go_menu" in src
    assert 'go_menu("📝 打卡 Check-in")' in src
    assert 'go_menu("📋 準客戶名單")' in src
    assert 'go_menu("🧠 AI Tim"' in src
    mob = (_ROOT / "tt_core" / "mobile.py").read_text(encoding="utf-8")
    assert "mobile_top_nav" in mob
    assert "go_menu" in mob
    assert "StreamlitWidgetAlreadyInstantiatedError" in mob


if __name__ == "__main__":
    test_go_menu_exported()
    test_go_menu_sets_nav_pending_not_widget_key()
    test_mobile_top_nav_only_forces_on_pending()
    test_nav_pending_roundtrip_simulation()
    test_force_home_once_sets_nav_pending()
    test_app_uses_go_menu_on_home_buttons()
    print("mobile nav ok")
