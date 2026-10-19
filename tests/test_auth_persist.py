"""Signed browser session tokens for reconnect / tab-sleep restore."""

from __future__ import annotations

import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def test_session_token_roundtrip():
    from tt_core.auth_persist import make_session_token, parse_session_token

    token = make_session_token(user="Tim", role="Member", avatar="http://x", ttl_days=14)
    data = parse_session_token(token)
    assert data is not None
    assert data["user"] == "Tim"
    assert data["role"] == "Member"
    assert data["avatar"] == "http://x"


def test_session_token_rejects_tamper_and_expiry():
    from tt_core import auth_persist as ap

    token = ap.make_session_token(user="Tim", role="Leader", ttl_days=14)
    bad = token[:-2] + ("aa" if not token.endswith("aa") else "bb")
    assert ap.parse_session_token(bad) is None
    assert ap.parse_session_token("") is None
    assert ap.parse_session_token(None) is None

    expired = ap.make_session_token(user="Tim", role="Member", ttl_days=14)
    # Force-expire by rewriting payload with e in the past
    body, _sig = expired.split(".", 1)
    import base64
    import hashlib
    import hmac
    import json

    raw = base64.urlsafe_b64decode(body + "=" * (-len(body) % 4))
    payload = json.loads(raw.decode("utf-8"))
    payload["e"] = int(time.time()) - 10
    new_body = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    ).decode("ascii").rstrip("=")
    sig = base64.urlsafe_b64encode(
        hmac.new(ap._secret().encode("utf-8"), new_body.encode("ascii"), hashlib.sha256).digest()
    ).decode("ascii").rstrip("=")
    assert ap.parse_session_token(f"{new_body}.{sig}") is None


def test_app_wires_persist_and_restore():
    src = (_ROOT / "app.py").read_text(encoding="utf-8")
    assert "try_restore_session" in src
    assert "persist_browser_session" in src
    assert "clear_browser_session" in src
    logout = src[src.index('key="sidebar_logout"') : src.index("if PHONE:")]
    assert "clear_browser_session" in logout
