"""Browser session persist + 30-minute idle logout."""

from __future__ import annotations

import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def test_default_idle_is_thirty_minutes():
    from tt_core.auth_persist import IDLE_SECONDS

    assert IDLE_SECONDS == 1800


def test_idle_expired_after_thirty_minutes():
    from tt_core import auth_persist as ap

    fake = {"_tt_last_active": time.time() - 1900}
    with patch.object(ap, "st") as st_mock:
        st_mock.session_state = fake
        assert ap.idle_expired(idle_seconds=1800) is True

    fake2 = {"_tt_last_active": time.time() - 60}
    with patch.object(ap, "st") as st_mock:
        st_mock.session_state = fake2
        assert ap.idle_expired(idle_seconds=1800) is False


def test_token_roundtrip_and_idle_reject():
    from tt_core import auth_persist as ap

    with patch.object(ap, "st") as st_mock:
        st_mock.secrets = {}
        st_mock.session_state = {}
        now = time.time()
        token = ap.make_session_token(
            user="Tim",
            role="Leader",
            avatar="🦁",
            last_active=now,
            idle_seconds=1800,
        )
        ok = ap.parse_session_token(token, idle_seconds=1800, now=now + 60)
        assert ok is not None
        assert ok["user"] == "Tim"
        assert ok["role"] == "Leader"

        stale = ap.make_session_token(
            user="Tim",
            role="Leader",
            last_active=now - 2000,
            idle_seconds=1800,
        )
        assert ap.parse_session_token(stale, idle_seconds=1800, now=now) is None


def test_touch_and_force_logout_clears_browser():
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
        st_mock.secrets = {}
        st_mock.html = MagicMock()
        st_mock.query_params = {}
        ap.touch_activity(persist=True)
        assert state["_tt_last_active"] > 1
        ap.force_logout_idle()
        assert state["logged_in"] is False
        assert "user" not in state
        assert state.get("_tt_logout_block") is True
        # clear script should run
        assert st_mock.html.called


def test_try_restore_respects_logout_block():
    from tt_core import auth_persist as ap

    state = {"_tt_logout_block": True}
    with patch.object(ap, "st") as st_mock:
        st_mock.session_state = state
        st_mock.context = MagicMock()
        st_mock.context.cookies = {}
        st_mock.query_params = {}
        assert ap.try_restore_session() is False


def test_try_restore_from_cookie():
    from tt_core import auth_persist as ap

    with patch.object(ap, "st") as st_mock:
        st_mock.secrets = {}
        st_mock.session_state = {}
        st_mock.html = MagicMock()
        st_mock.query_params = {}
        token = ap.make_session_token(
            user="Amy", role="Member", last_active=time.time()
        )
        st_mock.context = MagicMock()
        st_mock.context.cookies = {ap._LS_KEY: token}
        assert ap.try_restore_session() is True
        assert st_mock.session_state["logged_in"] is True
        assert st_mock.session_state["user"] == "Amy"


def test_guest_session_not_persisted_or_restored():
    from tt_core import auth_persist as ap

    state = {}
    with patch.object(ap, "st") as st_mock:
        st_mock.session_state = state
        st_mock.secrets = {}
        st_mock.html = MagicMock()
        st_mock.query_params = {}
        st_mock.context = MagicMock()
        token = ap.persist_browser_session(user="guest", role="Guest")
        assert token == ""
        assert not st_mock.html.called  # no localStorage write for guest

        # Even an old guest cookie must not restore
        guest_tok = ap.make_session_token(
            user="guest", role="Guest", last_active=time.time()
        )
        st_mock.context.cookies = {ap._LS_KEY: guest_tok}
        assert ap.try_restore_session() is False
        assert not state.get("logged_in")


def test_logout_sets_sync_tt_out_query():
    from tt_core import auth_persist as ap

    state = {"logged_in": True, "user": "guest"}
    qp: dict = {}
    with patch.object(ap, "st") as st_mock:
        st_mock.session_state = state
        st_mock.html = MagicMock()
        st_mock.query_params = qp
        ap.clear_browser_session()
        assert state.get("_tt_logout_block") is True
        assert qp.get("tt_out") == "1"
        assert ap._logout_blocked() is True


def test_hard_logout_js_forces_tt_out_url():
    from tt_core import auth_persist as ap

    state: dict = {}
    with patch.object(ap, "st") as st_mock:
        st_mock.session_state = state
        st_mock.html = MagicMock()
        st_mock.query_params = {}
        ap.clear_browser_session(hard_reload=True)
        html = "".join(
            str(c.args[0]) for c in st_mock.html.call_args_list if c.args
        )
        assert "location.replace" in html
        assert "tt_out" in html
        assert state.get("_tt_logout_block") is True


def test_app_wires_persist_and_idle():
    src = (_ROOT / "app.py").read_text(encoding="utf-8")
    assert "try_restore_session" in src
    assert "persist_browser_session" in src
    assert "clear_browser_session" in src
    assert "hard_reload=True" in src
    assert "home_phone_logout" in src
    assert "idle_expired" in src
    assert "touch_activity" in src
    assert "force_logout_idle" in src
    assert "30 分鐘" in src

    auth = (_ROOT / "tt_core" / "auth_persist.py").read_text(encoding="utf-8")
    assert "IDLE_SECONDS" in auth
    assert "localStorage.setItem" in auth
    assert "tt_sess_v2" in auth
    assert "tt_logout" in auth
    assert "location.replace" in auth
