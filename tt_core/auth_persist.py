"""Persist login across Streamlit reconnects, with idle auto-logout.

Streamlit ``session_state`` dies when the websocket drops (common on iPhone /
backgrounded PWA). A signed token in cookie + localStorage restores the user
after wake — but only if last activity is within ``IDLE_SECONDS`` (default
30 minutes). Manual logout clears the token and sets a short logout block so
restore cannot bounce the user back in.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any

import streamlit as st

# Idle window before auto logout (override with TIM_TEAM_IDLE_SECONDS)
IDLE_SECONDS = int(os.environ.get("TIM_TEAM_IDLE_SECONDS", str(30 * 60)))
# Hard cap even if somehow kept "active" (override with TIM_TEAM_SESSION_DAYS)
_TTL_DAYS = int(os.environ.get("TIM_TEAM_SESSION_DAYS", "7"))
_LS_KEY = "tt_sess_v2"
_LEGACY_LS_KEY = "tt_sess_v1"
_LOGOUT_COOKIE = "tt_logout"
_LOGOUT_QP = "tt_out"
_LAST_ACTIVE_KEY = "_tt_last_active"
_LOGOUT_BLOCK_KEY = "_tt_logout_block"
_BRIDGE_DONE_KEY = "_tt_sess_bridge_done"
_NEED_CLEAR_JS_KEY = "_tt_need_clear_js"


def _is_guest(user: str = "", role: str = "") -> bool:
    try:
        from tt_core.data import is_guest_account

        return bool(is_guest_account(user, role))
    except Exception:
        u = str(user or "").strip().lower()
        r = str(role or "").strip().lower()
        return u == "guest" or r == "guest"


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64url_decode(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode((text or "") + pad)


def _secret() -> str:
    try:
        sec = st.secrets.get("TT_SESSION_SECRET") or st.secrets.get("session_secret")
        if sec:
            return str(sec)
    except Exception:
        pass
    env = os.environ.get("TIM_TEAM_SESSION_SECRET")
    if env:
        return env
    # Internal team app fallback — override via secrets when possible
    return "tim-team-sess-v2-rotate-me"


def make_session_token(
    *,
    user: str,
    role: str,
    avatar: str = "",
    last_active: float | None = None,
    ttl_days: int | None = None,
    idle_seconds: int | None = None,
) -> str:
    """Return signed token ``payload.sig`` including last-active for idle checks."""
    days = int(ttl_days if ttl_days is not None else _TTL_DAYS)
    la = float(last_active if last_active is not None else time.time())
    # Encode idle limit so older tokens stay compatible if env changes
    idle = int(idle_seconds if idle_seconds is not None else IDLE_SECONDS)
    payload = {
        "u": str(user or "").strip(),
        "r": str(role or "Member").strip() or "Member",
        "a": str(avatar or "")[:500],
        "la": int(la),
        "idle": max(60, idle),
        "e": int(time.time()) + max(1, days) * 86400,
        "v": 2,
    }
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    body = _b64url(raw)
    sig = _b64url(
        hmac.new(_secret().encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest()
    )
    return f"{body}.{sig}"


def parse_session_token(
    token: str | None,
    *,
    idle_seconds: int | None = None,
    now: float | None = None,
) -> dict[str, Any] | None:
    """Validate token; return ``{user, role, avatar, last_active}`` or None."""
    if not token or "." not in token:
        return None
    ts = float(now if now is not None else time.time())
    try:
        body, sig = token.split(".", 1)
        expect = _b64url(
            hmac.new(_secret().encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest()
        )
        if not hmac.compare_digest(sig, expect):
            return None
        payload = json.loads(_b64url_decode(body).decode("utf-8"))
        if int(payload.get("e") or 0) < int(ts):
            return None
        user = str(payload.get("u") or "").strip()
        if not user:
            return None
        la = float(payload.get("la") or 0)
        if la <= 0:
            return None
        # Prefer token's encoded idle, then caller override, then module default
        limit = int(
            idle_seconds
            if idle_seconds is not None
            else payload.get("idle")
            if payload.get("idle") is not None
            else IDLE_SECONDS
        )
        if (ts - la) > max(60, limit):
            return None
        return {
            "user": user,
            "role": str(payload.get("r") or "Member").strip() or "Member",
            "avatar": str(payload.get("a") or ""),
            "last_active": la,
        }
    except Exception:
        return None


def _apply_session(data: dict[str, Any]) -> None:
    st.session_state["logged_in"] = True
    st.session_state["user"] = data["user"]
    st.session_state["role"] = data["role"]
    st.session_state["avatar"] = data.get("avatar") or ""
    st.session_state[_LAST_ACTIVE_KEY] = float(
        data.get("last_active") or time.time()
    )
    st.session_state.pop(_LOGOUT_BLOCK_KEY, None)


def _logout_blocked() -> bool:
    if st.session_state.get(_LOGOUT_BLOCK_KEY):
        return True
    try:
        # Sync flag — survives rerun even when clear JS has not run yet
        if st.query_params.get(_LOGOUT_QP):
            return True
    except Exception:
        pass
    try:
        cookies = st.context.cookies
        if cookies is not None and cookies.get(_LOGOUT_COOKIE):
            return True
    except Exception:
        pass
    return False


def _inject_clear_storage_js(*, hard_reload: bool = False) -> None:
    """Client-side wipe — call on a stable page (login), not only before rerun.

    When ``hard_reload`` is True (manual 登出), force the browser URL to
    ``?tt_out=1`` via ``location.replace`` so a dead Streamlit session cannot
    restore from an old cookie/localStorage without the logout flag.
    """
    key_js = json.dumps(_LS_KEY)
    legacy_js = json.dumps(_LEGACY_LS_KEY)
    logout_js = json.dumps(_LOGOUT_COOKIE)
    out_js = json.dumps(_LOGOUT_QP)
    hard_js = "true" if hard_reload else "false"
    script = f"""
