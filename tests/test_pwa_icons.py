"""iPhone home-screen icon: Streamlit Cloud cannot customize; use public launch.html."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def test_pwa_inject_uses_public_apple_touch_icon():
    src = (_ROOT / "tt_core" / "mobile.py").read_text(encoding="utf-8")
    assert "cdn.jsdelivr.net/gh/timwong1230/tim-team-system" in src
    assert "apple-touch-icon" in src
    assert "ace-v6" in src
    apply = src[src.index("function applyFavicon") : src.index("upsertMeta('name', 'viewport'")]
    assert "add('apple-touch-icon', P.icon" in apply
    assert "add('apple-touch-icon', P.iconLocal" not in apply


def test_static_ace_icons_exist():
    static = _ROOT / "static"
    assert (static / "apple-touch-icon.png").is_file()
    assert (static / "app_icon_180.png").is_file()
    assert (static / "app_icon_512.png").is_file()
    assert (static / "launch.html").is_file()
    assert (static / "site.webmanifest").is_file()


def test_launch_html_has_apple_touch_icon_not_streamlit():
    html = (_ROOT / "static" / "launch.html").read_text(encoding="utf-8")
    assert 'rel="apple-touch-icon"' in html
    assert "apple-touch-icon.png" in html
    assert "TIM TEAM" in html
    assert "tim-team-system.streamlit.app" in html
    assert "streamlit/static" not in html.lower()


def test_install_guide_points_to_public_launch_page():
    src = (_ROOT / "tt_core" / "mobile.py").read_text(encoding="utf-8")
    assert "_LAUNCH_URL" in src
    assert "launch.html" in src
    guide = src[src.index("def render_install_guide") : src.index("def _bump_phone_nav_popover")]
    assert "launch.html" in guide
    assert "link_button" in guide
    assert "皇冠" in guide
