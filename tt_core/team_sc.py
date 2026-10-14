"""Team SC (Year-to-date) manual value stored in system_settings."""

from __future__ import annotations

# Keep key inline so Cloud never depends on a constants reload for this path.
_TEAM_SC_KEY = "team_sc"


def get_team_sc(fallback: float = 0.0) -> float:
    """Return Leader-entered Team SC, or fallback if unset / unavailable."""
    try:
        from tt_core.iris_drive import get_setting

        raw = str(get_setting(_TEAM_SC_KEY, "") or "").strip()
    except Exception:
        return float(fallback or 0)

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
    try:
        from tt_core.iris_drive import set_setting

        return bool(set_setting(_TEAM_SC_KEY, str(float(amount))))
    except Exception:
        return False
