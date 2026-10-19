"""Idle-timeout session (no browser auto-restore)."""

from __future__ import annotations

import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def test_idle_expired_after_one_hour():
    from tt_core import auth_persist as ap

    fake = {"_tt_last_active": time.time() - 3700}
    with patch.object(ap, "st") as st_mock:
        st_mock.session_state = fake
        assert ap.idle_expired(idle_seconds=3600) is True

    fake2 = {"_tt_last_active": time.time() - 60}
    with patch.object(ap, "st") as st_mock:
        st_mock.session_state = fake2
        assert ap.idle_expired(idle_seconds=3600) is False


def test_touch_and_force_logout():
    from tt_core import auth_persist as ap

    state = {
        "logged_in": True,
        "user": "Tim",
        "role": "Member",
        "avatar": "x",
        "_tt_last_active": 1,
    }
    with patch.object(ap, "st") as st_mock:
        st_mock.session_state = state
        ap.touch_activity()
        assert state["_tt_last_active"] > 1
        ap.force_logout_idle()
        assert state["logged_in"] is False
        assert "user" not in state
        assert "_tt_last_active" not in state


def test_app_no_longer_auto_restores_browser_session():
    src = (_ROOT / "app.py").read_text(encoding="utf-8")
    assert "try_restore_session" not in src
    assert "persist_browser_session" not in src
    assert "clear_legacy_browser_session" in src
    assert "idle_expired" in src
    assert "touch_activity" in src
    assert "force_logout_idle" in src

    auth = (_ROOT / "tt_core" / "auth_persist.py").read_text(encoding="utf-8")
    assert "IDLE_SECONDS" in auth
    assert "localStorage.setItem" not in auth  # no more persist-on-login
    assert "tt_sess_v1" in auth  # still clears legacy key


def test_default_idle_is_one_hour():
    from tt_core.auth_persist import IDLE_SECONDS

    assert IDLE_SECONDS == 3600
