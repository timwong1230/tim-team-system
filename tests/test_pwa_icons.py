"""PWA helpers: keep Streamlit crown; no custom launch-page icon campaign."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def test_inject_pwa_does_not_override_favicon():
    src = (_ROOT / "tt_core" / "mobile.py").read_text(encoding="utf-8")
    inj = src[src.index("def inject_pwa_head") : src.index("def render_install_guide")]
    assert "applyFavicon" not in inj
    assert "apple-touch-icon" not in inj
    assert "tt-meta-v1" in inj


def test_install_guide_accepts_streamlit_crown():
    src = (_ROOT / "tt_core" / "mobile.py").read_text(encoding="utf-8")
    guide = src[src.index("def render_install_guide") : src.index("def _bump_phone_nav_popover")]
    assert "launch.html" not in guide
    assert "皇冠" in guide
    assert "_APP_URL" in guide
    assert "ACE TEAM 圖示" not in guide


def test_launch_html_removed():
    assert not (_ROOT / "static" / "launch.html").exists()
    assert not (_ROOT / ".github" / "workflows" / "pages.yml").exists()