<script>
(function () {{
  try {{
    var key = {key_js};
    var legacy = {legacy_js};
    localStorage.removeItem(key);
    localStorage.removeItem(legacy);
    document.cookie = key + "=; Max-Age=0; Path=/; SameSite=Lax";
    document.cookie = legacy + "=; Max-Age=0; Path=/; SameSite=Lax";
    document.cookie = {logout_js} + "=1; Max-Age=86400; Path=/; SameSite=Lax";
  }} catch (e) {{}}
  try {{
    var url = new URL(window.location.href);
    url.searchParams.delete('tt_sess');
    url.searchParams.set({out_js}, '1');
    if ({hard_js}) {{
      window.location.replace(url.toString());
    }} else {{
      window.history.replaceState({{}}, '', url.toString());
    }}
  }} catch (e) {{}}
}})();
</script>
"""
    try:
        st.html(script, unsafe_allow_javascript=True)
    except Exception:
        pass


def flush_pending_logout_clear() -> None:
    """Run deferred localStorage/cookie clear on the login screen."""
    if not st.session_state.get(_NEED_CLEAR_JS_KEY) and not _logout_blocked():
        return
    _inject_clear_storage_js(hard_reload=False)
    st.session_state.pop(_NEED_CLEAR_JS_KEY, None)


def persist_browser_session(
    *,
    user: str,
    role: str,
    avatar: str = "",
    last_active: float | None = None,
) -> str:
    """Save signed session to localStorage + cookie; clear logout block.

    Guest trial accounts are never persisted — they were bouncing back in
    after 「登出」via localStorage restore.
    """
    if _is_guest(user, role):
        st.session_state[_LAST_ACTIVE_KEY] = float(
            last_active if last_active is not None else time.time()
        )
        return ""
    la = float(last_active if last_active is not None else time.time())
    token = make_session_token(
        user=user, role=role, avatar=avatar, last_active=la
    )
    st.session_state[_LAST_ACTIVE_KEY] = la
    st.session_state.pop(_LOGOUT_BLOCK_KEY, None)
    st.session_state.pop(_NEED_CLEAR_JS_KEY, None)
    try:
        qp = st.query_params
        if _LOGOUT_QP in qp:
            del qp[_LOGOUT_QP]
    except Exception:
        pass
    token_js = json.dumps(token)
    key_js = json.dumps(_LS_KEY)
    legacy_js = json.dumps(_LEGACY_LS_KEY)
    logout_js = json.dumps(_LOGOUT_COOKIE)
    # Cookie lives a bit longer than idle; idle is enforced via token ``la``
    max_age = max(IDLE_SECONDS * 2, 3600)
    script = f"""
