"""Polar Ask AI — menu-aware host with optional OpenAI + local fallback."""

from __future__ import annotations

import json
import os
import re
import sqlite3
import urllib.error
import urllib.request
from typing import Any

from .pricing import current_promo

OPENAI_KEY = os.getenv("POLAR_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY") or ""
OPENAI_MODEL = os.getenv("POLAR_OPENAI_MODEL", "gpt-4o-mini")


def bestsellers(conn: sqlite3.Connection, limit: int = 8) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT oi.item_id, oi.item_name, oi.category_id,
               SUM(oi.qty) AS qty, SUM(oi.line_total) AS revenue
        FROM order_items oi
        JOIN orders o ON o.id = oi.order_id
        JOIN sessions s ON s.id = o.session_id
        JOIN tables t ON t.id = o.table_id
        WHERE o.status != 'cancelled'
          AND COALESCE(t.zone, '') != 'boss'
        GROUP BY oi.item_id
        ORDER BY qty DESC, revenue DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [
        {
            "item_id": r["item_id"],
            "name": r["item_name"],
            "category_id": r["category_id"],
            "qty": int(r["qty"] or 0),
        }
        for r in rows
    ]


def menu_catalog(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    cats = conn.execute(
        "SELECT id, name FROM menu_categories ORDER BY sort_order ASC"
    ).fetchall()
    out = []
    for cat in cats:
        items = conn.execute(
            """
            SELECT id, name, price, note, unit
            FROM menu_items
            WHERE category_id = ? AND available = 1
            ORDER BY name ASC
            """,
            (cat["id"],),
        ).fetchall()
        out.append(
            {
                "id": cat["id"],
                "name": cat["name"],
                "items": [
                    {
                        "id": i["id"],
                        "name": i["name"],
                        "price": float(i["price"]),
                        "note": i["note"] or "",
                        "unit": i["unit"] or "",
                    }
                    for i in items
                ],
            }
        )
    return out


def _local_reply(
    message: str,
    *,
    catalog: list[dict[str, Any]],
    hot: list[dict[str, Any]],
    guest_name: str | None,
    promo: dict[str, Any],
) -> dict[str, Any]:
    text = (message or "").strip().lower()
    name = (guest_name or "friend").strip() or "friend"
    flat = []
    for cat in catalog:
        for item in cat["items"]:
            flat.append({**item, "category_id": cat["id"], "category": cat["name"]})

    def pick(pred, n=3):
        hits = [x for x in flat if pred(x)]
        return hits[:n]

    mood_picks: list[dict] = []
    vibe = "something tasty"

    if any(k in text for k in ("shisha", "hookah", "smoke", "雲")):
        vibe = "a proper Polar session"
        mood_picks = pick(lambda x: x["category_id"] == "shisha", 2) + pick(
            lambda x: x["category_id"] == "snacks", 2
        )
    elif any(k in text for k in ("sweet", "fruity", "lychee", "芒果", "甜", "果")):
        vibe = "something sweet & fruity"
        mood_picks = pick(
            lambda x: any(
                w in (x["note"] + x["name"]).lower()
                for w in ("lychee", "strawberry", "passion", "mango", "pineapple", "berry")
            ),
            3,
        )
    elif any(k in text for k in ("no alcohol", "mocktail", "soda", "唔飲酒", "無酒精")):
        vibe = "zero-proof vibes"
        mood_picks = pick(lambda x: x["category_id"] in ("non-alcohol", "teas"), 3)
    elif any(k in text for k in ("celebrate", "party", "開心", "慶祝", "birthday")):
        vibe = "a celebratory night"
        mood_picks = pick(lambda x: x["category_id"] in ("celestial", "champagne", "tower"), 3)
    elif any(k in text for k in ("chill", "relax", "tired", "calm", "放鬆", "累")):
        vibe = "a chill unwind"
        mood_picks = pick(
            lambda x: x["category_id"] in ("celestial", "wine", "non-alcohol", "teas")
            or "sooth" in (x["note"] + x["name"]).lower()
            or "rose" in (x["note"] + x["name"]).lower(),
            3,
        )
    elif any(k in text for k in ("date", "romantic", "impress", "約會", "浪漫")):
        vibe = "a little romance"
        mood_picks = pick(
            lambda x: x["category_id"] in ("celestial", "champagne", "wine"),
            3,
        )
    elif any(k in text for k in ("bitter", "strong", "smoky", "whisky", "whiskey", "濃", "烈")):
        vibe = "something bold"
        mood_picks = pick(
            lambda x: x["category_id"] in ("whisky", "celestial")
            or "smoky" in (x["note"] + x["name"]).lower(),
            3,
        )
    elif any(k in text for k in ("hungry", "snack", "food", "eat", "肚餓", "小食")):
        vibe = "snacks first"
        mood_picks = pick(lambda x: x["category_id"] == "snacks", 4)
    elif any(k in text for k in ("hot", "best", "popular", "sell", "熱銷", "人氣", "recommend")):
        vibe = "what people keep ordering"
        hot_ids = {h["item_id"] for h in hot}
        mood_picks = [x for x in flat if x["id"] in hot_ids][:4]
    else:
        # default: mix bestsellers + a signature
        hot_ids = {h["item_id"] for h in hot}
        mood_picks = [x for x in flat if x["id"] in hot_ids][:2]
        mood_picks += pick(lambda x: x["category_id"] == "celestial", 2)

    # dedupe
    seen = set()
    suggestions = []
    for x in mood_picks:
        if x["id"] in seen:
            continue
        seen.add(x["id"])
        suggestions.append(
            {
                "item_id": x["id"],
                "name": x["name"],
                "price": x["price"],
                "why": x["note"] or x["category"],
            }
        )
        if len(suggestions) >= 4:
            break

    if not suggestions and flat:
        for x in flat[:3]:
            suggestions.append(
                {
                    "item_id": x["id"],
                    "name": x["name"],
                    "price": x["price"],
                    "why": x["note"] or x["category"],
                }
            )

    hot_line = ""
    if hot:
        names = ", ".join(h["name"] for h in hot[:3])
        hot_line = f" Tonight’s crowd favourites: {names}."

    promo_line = f" Promo window now: {promo.get('label', 'regular')}."
    reply = (
        f"Hey {name} — I’m your Polar host. For {vibe}, I’d go with these from our menu."
        f"{hot_line}{promo_line} Tap Add if one calls to you, or tell me your mood "
        f"(chill / celebrate / sweet / strong / shisha / no alcohol)."
    )
    return {"reply": reply, "suggestions": suggestions, "source": "polar-host"}


def _openai_reply(
    message: str,
    history: list[dict[str, str]],
    *,
    catalog: list[dict[str, Any]],
    hot: list[dict[str, Any]],
    guest_name: str | None,
    promo: dict[str, Any],
) -> dict[str, Any] | None:
    if not OPENAI_KEY:
        return None
    # Compact menu for token budget
    menu_lines = []
    for cat in catalog:
        for item in cat["items"][:40]:
            menu_lines.append(
                f"- [{item['id']}] {item['name']} ${item['price']:.0f} "
                f"({cat['name']}) {item['note']}"
            )
        if len(menu_lines) > 80:
            break
    hot_txt = ", ".join(f"{h['name']}({h['qty']})" for h in hot) or "none yet"
    system = (
        "You are Polar Lounge's playful in-house host AI in Causeway Bay. "
        "Help guests choose drinks/food from ONLY the menu below. "
        "Be warm, short (3-6 sentences), bilingual OK (EN + casual Cantonese words). "
        "Use bestsellers when relevant. Never invent items. "
        "When recommending, end with a JSON block on its own line like:\n"
        'SUGGESTIONS: [{"item_id":"...","name":"...","price":123,"why":"..."}]\n'
        "Max 4 suggestions. item_id must match menu ids.\n\n"
        f"Guest: {guest_name or 'guest'}\n"
        f"Current promo: {promo.get('label')}\n"
        f"Bestsellers (qty): {hot_txt}\n"
        f"MENU:\n" + "\n".join(menu_lines[:90])
    )
    messages = [{"role": "system", "content": system}]
    for turn in history[-8:]:
        role = turn.get("role")
        content = (turn.get("content") or "").strip()
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content[:800]})
    messages.append({"role": "user", "content": message[:800]})

    body = json.dumps(
        {
            "model": OPENAI_MODEL,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 500,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {OPENAI_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        content = data["choices"][0]["message"]["content"]
    except (urllib.error.URLError, urllib.error.HTTPError, KeyError, TimeoutError, json.JSONDecodeError):
        return None

    suggestions: list[dict] = []
    reply = content
    m = re.search(r"SUGGESTIONS:\s*(\[[\s\S]*?\])", content)
    if m:
        reply = content[: m.start()].strip()
        try:
            raw = json.loads(m.group(1))
            valid_ids = {i["id"] for c in catalog for i in c["items"]}
            prices = {i["id"]: i["price"] for c in catalog for i in c["items"]}
            names = {i["id"]: i["name"] for c in catalog for i in c["items"]}
            for s in raw[:4]:
                iid = s.get("item_id")
                if iid in valid_ids:
                    suggestions.append(
                        {
                            "item_id": iid,
                            "name": names[iid],
                            "price": prices[iid],
                            "why": str(s.get("why") or "")[:80],
                        }
                    )
        except (json.JSONDecodeError, TypeError, AttributeError):
            suggestions = []

    if not suggestions:
        # fall back to local picks based on same message
        local = _local_reply(
            message, catalog=catalog, hot=hot, guest_name=guest_name, promo=promo
        )
        suggestions = local["suggestions"]

    return {"reply": reply, "suggestions": suggestions, "source": "openai"}


def ask_ai(
    conn: sqlite3.Connection,
    *,
    message: str,
    history: list[dict[str, str]] | None = None,
    guest_name: str | None = None,
) -> dict[str, Any]:
    catalog = menu_catalog(conn)
    hot = bestsellers(conn)
    promo = current_promo()
    history = history or []
    ai = _openai_reply(
        message,
        history,
        catalog=catalog,
        hot=hot,
        guest_name=guest_name,
        promo=promo,
    )
    if ai:
        return ai
    return _local_reply(
        message,
        catalog=catalog,
        hot=hot,
        guest_name=guest_name,
        promo=promo,
    )
