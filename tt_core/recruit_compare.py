"""同行新人 Package 對比 — FWD FLDP 2.0 vs AIA / Manulife / Sun Life."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

DATA_PATH = Path(__file__).resolve().parent / "data_files" / "recruit_packages.json"

GATE_KEYS = {
    "entry": "entry",
    "survival": "survival",
    "cashflow": "cashflow",
    "clawback": "clawback",
}


@lru_cache(maxsize=1)
def load_packages() -> dict[str, Any]:
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


def list_competitors() -> list[dict[str, Any]]:
    data = load_packages()
    return [c for c in data["companies"].values() if not c.get("is_home")]


def get_company(company_id: str) -> dict[str, Any]:
    data = load_packages()
    return data["companies"][company_id]


def get_home() -> dict[str, Any]:
    return get_company("fwd")


def gate_rows(gate_id: str, competitor_ids: list[str]) -> list[dict[str, Any]]:
    """Build side-by-side rows for one gate: FWD + selected competitors."""
    data = load_packages()
    key = GATE_KEYS[gate_id]
    home = get_home()
    rows = [
        {
            "company_id": "fwd",
            "label": f"{home['name']} · {home['package']}",
            "is_home": True,
            "block": home[key],
        }
    ]
    for cid in competitor_ids:
        c = data["companies"][cid]
        rows.append(
            {
                "company_id": cid,
                "label": f"{c['name']} · {c['package']}",
                "is_home": False,
                "block": c[key],
            }
        )
    return rows


def snapshot_table(competitor_ids: list[str]) -> list[dict[str, str]]:
    """High-level snapshot for the header comparison table."""
    ids = ["fwd"] + list(competitor_ids)
    out = []
    for cid in ids:
        c = get_company(cid)
        out.append(
            {
                "公司": c["name"],
                "計劃": c["package"],
                "合約期": c["contract_label"],
                "津貼": c["allowance_range"],
                "對數": c["survival"]["ratio"],
                "一句話": c["tagline"],
            }
        )
    return out


def _esc(s: str) -> str:
    return (
        str(s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def snapshot_html(competitor_ids: list[str]) -> str:
    """Premium HTML snapshot — FWD row highlighted, metrics as clear chips."""
    ids = ["fwd"] + list(competitor_ids)
    cards = []
    for cid in ids:
        c = get_company(cid)
        home = bool(c.get("is_home"))
        if home:
            wrap = (
                "border:1.5px solid #E2C56A;background:linear-gradient(165deg,#FFFDF5 0%,#FFFFFF 70%);"
                "box-shadow:0 10px 28px rgba(197,160,40,0.14);"
            )
            badge = (
                "<span style='display:inline-block;background:linear-gradient(135deg,#D4AF37,#B38F21);"
                "color:#fff;font-size:0.72rem;font-weight:700;letter-spacing:0.06em;"
                "padding:3px 9px;border-radius:999px;margin-bottom:8px;'>推薦 · FWD</span>"
            )
            name_color = "#1C2430"
            tag_color = "#9A7B1A"
        else:
            wrap = "border:1px solid #E6E8EC;background:#FFFFFF;"
            badge = (
                "<span style='display:inline-block;background:#F3F1EB;color:#6B7280;"
                "font-size:0.72rem;font-weight:600;padding:3px 9px;border-radius:999px;"
                "margin-bottom:8px;'>對比</span>"
            )
            name_color = "#374151"
            tag_color = "#6B7280"

        metrics = [
            ("合約期", c["contract_label"]),
            ("津貼", c["allowance_range"]),
            ("對數", c["survival"]["ratio"]),
        ]
        metric_html = "".join(
            f"<div style='flex:1;min-width:140px;padding:10px 12px;border-radius:10px;"
            f"background:{'#FFF8E1' if home else '#F7F7F5'};border:1px solid "
            f"{'#F0E0A8' if home else '#ECEAE4'};'>"
            f"<div style='font-size:0.72rem;letter-spacing:0.06em;text-transform:uppercase;"
            f"color:#8A8478;margin-bottom:4px;'>{_esc(label)}</div>"
            f"<div style='font-size:0.95rem;font-weight:600;color:#1C2430;line-height:1.35;'>"
            f"{_esc(val)}</div></div>"
            for label, val in metrics
        )
        cards.append(
            f"<div style='{wrap}border-radius:16px;padding:16px 16px 14px;margin-bottom:12px;'>"
            f"{badge}"
            f"<div style='font-size:1.15rem;font-weight:700;color:{name_color};'>"
            f"{_esc(c['name'])}</div>"
            f"<div style='color:{tag_color};font-size:0.92rem;margin:2px 0 12px;'>"
            f"{_esc(c['package'])} · {_esc(c['tagline'])}</div>"
            f"<div style='display:flex;flex-wrap:wrap;gap:8px;'>{metric_html}</div>"
            f"</div>"
        )
    return (
        "<div class='rpc-snapshot' style='margin:4px 0 8px;'>"
        + "".join(cards)
        + "</div>"
    )


def whatsapp_summary(
    competitor_ids: list[str],
    *,
    prospect: str = "",
    agent: str = "",
) -> str:
    home = get_home()
    data = load_packages()
    name = f"— {prospect.strip()}" if str(prospect or "").strip() else ""
    comps = [get_company(cid) for cid in competitor_ids]
    vs = "／".join(c["name"] for c in comps) if comps else "同行"
    lines = [
        f"📌 *新人 Package 對比* {name}".rstrip(),
        f"富衛 *{home['package']}* vs {vs}",
        "",
        "*點解多數新人會揀 FWD？*",
    ]
    for p in data.get("verdict_points") or []:
        lines.append(f"· {p}")
    lines += [
        "",
        f"*FWD 重點*",
        f"· 合約期：{home['contract_label']}",
        f"· 津貼：{home['allowance_range']}",
        f"· 對數：{home['survival']['ratio']}",
        f"· 追補：{home['survival']['catchup']}",
        f"· 離職風險：{home['clawback']['normal_exit']}",
        "",
    ]
    for c in comps:
        lines.append(f"*{c['name']}（{c['package']}）*")
        lines.append(f"· {c['survival']['ratio']}")
        lines.append(f"· {c['clawback']['summary']}")
        lines.append("")
    if str(agent or "").strip():
        lines.append(f"_聯絡：{agent.strip()}_")
    lines.append("_僅供招募面談參考，實際以各公司最新計劃條款為準。_")
    return "\n".join(lines)
