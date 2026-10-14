"""Team SC (Year-to-date) manual value stored in system_settings.

Uses tt_core.db only — never imports iris_drive/constants at call time
(Streamlit Cloud has repeatedly failed those lazy imports).
"""

from __future__ import annotations

import datetime

_TEAM_SC_KEY = "team_sc"
_SETTINGS_SHEET = "system_settings"


def get_team_sc(fallback: float = 0.0) -> float:
    """Return Leader-entered Team SC, or fallback if unset / unavailable."""
    try:
        from tt_core.db import read_data

        df = read_data(_SETTINGS_SHEET)
        if df is None or getattr(df, "empty", True) or "key" not in df.columns:
            return float(fallback or 0)
        hit = df[df["key"].astype(str) == _TEAM_SC_KEY]
        if hit.empty:
            return float(fallback or 0)
        raw = str(hit.iloc[0].get("value", "") or "").strip()
        if not raw:
            return float(fallback or 0)
        return float(
            raw.replace(",", "")
            .replace("$", "")
            .replace("HK$", "")
            .replace(" ", "")
        )
    except Exception:
        return float(fallback or 0)


def set_team_sc(amount: float) -> bool:
    try:
        from tt_core.db import read_data, run_query_gs

        value = str(float(amount))
        now = str(datetime.datetime.now())
        df = read_data(_SETTINGS_SHEET)
        if df is not None and not df.empty and "key" in df.columns:
            hit = df[df["key"].astype(str) == _TEAM_SC_KEY]
            if (
                not hit.empty
                and "id" in df.columns
                and str(hit.iloc[0].get("id", "")).strip()
            ):
                return bool(
                    run_query_gs(
                        "UPDATE",
                        _SETTINGS_SHEET,
                        {"value": value, "updated_at": now},
                        row_id=hit.iloc[0]["id"],
                    )
                )
        return bool(
            run_query_gs(
                "INSERT",
                _SETTINGS_SHEET,
                {"key": _TEAM_SC_KEY, "value": value, "updated_at": now},
            )
        )
    except Exception:
        return False
