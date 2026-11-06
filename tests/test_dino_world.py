"""Dino World series: hub plus five dinosaur games for iPad."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORLD = ROOT / "dino-world"


def test_series_files_exist():
    for name in [
        "index.html",
        "abc.html",
        "chinese.html",
        "color.html",
        "numbers.html",
        "focus.html",
        "shared.css",
        "shared.js",
        "manifest.webmanifest",
        "icon-180.png",
        "icon-512.png",
        "fonts/andika-400.woff2",
        "fonts/andika-700.woff2",
    ]:
        assert (WORLD / name).exists(), name


def test_hub_lists_all_five_games():
    hub = (WORLD / "index.html").read_text(encoding="utf-8")
    for href in ["abc.html", "chinese.html", "color.html", "numbers.html", "focus.html"]:
        assert href in hub
    assert "Dino World" in hub


def test_games_share_theme_and_attention_loop():
    shared = (WORLD / "shared.js").read_text(encoding="utf-8")
    assert "drawDino" in shared
    assert "trailHtml" in shared
    for name in ["chinese.html", "color.html", "numbers.html", "focus.html"]:
        src = (WORLD / name).read_text(encoding="utf-8")
        assert "shared.js" in src
        assert 'key: "dino-' in src or "dino-hanzi" in src or "dino-color" in src or "dino-num" in src or "dino-focus" in src
        assert "trail" in src
        assert "setInterval" not in src


def test_old_dino_letters_points_at_series():
    legacy = (ROOT / "dino-letters" / "index.html").read_text(encoding="utf-8")
    assert "dino-world" in legacy
