"""iPad / desktop sidebar nav polish."""

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


def test_app_uses_sidebar_nav_flag():
    assert "SIDEBAR_NAV" in _APP
    assert "is_tablet" in _APP
    assert "is_phone" in _APP
    assert "tt-side-nav-label" in _APP
    assert "tt-side-brand" in _APP


def test_sidebar_css_is_flat_rail_not_card_stack():
    assert "[data-testid=\"stSidebar\"] div[role=\"radiogroup\"] label:has(input:checked)" in _STYLES
    assert "border-left: 3px solid" in _STYLES or "border-left: 3px solid var(--gold)" in _STYLES
    # Must not restyle sidebar items as bordered white cards
    assert ".tt-side-nav-label" in _STYLES
    assert "Hide Streamlit radio control" in _STYLES or "radio control" in _STYLES.lower()
