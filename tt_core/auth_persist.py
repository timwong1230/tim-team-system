"""Simple in-memory idle timeout — no browser auto-restore.

Previous localStorage/cookie persistence made logout unreliable. We only track
last activity in ``st.session_state`` and expire after ``IDLE_SECONDS`` of no
interaction (default 1 hour).
"""

from __future__ import annotations

import os
import time

import streamlit as st

# 1 hour idle → auto logout (override with TIM_TEAM_IDLE_SECONDS)
IDLE_SECONDS = int(os.environ.get("TIM_TEAM_IDLE_SECONDS", str(60 * 60)))
_LAST_ACTIVE_KEY = "_tt_last_active"
_CLEARED_LEGACY_KEY = "_tt_cleared_legacy_sess"


def clear_legacy_browser_session() -> None:
    """One-shot: wipe old 14-day localStorage/cookie tokens so logout works again."""
    if st.session_state.get(_CLEARED_LEGACY_KEY):
        return
    st.session_state[_CLEARED_LEGACY_KEY] = True
    script = """
<script>
(function () {
  try {
    localStorage.removeItem('tt_sess_v1');
    document.cookie = 'tt_sess_v1=; Max-Age=0; Path=/; SameSite=Lax';
  } catch (e) {}
  try {
    var url = new URL(window.location.href);
    if (url.searchParams.has('tt_sess')) {
      url.searchParams.delete('tt_sess');
      window.history.replaceState({}, '', url.toString());
    }
  } catch (e) {}
})();
</script>
"""
    try:
        st.html(script, unsafe_allow_javascript=True)
    except Exception:
        pass
    try:
        qp = st.query_params
        if "tt_sess" in qp:
            del qp["tt_sess"]
    except Exception:
        pass


def touch_activity() -> None:
    """Record that the user interacted this run."""
    st.session_state[_LAST_ACTIVE_KEY] = time.time()


def idle_expired(*, idle_seconds: int | None = None) -> bool:
    """True if last activity is older than idle window."""
    limit = int(idle_seconds if idle_seconds is not None else IDLE_SECONDS)
    last = st.session_state.get(_LAST_ACTIVE_KEY)
    if last is None:
        return False
    try:
        return (time.time() - float(last)) > max(60, limit)
    except Exception:
        return False


def force_logout_idle() -> None:
    """Clear login flags after idle expiry."""
    st.session_state["logged_in"] = False
    st.session_state.pop("user", None)
    st.session_state.pop("role", None)
    st.session_state.pop("avatar", None)
    st.session_state.pop(_LAST_ACTIVE_KEY, None)