<script>
(function () {{
  try {{
    var key = {key_js};
    var legacy = {legacy_js};
    var token = {token_js};
    localStorage.setItem(key, token);
    localStorage.removeItem(legacy);
    var maxAge = {int(max_age)};
    document.cookie = key + "=" + encodeURIComponent(token)
      + "; Max-Age=" + maxAge + "; Path=/; SameSite=Lax";
    document.cookie = legacy + "=; Max-Age=0; Path=/; SameSite=Lax";
    document.cookie = {logout_js} + "=; Max-Age=0; Path=/; SameSite=Lax";
  }} catch (e) {{}}
}})();
</script>
"""
    try:
        st.html(script, unsafe_allow_javascript=True)
    except Exception:
        pass
    return token


def clear_browser_session(*, hard_reload: bool = False) -> None:
    """Drop persisted session and block restore until next successful login.

    Sets sync flags (session_state + ``?tt_out=1``) immediately, and defers the
    localStorage wipe to the next stable render so ``st.rerun()`` cannot skip JS.

    Pass ``hard_reload=True`` for the 登出 button so the browser navigates to a
    URL that already contains ``tt_out=1`` (survives full remount / PWA wake).
    """
    st.session_state[_LOGOUT_BLOCK_KEY] = True
    st.session_state[_NEED_CLEAR_JS_KEY] = True
    st.session_state.pop(_LAST_ACTIVE_KEY, None)
    st.session_state.pop(_BRIDGE_DONE_KEY, None)
    st.session_state.pop("_tt_last_persist", None)
    try:
        st.query_params[_LOGOUT_QP] = "1"
    except Exception:
        pass
    try:
        qp = st.query_params
        if "tt_sess" in qp:
            del qp["tt_sess"]
    except Exception:
        pass
    # Best-effort clear now; flush_pending_logout_clear runs again on login page
    _inject_clear_storage_js(hard_reload=hard_reload)


# Back-compat alias used by older app paths
def clear_legacy_browser_session() -> None:
    clear_browser_session()


def touch_activity(*, persist: bool = False) -> None:
    """Record that the user interacted this run.

    When ``persist`` is True (or every ~2 minutes while logged in), refresh the
    browser token so idle countdown survives phone sleeps / reconnects.
    Guest sessions are never written to the browser.
    """
    now = time.time()
    st.session_state[_LAST_ACTIVE_KEY] = now
    user = str(st.session_state.get("user") or "").strip()
    role = str(st.session_state.get("role") or "")
    if not user or _is_guest(user, role):
        return
    if not persist:
        last_persist = float(st.session_state.get("_tt_last_persist") or 0)
        # Refresh cookie at least every 2 minutes of active use
        if now - last_persist < 120:
            return
    try:
        persist_browser_session(
            user=user,
            role=role or "Member",
            avatar=str(st.session_state.get("avatar") or ""),
            last_active=now,
        )
        st.session_state["_tt_last_persist"] = now
    except Exception:
        pass


def idle_expired(*, idle_seconds: int | None = None) -> bool:
    """True if last activity is older than idle window (session_state clock)."""
    limit = int(idle_seconds if idle_seconds is not None else IDLE_SECONDS)
    last = st.session_state.get(_LAST_ACTIVE_KEY)
    if last is None:
        return False
    try:
        return (time.time() - float(last)) > max(60, limit)
    except Exception:
        return False


def force_logout_idle() -> None:
    """Clear login flags after idle expiry (and wipe browser token)."""
    st.session_state["logged_in"] = False
    st.session_state.pop("user", None)
    st.session_state.pop("role", None)
    st.session_state.pop("avatar", None)
    st.session_state.pop(_LAST_ACTIVE_KEY, None)
    try:
        clear_browser_session()
    except Exception:
        st.session_state[_LOGOUT_BLOCK_KEY] = True


def try_restore_session() -> bool:
    """If not logged in, restore from cookie / query / localStorage bridge.

    Returns True when a restore applied (caller should ``st.rerun()``).
    """
    if st.session_state.get("logged_in") and st.session_state.get("user"):
        return False
    if _logout_blocked():
        return False

    token = None
    try:
        token = st.query_params.get("tt_sess")
        if isinstance(token, (list, tuple)):
            token = token[0] if token else None
    except Exception:
        token = None

    if not token:
        try:
            cookies = st.context.cookies
            if cookies is not None:
                token = cookies.get(_LS_KEY) or cookies.get(_LEGACY_LS_KEY)
        except Exception:
            token = None

    if token:
        data = parse_session_token(str(token))
        if data:
            # Never auto-restore guest trial sessions
            if _is_guest(data.get("user") or "", data.get("role") or ""):
                clear_browser_session()
                return False
            _apply_session(data)
            # Sliding idle window — refresh last_active on successful wake
            try:
                persist_browser_session(
                    user=data["user"],
                    role=data["role"],
                    avatar=data.get("avatar") or "",
                    last_active=time.time(),
                )
            except Exception:
                pass
            # Drop bridge query param after consume
            try:
                qp = st.query_params
                if "tt_sess" in qp:
                    del qp["tt_sess"]
            except Exception:
                pass
            return True
        clear_browser_session()
        return False

    # Bridge: pull localStorage into ?tt_sess= once (phone tab wake)
    if st.session_state.get(_BRIDGE_DONE_KEY):
        return False
    st.session_state[_BRIDGE_DONE_KEY] = True
    key_js = json.dumps(_LS_KEY)
    legacy_js = json.dumps(_LEGACY_LS_KEY)
    logout_cookie_js = json.dumps(_LOGOUT_COOKIE)
    script = f"""
<script>
(function () {{
  try {{
    // Honour logout cookie — do not bounce after 登出
    if (document.cookie.split(';').some(function (c) {{
      return c.trim().indexOf({logout_cookie_js} + '=') === 0;
    }})) {{
      localStorage.removeItem({key_js});
      localStorage.removeItem({legacy_js});
      return;
    }}
    var key = {key_js};
    var legacy = {legacy_js};
    var token = localStorage.getItem(key) || localStorage.getItem(legacy);
    if (!token) return;
    var url = new URL(window.location.href);
    if (url.searchParams.get('tt_sess')) return;
    if (url.searchParams.get({json.dumps(_LOGOUT_QP)})) return;
    url.searchParams.set('tt_sess', token);
    window.location.replace(url.toString());
  }} catch (e) {{}}
}})();
</script>
"""
    try:
        st.html(script, unsafe_allow_javascript=True)
    except Exception:
        pass
    return False
