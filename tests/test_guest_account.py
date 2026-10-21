"""Guest trial account — login OK, hidden from team ops."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def test_is_guest_account():
    from tt_core.data import is_guest_account

    assert is_guest_account("guest", "Guest")
    assert is_guest_account("Guest", "Member")  # username wins
    assert is_guest_account("Tim", "Guest")
    assert not is_guest_account("Tim", "Member")
    assert not is_guest_account("Admin", "Leader")


def test_get_team_users_excludes_guest():
    from tt_core import data as d

    fake = pd.DataFrame(
        [
            {"username": "Tim", "password": "1234", "role": "Member", "team": "Tim Team", "recruit": 0, "avatar": "", "last_read": ""},
            {"username": "guest", "password": "1234", "role": "Guest", "team": "Tim Team", "recruit": 0, "avatar": "", "last_read": ""},
            {"username": "Admin", "password": "x", "role": "Leader", "team": "Tim Team", "recruit": 0, "avatar": "", "last_read": ""},
            {"username": "Wilson", "password": "x", "role": "Member", "team": "Tim Team", "recruit": 0, "avatar": "", "last_read": ""},
        ]
    )
    with patch.object(d, "read_data", return_value=fake):
        clean = d.get_clean_users()
        assert "guest" in set(clean["username"])
        assert "Wilson" not in set(clean["username"])  # inactive
        team = d.get_team_users()
        names = set(team["username"].astype(str))
        assert "guest" not in names
        assert "Tim" in names
        assert "Admin" in names


def test_login_guest():
    from tt_core import data as d

    fake = pd.DataFrame(
        [
            {"username": "guest", "password": "1234", "role": "Guest", "team": "Tim Team", "recruit": 0, "avatar": "", "last_read": ""},
        ]
    )
    with patch.object(d, "read_data", return_value=fake):
        with patch.object(d, "ensure_guest_user", return_value=True):
            rows = d.login("guest", "1234")
            assert rows and rows[0][0] == "guest"
            assert d.login("Guest", "1234")  # case-insensitive
            assert not d.login("guest", "wrong")


def test_login_guest_builtin_without_sheets():
    """Guest must work even when users sheet/cache is empty."""
    from tt_core import data as d

    empty = pd.DataFrame(
        columns=["username", "password", "role", "team", "recruit", "avatar", "last_read"]
    )
    with patch.object(d, "read_data", return_value=empty):
        with patch.object(d, "ensure_guest_user", return_value=True):
            rows = d.login("guest", "1234")
            assert rows
            assert rows[0][0] == "guest"
            assert rows[0][2] == "Guest"
            assert d.login("GUEST", "1234")
            assert not d.login("guest", "9999")


def test_login_guest_password_float_cell():
    from tt_core import data as d

    fake = pd.DataFrame(
        [
            {
                "username": "guest",
                "password": 1234.0,
                "role": "Guest",
                "team": "Tim Team",
                "recruit": 0,
                "avatar": "",
                "last_read": "",
            },
        ]
    )
    with patch.object(d, "read_data", return_value=fake):
        assert d.login("guest", "1234")


def test_get_data_excludes_guest():
    from tt_core import data as d

    users = pd.DataFrame(
        [
            {"username": "Tim", "password": "1", "role": "Member", "team": "Tim Team", "recruit": 1, "avatar": "", "last_read": ""},
            {"username": "guest", "password": "1234", "role": "Guest", "team": "Tim Team", "recruit": 0, "avatar": "", "last_read": ""},
        ]
    )
    empty = pd.DataFrame(columns=["username", "month", "amount"])
    with patch.object(d, "read_data", side_effect=lambda sheet: users if sheet == "users" else empty):
        df = d.get_data("Yearly")
        assert "guest" not in set(df["username"].astype(str))
        assert "Tim" in set(df["username"].astype(str))


def test_db_seeds_guest_and_kk():
    from tt_core.constants import SEED_USERS

    assert ("guest", "1234", "Guest") in SEED_USERS
    assert ("KK", "1234", "Member") in SEED_USERS
    src = (_ROOT / "tt_core" / "db.py").read_text(encoding="utf-8")
    assert "SEED_USERS" in src


def test_login_kk_member_builtin():
    """New colleague KK must log in even before Sheets has the row."""
    from tt_core import data as d

    empty = pd.DataFrame(
        columns=["username", "password", "role", "team", "recruit", "avatar", "last_read"]
    )
    with patch.object(d, "read_data", return_value=empty):
        with patch.object(d, "ensure_seed_users", return_value=True):
            rows = d.login("KK", "1234")
            assert rows
            assert rows[0][0] == "KK"
            assert rows[0][2] == "Member"
            assert d.login("kk", "1234")
            assert not d.login("KK", "9999")


def test_app_hides_ops_menus_for_guest():
    src = (_ROOT / "app.py").read_text(encoding="utf-8")
    assert "is_guest" in src
    assert "試用主頁" in src
    assert "get_team_users" in src
    assert "Trial account: client tools only" in src
    # Guest branch lists client tools; ops menus live only in the else branch
    guest_start = src.index("if is_guest:")
    else_start = src.index("else:", guest_start)
    guest_block = src[guest_start:else_start]
    assert "打卡 Check-in" not in guest_block
    assert "團隊 Dashboard" not in guest_block
    assert "RECRUIT_TOOLS_MENU" not in guest_block
    assert "CLIENT_TOOLS_MENU" in guest_block


def test_app_guest_has_logout_path():
    src = (_ROOT / "app.py").read_text(encoding="utf-8")
    assert "def _do_logout" in src
    assert "guest_home_logout" in src
    assert "flush_pending_logout_clear" in src
