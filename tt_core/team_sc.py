"""Team SC (Year-to-date) manual value stored in system_settings."""

from __future__ import annotations


def get_team_sc(fallback: float = 0.0) -> float:
    """Return Leader-entered Team SC, or fallback if unset."""
    from tt_core.constants import TEAM_SC_SETTING_KEY
    from tt_core.iris_drive import get_setting

    raw = str(get_setting(TEAM_SC_SETTING_KEY, "") or "").strip()
    if not raw:
        return float(fallback or 0)
    try:
        return float(
            raw.replace(",", "")
            .replace("$", "")
            .replace("HK$", "")
            .replace(" ", "")
        )
    except ValueError:
        return float(fallback or 0)


def set_team_sc(amount: float) -> bool:
    from tt_core.constants import TEAM_SC_SETTING_KEY
    from tt_core.iris_drive import set_setting

    return bool(set_setting(TEAM_SC_SETTING_KEY, str(float(amount))))
