"""Mobile top nav must sync with programmatic Home button jumps."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def test_go_menu_exported():
    from tt_core.mobile import go_menu, mobile_top_nav

    assert callable(go_menu)
    assert callable(mobile_top_nav)


def test_app_uses_go_menu_on_home_buttons():
    src = (_ROOT / "app.py").read_text(encoding="utf-8")
    assert "from tt_core.mobile import" in src
    assert "go_menu" in src
    assert 'go_menu("📝 打卡 Check-in")' in src
    assert 'go_menu("📋 準客戶名單")' in src
    assert 'go_menu("🧠 Coach Tim"' in src
    # Docstring / comment in mobile.py explains the Streamlit key trap
    mob = (_ROOT / "tt_core" / "mobile.py").read_text(encoding="utf-8")
    assert "mobile_top_nav" in mob
    assert "go_menu" in mob


if __name__ == "__main__":
    test_go_menu_exported()
    test_app_uses_go_menu_on_home_buttons()
    print("mobile nav ok")
