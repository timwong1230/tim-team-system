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

# Mood → ordered category groups (first groups preferred).
COCKTAIL_CATS = ("celestial",)
SPIRIT_CATS = ("vodka", "gin", "whisky", "liqueur", "tequila", "rum", "cognac")
MOOD_PLAYBOOK: dict[str, tuple[str, tuple[tuple[str, ...], ...]]] = {
    # key → (vibe label, ordered category groups)
    "happy": ("a happy night", (("shisha",), COCKTAIL_CATS, SPIRIT_CATS)),
    "sad": ("a heavier mood", (("shisha",), SPIRIT_CATS, COCKTAIL_CATS)),
    "calm": ("a calm unwind", (("shisha",), COCKTAIL_CATS, ("beer",))),
    "celebration": ("a celebration", (("shisha",), ("champagne",), ("tower",))),
    "non_alcoholic": (
        "zero-proof vibes",
        (("shisha",), ("teas",), ("non-alcohol",)),
    ),
}

ALCOHOL_CATS = {
    "celestial",
    "beer",
    "tower",
    "wine",
    "red-wine",
    "white-wine",
    *SPIRIT_CATS,
    "champagne",
}
ZERO_PROOF_CATS = {"non-alcohol", "teas"}


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


def _detect_mood(text: str) -> str | None:
    """Return playbook mood key from free text / chip labels."""
    t = (text or "").strip().lower()
    if not t:
        return None
    # Explicit chip / keyword mapping (order matters for overlaps).
    if any(
        k in t
        for k in (
            "non alcoholic",
            "non-alcoholic",
            "non alcohol",
            "no alcohol",
            "zero-proof",
            "zero proof",
            "mocktail",
            "唔飲酒",
            "無酒精",
            "冇酒",
            "soft drink",
        )
    ):
        return "non_alcoholic"
    if any(
        k in t
        for k in (
            "celebration",
            "celebrate",
            "party",
            "birthday",
            "慶祝",
            "派對",
            "cheers",
        )
    ):
        return "celebration"
    if any(k in t for k in ("sad", "down", "blue", "傷心", "唔開心", "emo", "breakup")):
        return "sad"
    if any(k in t for k in ("calm", "chill", "relax", "放鬆", "累", "tired", "zen")):
        return "calm"
    if any(k in t for k in ("happy", "開心", "歡樂", "fun", "good mood", "excited")):
        return "happy"
    return None


# Not vibe picks — skip in mood recommendations
SKIP_AI_IDS = {"shisha-change", "not-on-menu"}


def _rank_in_group(item: dict[str, Any]) -> tuple:
    """Prefer Regular Shisha, Glass serves, then name."""
    iid = item.get("id") or ""
    unit = item.get("unit") or ""
    shisha_rank = 0 if iid == "shisha-regular" else 1
    unit_rank = 0 if unit == "Glass" else (1 if unit == "Bottle" else 0)
    return (shisha_rank, unit_rank, (item.get("name") or "").lower())


def _best_in_group(
    flat: list[dict[str, Any]],
    hot: list[dict[str, Any]],
    group: tuple[str, ...],
    seen: set[str],
) -> dict[str, Any] | None:
    by_id = {x["id"]: x for x in flat}

    def ok(item: dict[str, Any] | None) -> bool:
        return bool(
            item
            and item["id"] not in seen
            and item["id"] not in SKIP_AI_IDS
            and item["category_id"] in group
        )

    hot_hits = [by_id[h["item_id"]] for h in hot if ok(by_id.get(h["item_id"]))]
    if hot_hits:
        hot_hits.sort(key=_rank_in_group)
        return hot_hits[0]
    pool = [x for x in flat if ok(x)]
    if not pool:
        return None
    pool.sort(key=_rank_in_group)
    return pool[0]


