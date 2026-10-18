"""iPhone home-screen icon: launch.html must be real HTML, not jsDelivr text/plain."""

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
    apply = src[src.index("function applyFavicon") : src.index("upsertMeta('name', 'viewport'")]
    assert "add('apple-touch-icon', P.icon" in apply
    assert "add('apple-touch-icon', P.iconLocal" not in apply


def test_static_ace_icons_exist():
    static = _ROOT / "static"
    assert (static / "apple-touch-icon.png").is_file()
    assert (static / "launch.html").is_file()
    assert (_ROOT / ".github" / "workflows" / "pages.yml").is_file()


def test_launch_html_uses_cdn_icons_and_not_jsdelivr_as_page_host():
    html = (_ROOT / "static" / "launch.html").read_text(encoding="utf-8")
    assert 'rel="apple-touch-icon"' in html
    assert "cdn.jsdelivr.net/gh/timwong1230/tim-team-system@main/static/apple-touch-icon.png" in html
    assert "tim-team-system.streamlit.app" in html
    assert "jsDelivr serves HTML as text/plain" in html or "text/plain" in html


def test_install_guide_avoids_jsdelivr_html_url():
    src = (_ROOT / "tt_core" / "mobile.py").read_text(encoding="utf-8")
    assert "_LAUNCH_URL_PAGES" in src
    assert "github.io/tim-team-system/launch.html" in src
    assert "/app/static/launch.html" in src
    # Must not point users at jsDelivr .html (Safari shows source)
    assert '_LAUNCH_URL = f"{_REPO_CDN}/launch.html"' not in src
    assert "_LAUNCH_URL = _LAUNCH_URL_APP_STATIC" in src
    guide = src[src.index("def render_install_guide") : src.index("def _bump_phone_nav_popover")]
    assert "jsDelivr" in guide or "jsdelivr" in guide
    assert "Anyone with the link" in guide
