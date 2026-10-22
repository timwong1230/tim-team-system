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


# Categories with alcohol (never suggest Coke / soft drinks for these)
ALCOHOL_CATS = {
    "celestial",
    "beer",
    "tower",
    "wine",
    "red-wine",
    "white-wine",
    "vodka",
    "gin",
    "whisky",
    "liqueur",
    "champagne",
    "tequila",
    "rum",
    "cognac",
}
WINE_CATS = {"wine", "red-wine", "white-wine"}
ZERO_PROOF_CATS = {"non-alcohol", "teas"}
NON_DRINK_CATS = {"shisha", "snacks"}


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
    by_id = {}
    for cat in catalog:
        for item in cat["items"]:
            row = {**item, "category_id": cat["id"], "category": cat["name"]}
            flat.append(row)
            by_id[item["id"]] = row

    def pick(pred, n=3):
        hits = [x for x in flat if pred(x)]
        return hits[:n]

    def is_alcohol(x: dict) -> bool:
        return x["category_id"] in ALCOHOL_CATS

    def hot_in_cats(cats: set[str], n=3) -> list[dict]:
        out = []
        for h in hot:
            item = by_id.get(h["item_id"])
            if item and item["category_id"] in cats:
                out.append(item)
            if len(out) >= n:
                break
        return out

    wants_zero = any(
        k in text
        for k in (
            "no alcohol",
            "non-alcohol",
            "non alcohol",
            "mocktail",
            "唔飲酒",
            "無酒精",
            "冇酒",
        )
    )
    # "alcoholic" / "alcohol" / "drinks" — but not when asking for zero-proof
    wants_alcohol = (not wants_zero) and any(
        k in text
        for k in (
            "alcoholic",
            "alcohol",
            "cocktail",
            "cocktails",
            "飲酒",
            "有酒精",
            "酒類",
            "酒精",
            "with alcohol",
            "booze",
            "spirits",
            "beer",
            "wine",
            "whisky",
            "whiskey",
            "gin",
            "vodka",
            "champagne",
            "tequila",
            "rum",
        )
    )

    mood_picks: list[dict] = []
    vibe = "something tasty"
    hot_for_line: list[dict] = []

    if any(k in text for k in ("shisha", "hookah", "smoke", "雲")):
        vibe = "a proper Polar session"
        mood_picks = pick(lambda x: x["category_id"] == "shisha", 2) + pick(
            lambda x: x["category_id"] == "snacks", 2
        )
    elif wants_zero:
        vibe = "zero-proof vibes"
        mood_picks = pick(lambda x: x["category_id"] in ZERO_PROOF_CATS, 4)
        hot_for_line = hot_in_cats(ZERO_PROOF_CATS)
    elif wants_alcohol and any(
        k in text for k in ("sweet", "fruity", "lychee", "芒果", "甜", "果")
    ):
        vibe = "a sweet alcoholic sip"
        mood_picks = pick(
            lambda x: is_alcohol(x)
            and any(
                w in (x["note"] + x["name"]).lower()
                for w in ("lychee", "strawberry", "passion", "mango", "pineapple", "berry")
            ),
            4,
        ) or pick(lambda x: x["category_id"] == "celestial", 3)
        hot_for_line = hot_in_cats(ALCOHOL_CATS)
    elif wants_alcohol and any(
        k in text for k in ("bitter", "strong", "smoky", "濃", "烈")
    ):
        vibe = "something bold with alcohol"
        mood_picks = pick(
            lambda x: x["category_id"] in ("whisky", "cognac", "rum", "tequila")
            or (is_alcohol(x) and "smoky" in (x["note"] + x["name"]).lower()),
            4,
        ) or pick(is_alcohol, 3)
        hot_for_line = hot_in_cats(ALCOHOL_CATS)
    elif wants_alcohol:
        vibe = "alcoholic drinks"
        # Prefer signatures + a spirit/beer/wine, never soft drinks
        mood_picks = pick(lambda x: x["category_id"] == "celestial", 2)
        mood_picks += hot_in_cats(ALCOHOL_CATS, 2)
        mood_picks += pick(
            lambda x: x["category_id"]
            in (*WINE_CATS, "beer", "champagne", "gin", "vodka"),
            2,
        )
        hot_for_line = hot_in_cats(ALCOHOL_CATS)
    elif any(k in text for k in ("sweet", "fruity", "lychee", "芒果", "甜", "果")):
        vibe = "something sweet & fruity"
        mood_picks = pick(
            lambda x: is_alcohol(x)
            and any(
                w in (x["note"] + x["name"]).lower()
                for w in ("lychee", "strawberry", "passion", "mango", "pineapple", "berry")
            ),
            3,
        )
        hot_for_line = hot_in_cats(ALCOHOL_CATS)
    elif any(k in text for k in ("celebrate", "party", "開心", "慶祝", "birthday")):
        vibe = "a celebratory night"
        mood_picks = pick(lambda x: x["category_id"] in ("celestial", "champagne", "tower"), 3)
        hot_for_line = hot_in_cats(ALCOHOL_CATS)
    elif any(k in text for k in ("chill", "relax", "tired", "calm", "放鬆", "累")):
        vibe = "a chill unwind"
        mood_picks = pick(
            lambda x: x["category_id"] in ("celestial", *WINE_CATS)
            or "sooth" in (x["note"] + x["name"]).lower()
            or "rose" in (x["note"] + x["name"]).lower(),
            3,
        )
        hot_for_line = hot_in_cats(ALCOHOL_CATS | ZERO_PROOF_CATS)
    elif any(k in text for k in ("date", "romantic", "impress", "約會", "浪漫")):
        vibe = "a little romance"
        mood_picks = pick(
            lambda x: x["category_id"] in ("celestial", "champagne", *WINE_CATS),
            3,
        )
        hot_for_line = hot_in_cats(ALCOHOL_CATS)
    elif any(k in text for k in ("bitter", "strong", "smoky", "濃", "烈")):
        vibe = "something bold"
        mood_picks = pick(
            lambda x: x["category_id"] in ("whisky", "celestial")
            or "smoky" in (x["note"] + x["name"]).lower(),
            3,
        )
        hot_for_line = hot_in_cats(ALCOHOL_CATS)
    elif any(k in text for k in ("hungry", "snack", "food", "eat", "肚餓", "小食")):
        vibe = "snacks first"
        mood_picks = pick(lambda x: x["category_id"] == "snacks", 4)
        hot_for_line = hot_in_cats({"snacks"})
    elif any(k in text for k in ("hot", "best", "popular", "sell", "熱銷", "人氣", "recommend")):
        vibe = "what people keep ordering"
        hot_ids = {h["item_id"] for h in hot}
        mood_picks = [x for x in flat if x["id"] in hot_ids][:4]
        hot_for_line = [by_id[h["item_id"]] for h in hot if h["item_id"] in by_id][:3]
    else:
        # default: signatures, not random soft-drink smoke-test bestsellers
        vibe = "a Polar night"
        mood_picks = pick(lambda x: x["category_id"] == "celestial", 2)
        mood_picks += hot_in_cats(ALCOHOL_CATS, 2)
        hot_for_line = hot_in_cats(ALCOHOL_CATS)

    # If user asked for alcohol, hard-filter soft drinks / snacks / shisha out
    if wants_alcohol and not wants_zero:
        mood_picks = [x for x in mood_picks if is_alcohol(x)]
        if not mood_picks:
            mood_picks = pick(is_alcohol, 4)

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

    if not suggestions:
        fallback = pick(is_alcohol if wants_alcohol else lambda _: True, 3)
        for x in fallback:
            suggestions.append(
                {
                    "item_id": x["id"],
                    "name": x["name"],
                    "price": x["price"],
                    "why": x["note"] or x["category"],
                }
            )

    hot_line = ""
    if hot_for_line:
        names = ", ".join(h["name"] for h in hot_for_line[:3])
        hot_line = f" Popular with alcohol tonight: {names}." if wants_alcohol else f" Tonight’s crowd favourites: {names}."

    promo_line = f" Promo window now: {promo.get('label', 'regular')}."
    reply = (
        f"Hey {name} — I’m your Polar host. For {vibe}, I’d go with these from our menu."
        f"{hot_line}{promo_line} Tap Add if one calls to you, or tell me your mood "
        f"(alcoholic / chill / celebrate / sweet / strong / shisha / no alcohol)."
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
        "CRITICAL: If the guest asks for alcoholic / alcohol / cocktails / 飲酒, "
        "ONLY suggest items from alcohol categories (Celestial, beer, wine, spirits, "
        "champagne, etc). NEVER suggest Coke, soft drinks, teas, snacks, or non-alcohol. "
        "If they ask for no alcohol, only suggest non-alcohol / teas. "
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
