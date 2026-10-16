"""Dark mode CSS follows prefers-color-scheme for iPhone night mode."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tt_core.styles import CUSTOM_CSS  # noqa: E402


def test_dark_mode_media_query():
    assert "@media (prefers-color-scheme: dark)" in CUSTOM_CSS
    assert "color-scheme: dark" in CUSTOM_CSS
    assert "--bg: #0F1419" in CUSTOM_CSS
    assert "--ink: #E8EAED" in CUSTOM_CSS
    # Widget labels forced readable
    assert 'div[role="radiogroup"] label' in CUSTOM_CSS
    assert "stWidgetLabel" in CUSTOM_CSS


def test_mf_steps_use_classes():
    src = (_ROOT / "app.py").read_text(encoding="utf-8")
    assert 'class="mf-steps"' in src
    assert 'class="mf-step mf-step-active"' in src
    assert ".mf-step" in CUSTOM_CSS


if __name__ == "__main__":
    test_dark_mode_media_query()
    test_mf_steps_use_classes()
    print("dark mode css ok")
