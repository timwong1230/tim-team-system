"""Send order includes a Not on Menu row that was typed but not tapped Add."""

from __future__ import annotations

from pathlib import Path

_POLAR = Path(__file__).resolve().parents[1] / "polar-order"


def _send_chunk(js: str) -> str:
    start = js.index('getElementById("submitOrder")')
    return js[start : start + 500]


def test_staff_send_commits_pending_not_on_menu():
    js = (_POLAR / "static/js/staff_order.js").read_text(encoding="utf-8")
    chunk = _send_chunk(js)
    assert "commitPendingNom()" in chunk
    assert chunk.index("commitPendingNom()") < chunk.index("Cart is empty")
    # Chinese (and other non-ascii) names must not share one cart key.
    assert "customName === name" in js
    assert 'replace(/[^a-z0-9]+/g, "-")' not in js.split("function addNomLine")[1].split("function commitPendingNom")[0]


def test_boss_send_commits_pending_not_on_menu():
    js = (_POLAR / "static/js/boss.js").read_text(encoding="utf-8")
    chunk = _send_chunk(js)
    assert "commitPendingNom()" in chunk
    assert chunk.index("commitPendingNom()") < chunk.index("Cart is empty")
    assert "customName === name" in js
