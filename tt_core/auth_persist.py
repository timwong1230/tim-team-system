"""Persist login across Streamlit reconnects / phone tab sleeps.

Streamlit ``session_state`` dies when the websocket drops (common on iPhone).
We keep a signed token in ``localStorage`` + optional ``?tt_sess=`` so a refresh
can restore the user for up to ``TTL_DAYS`` without re-typing the password.
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

_TTL_DAYS = int(os.environ.get("TIM_TEAM_SESSION_DAYS", "14"))
_LS_KEY = "tt_sess_v1"


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
    return "tim-team-sess-v1-rotate-me"


def make_session_token(
    *,
    user: str,
    role: str,
    avatar: str = "",
    ttl_days: int | None = None,
) -> str:
    """Return signed token ``payload.sig``."""
    days = int(ttl_days if ttl_days is not None else _TTL_DAYS)
    payload = {
        "u": str(user or "").strip(),
        "r": str(role or "Member").strip() or "Member",
        "a": str(avatar or "")[:500],
        "e": int(time.time()) + max(1, days) * 86400,
        "v": 1,
    }
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    body = _b64url(raw)
    sig = _b64url(
        hmac.new(_secret().encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest()
    )
    return f"{body}.{sig}"


def parse_session_token(token: str | None) -> dict[str, Any] | None:
    """Validate token; return ``{user, role, avatar}`` or None."""
    if not token or "." not in token:
        return None
    try:
        body, sig = token.split(".", 1)
        expect = _b64url(
            hmac.new(_secret().encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest()
        )
        if not hmac.compare_digest(sig, expect):
            return None
        payload = json.loads(_b64url_decode(body).decode("utf-8"))
        if int(payload.get("e") or 0) < int(time.time()):
            return None
        user = str(payload.get("u") or "").strip()
        if not user:
            return None
        return {
            "user": user,
            "role": str(payload.get("r") or "Member").strip() or "Member",
            "avatar": str(payload.get("a") or ""),
        }
    except Exception:
        return None


def _apply_session(data: dict[str, Any]) -> None:
    st.session_state["logged_in"] = True
    st.session_state["user"] = data["user"]
    st.session_state["role"] = data["role"]
    st.session_state["avatar"] = data.get("avatar") or ""


def persist_browser_session(*, user: str, role: str, avatar: str = "") -> str:
    """Save signed session to localStorage (via st.html) and return the token."""
    token = make_session_token(user=user, role=role, avatar=avatar)
    token_js = json.dumps(token)
    key_js = json.dumps(_LS_KEY)
    days = max(1, _TTL_DAYS)
    script = f"""
<script>
(function () {{
  try {{
    var key = {key_js};
    var token = {token_js};
    localStorage.setItem(key, token);
    var maxAge = {days * 86400};
    document.cookie = key + "=" + encodeURIComponent(token)
      + "; Max-Age=" + maxAge + "; Path=/; SameSite=Lax";
  }} catch (e) {{}}
}})();
</script>
"""
    try:
        st.html(script, unsafe_allow_javascript=True)
    except Exception:
        pass
    try:
        st.query_params["tt_sess"] = token
    except Exception:
        pass
    return token


def clear_browser_session() -> None:
    """Drop persisted session (logout)."""
    key_js = json.dumps(_LS_KEY)
    script = f"""
<script>
(function () {{
  try {{
    var key = {key_js};
    localStorage.removeItem(key);
    document.cookie = key + "=; Max-Age=0; Path=/; SameSite=Lax";
  }} catch (e) {{}}
}})();
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


def try_restore_session() -> bool:
    """If not logged in, restore from query param / cookie / localStorage bridge.

    Returns True when a restore triggered (caller should ``st.rerun()``).
    """
    if st.session_state.get("logged_in") and st.session_state.get("user"):
        return False

    # 1) URL / cookie (server already has them on this request)
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
            token = cookies.get(_LS_KEY) if cookies is not None else None
        except Exception:
            token = None

    if token:
        data = parse_session_token(str(token))
        if data:
            _apply_session(data)
            # Refresh cookie/localStorage expiry
            try:
                persist_browser_session(
                    user=data["user"], role=data["role"], avatar=data.get("avatar") or ""
                )
            except Exception:
                pass
            return True
        # Bad / expired token — clear
        clear_browser_session()
        return False

    # 2) Bridge: pull localStorage into ?tt_sess= once (phone tab wake)
    if st.session_state.get("_tt_sess_bridge_done"):
        return False
    st.session_state["_tt_sess_bridge_done"] = True
    key_js = json.dumps(_LS_KEY)
    script = f"""
<script>
(function () {{
  try {{
    var key = {key_js};
    var token = localStorage.getItem(key);
    if (!token) return;
    var url = new URL(window.location.href);
    if (url.searchParams.get('tt_sess')) return;
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
