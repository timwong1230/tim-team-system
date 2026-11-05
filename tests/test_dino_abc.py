"""Dino ABC stays a self-contained iPad letter game."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GAME = ROOT / "dino-letters"
HTML = (GAME / "index.html").read_text(encoding="utf-8")


def test_game_files_exist():
    assert (GAME / "index.html").is_file()
    assert (GAME / "manifest.webmanifest").is_file()
    assert (GAME / "icon-180.png").stat().st_size > 1000
    assert (GAME / "icon-512.png").stat().st_size > 1000
    assert (GAME / "fonts" / "andika-400.woff2").is_file()
    assert (GAME / "fonts" / "andika-700.woff2").is_file()
    assert (GAME / "fonts" / "OFL.txt").is_file()


def test_ipad_shell_and_offline():
    assert "viewport-fit=cover" in HTML
    assert 'apple-mobile-web-app-capable" content="yes"' in HTML
    assert "touch-action: manipulation" in HTML
    assert "fonts.googleapis.com" not in HTML
    assert "fonts.gstatic.com" not in HTML
    assert "<script src=" not in HTML


def test_curriculum_starts_with_distinct_letters_and_covers_alphabet():
    start = HTML.index('const ORDER = [')
    order = HTML[start:HTML.index("];", start)]
    found = []
    token = ""
    for ch in order:
        if ch.isalpha():
            token += ch
        elif token:
            if len(token) == 1:
                found.append(token)
            token = ""
    if token and len(token) == 1:
        found.append(token)
    assert found[:4] == ["D", "O", "A", "T"]
    assert sorted(found) == list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    assert len(found) == 26
    for letter in found:
        assert f'{letter}: {{ label:' in HTML


def test_no_punishing_timer_and_attention_supports_are_present():
    assert "setInterval" not in HTML
    assert "hintCorrect" in HTML
    assert "trail" in HTML
    assert "唔會扣分" in HTML or "唔會罰" in HTML
