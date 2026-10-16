"""Recruit package comparison — FWD FLDP vs peers."""

from __future__ import annotations

from tt_core.recruit_compare import (
    gate_rows,
    get_home,
    list_competitors,
    load_packages,
    snapshot_table,
    whatsapp_summary,
)


def test_packages_loaded():
    data = load_packages()
    assert "fwd" in data["companies"]
    assert {"aia", "manulife", "sunlife"} <= set(data["companies"])
    home = get_home()
    assert home["is_home"]
    assert "FLDP" in home["package"]


def test_competitors_exclude_home():
    comps = list_competitors()
    assert all(not c.get("is_home") for c in comps)
    assert len(comps) == 3


def test_snapshot_and_gates():
    from tt_core.recruit_compare import snapshot_html

    snap = snapshot_table(["aia", "sunlife"])
    assert snap[0]["公司"].startswith("富衛")
    assert len(snap) == 3
    html = snapshot_html(["aia"])
    assert "推薦 · FWD" in html
    assert "友邦" in html
    assert "1.1" in html
    rows = gate_rows("survival", ["aia"])
    assert rows[0]["is_home"]
    assert "1.1" in rows[0]["block"]["ratio"]
    assert "1.5" in rows[1]["block"]["ratio"]


def test_whatsapp_mentions_fwd_edge():
    text = whatsapp_summary(["manulife"], prospect="Chris", agent="Tim")
    assert "FLDP" in text
    assert "宏利" in text or "Manulife" in text
    assert "Chris" in text
    assert "僅供招募面談參考" in text
