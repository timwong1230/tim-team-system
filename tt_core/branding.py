"""App logo / brand helpers for Streamlit + PWA."""

from __future__ import annotations

import base64
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"

# On-screen product name (login / home copy) — keep TIM TEAM
BRAND_NAME = "TIM TEAM"
BRAND_APP = "TIM TEAM APP"
BRAND_SYSTEM = "TIM TEAM SYSTEM"

# App icon art (replaces the old crown favicon / home-screen icon)
LOGO_JPG = STATIC / "ace_team_logo.jpg"
ICON_180 = STATIC / "app_icon_180.png"
ICON_192 = STATIC / "app_icon_192.png"
ICON_512 = STATIC / "app_icon_512.png"


def logo_path() -> str:
    """Absolute path to icon file if present."""
    for p in (ICON_180, ICON_512, LOGO_JPG):
        if p.exists():
            return str(p)
    return ""


def page_icon_arg():
    """Value for st.set_page_config(page_icon=...). Prefer repo-relative path."""
    for rel in ("static/app_icon_180.png", "static/app_icon_512.png", "static/ace_team_logo.jpg"):
        if (ROOT / rel).exists():
            return rel
    return "🃏"


@lru_cache(maxsize=4)
def _b64(path: str) -> str:
    data = Path(path).read_bytes()
    return base64.b64encode(data).decode("ascii")


def icon_data_uri(size: int = 180) -> str:
    """PNG data URI for apple-touch-icon / favicon injection."""
    path = ICON_180 if size <= 180 else ICON_192 if size <= 192 else ICON_512
    if not path.exists():
        path = next((p for p in (ICON_180, ICON_192, ICON_512, LOGO_JPG) if p.exists()), None)
    if path is None:
        return ""
    mime = "image/jpeg" if path.suffix.lower() in {".jpg", ".jpeg"} else "image/png"
    return f"data:{mime};base64,{_b64(str(path))}"
