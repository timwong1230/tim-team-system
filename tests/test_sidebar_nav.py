"""iPad / desktop sidebar nav — professional button rail (no radio dots)."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_APP = (_ROOT / "app.py").read_text(encoding="utf-8")
_STYLES = (_ROOT / "tt_core" / "styles.py").read_text(encoding="utf-8")


def test_is_tablet_detects_ipad():
    from tt_core import mobile as mob

    with patch.object(mob, "_user_agent", return_value="Mozilla/5.0 (iPad; CPU OS 17_0)"):
        assert mob.is_tablet() is True
        assert mob.is_phone() is False
        assert mob.is_mobile() is True


def test_is_phone_excludes_ipad():
    from tt_core import mobile as mob

    with patch.object(
        mob, "_user_agent", return_value="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0)"
    ):
        assert mob.is_tablet() is False
        assert mob.is_phone() is True


def test_app_uses_button_sidebar_nav_not_radio():
    assert "SIDEBAR_NAV" in _APP
    assert "def _render_sidebar_nav" in _APP
    assert "tt-nav-item-active" in _APP
    # Must not use st.radio for the main sidebar menu anymore
    side_nav_fn = _APP[
        _APP.index("def _render_sidebar_nav") : _APP.index(
            "if \"logged_in\" not in st.session_state"
        )
    ]
    assert "st.radio" not in side_nav_fn
    assert "st.button" in side_nav_fn


def test_sidebar_css_has_active_item_and_flat_buttons():
    assert ".tt-nav-item-active" in _STYLES
    assert ".tt-nav-bar" in _STYLES
    assert '[data-testid="stSidebar"] div.stButton > button' in _STYLES
    assert "background: transparent !important" in _STYLES
