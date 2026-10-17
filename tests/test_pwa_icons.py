"""iPhone home-screen icon must use public CDN, not auth-gated /app/static."""

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
    # Must not register /app/static as apple-touch-icon (iOS fetch has no cookies)
    apply = src[src.index("function applyFavicon") : src.index("upsertMeta('name', 'viewport'")]
    assert "add('apple-touch-icon', P.icon" in apply
    assert "add('apple-touch-icon', P.iconLocal" not in apply
    assert "add('apple-touch-icon-precomposed', P.iconLocal" not in apply


def test_static_ace_icons_exist():
    static = _ROOT / "static"
    assert (static / "apple-touch-icon.png").is_file()
    assert (static / "app_icon_180.png").is_file()
    assert (static / "app_icon_512.png").is_file()


def test_install_guide_tells_user_to_delete_old_crown():
    src = (_ROOT / "tt_core" / "mobile.py").read_text(encoding="utf-8")
    guide = src[src.index("def render_install_guide") : src.index("def _bump_phone_nav_popover")]
    assert "刪除" in guide or "先長按刪除" in guide
    assert "ACE TEAM" in guide
    assert "唔會自動更新" in guide
