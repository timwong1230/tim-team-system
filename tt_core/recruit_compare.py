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