def _picks_for_groups(
    flat: list[dict[str, Any]],
    hot: list[dict[str, Any]],
    groups: tuple[tuple[str, ...], ...],
    *,
    limit: int = 4,
) -> list[dict[str, Any]]:
    """One from each group in order, then a second pass to fill to `limit`."""
    seen: set[str] = set()
    out: list[dict[str, Any]] = []

    def add(item: dict[str, Any] | None) -> None:
        if not item or item["id"] in seen:
            return
        seen.add(item["id"])
        out.append(item)

    # Pass 1: exactly one pick per group (preserves Happy/Sad/… order)
    for group in groups:
        if len(out) >= limit:
            break
        add(_best_in_group(flat, hot, group, seen))

    # Pass 2: second pick from each group until full
    for group in groups:
        if len(out) >= limit:
            break
        add(_best_in_group(flat, hot, group, seen))

    return out[:limit]


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

    mood = _detect_mood(text)
    mood_picks: list[dict] = []
    vibe = "a Polar night"
    hot_for_line: list[dict] = []

    if mood and mood in MOOD_PLAYBOOK:
        vibe, groups = MOOD_PLAYBOOK[mood]
        mood_picks = _picks_for_groups(flat, hot, groups, limit=4)
        allowed = {c for g in groups for c in g}
        hot_for_line = []
        for h in hot:
            item = by_id.get(h["item_id"])
            if item and item["category_id"] in allowed:
                hot_for_line.append(item)
            if len(hot_for_line) >= 3:
                break
    elif any(k in text for k in ("shisha", "hookah", "smoke", "雲")):
        vibe = "a proper Polar session"
        mood_picks = _picks_for_groups(
            flat, hot, (("shisha",), COCKTAIL_CATS, ("snacks",)), limit=4
        )
    elif any(k in text for k in ("hungry", "snack", "food", "eat", "肚餓", "小食")):
        vibe = "snacks first"
        mood_picks = pick(lambda x: x["category_id"] == "snacks", 4)
    elif any(k in text for k in ("hot", "best", "popular", "sell", "熱銷", "人氣", "recommend")):
        vibe = "what people keep ordering"
        hot_ids = {h["item_id"] for h in hot}
        mood_picks = [x for x in flat if x["id"] in hot_ids][:4]
        hot_for_line = [by_id[h["item_id"]] for h in hot if h["item_id"] in by_id][:3]
    else:
        # Default → Happy playbook (shisha + cocktail + spirits)
        vibe, groups = MOOD_PLAYBOOK["happy"]
        mood_picks = _picks_for_groups(flat, hot, groups, limit=4)

    seen: set[str] = set()
    suggestions = []
    for x in mood_picks:
        if x["id"] in seen:
            continue
        seen.add(x["id"])
        suggestions.append(
            {
                "item_id": x["id"],
                "name": x["name"]
                + (f" ({x['unit']})" if x.get("unit") in ("Glass", "Bottle") else ""),
                "price": x["price"],
                "why": x["note"] or x["category"],
            }
        )
        if len(suggestions) >= 4:
            break

    if not suggestions:
        for x in pick(lambda _: True, 3):
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
        hot_line = f" Tonight’s crowd favourites: {names}."

    promo_line = f" Promo window now: {promo.get('label', 'regular')}."
    reply = (
        f"Hey {name} — I’m your Polar host. For {vibe}, I’d go with these from our menu."
        f"{hot_line}{promo_line} Tap Add if one calls to you, or pick a mood chip "
        f"(Happy / Sad / Calm / Celebration / Non alcoholic)."
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
        "Help guests choose from ONLY the menu below. "
        "Be warm, short (3-6 sentences), bilingual OK (EN + casual Cantonese words). "
        "Never invent items.\n"
        "MOOD PLAYBOOK (follow category order; include ~1 item from each group when possible):\n"
        "- Happy → Shisha, Cocktail (Celestial), Spirits\n"
        "- Sad → Shisha, Spirits, Cocktail (Celestial)\n"
        "- Calm → Shisha, Cocktail (Celestial), Beer\n"
        "- Celebration → Shisha, Champagne, Tower\n"
        "- Non alcoholic → Shisha, Tea (Special Teas), Soft drinks (Non Alcohol)\n"
        "Spirits = Vodka/Gin/Whisky/Liqueur/Tequila/Rum/Cognac. Cocktail = Celestial Signatures.\n"
        "If mood is Happy/Sad/Calm/Celebration, DO include Shisha — do not replace it with soft drinks.\n"
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
    except (
        urllib.error.URLError,
        urllib.error.HTTPError,
        KeyError,
        TimeoutError,
        json.JSONDecodeError,
    ):
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

    # Prefer local playbook suggestions when mood chips are used (deterministic).
    mood = _detect_mood(message)
    if mood:
        local = _local_reply(
            message, catalog=catalog, hot=hot, guest_name=guest_name, promo=promo
        )
        suggestions = local["suggestions"]
        if not reply.strip():
            reply = local["reply"]
    elif not suggestions:
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
    # Mood chips use the deterministic playbook (no OpenAI drift).
    if _detect_mood(message):
        return _local_reply(
            message,
            catalog=catalog,
            hot=hot,
            guest_name=guest_name,
            promo=promo,
        )
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
