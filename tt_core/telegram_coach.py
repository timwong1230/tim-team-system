"""Telegram Coach Tim — Bot API bridge sharing AI Tim product knowledge.

Colleagues already use Telegram Coach Tim; this module lets the same
product packs (危疾全應援 etc.) answer on Telegram when a BotFather token
is configured. Knowledge can also be exported for Custom GPT upload.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

SETTING_BOT_TOKEN = "coach_tim_telegram_bot_token"
SETTING_UPDATE_OFFSET = "coach_tim_telegram_update_offset"
SETTING_USER_MAP = "coach_tim_telegram_user_map"  # JSON: {telegram_user_id: m2_username}
_API = "https://api.telegram.org"


def _settings_get(key: str, default: str = "") -> str:
    from tt_core.coach_tim import _settings_get as _get

    return _get(key, default)


def _settings_set(key: str, value: str) -> bool:
    from tt_core.coach_tim import _settings_set as _set

    return _set(key, value)


def get_bot_token() -> str:
    try:
        import streamlit as st

        if "coach_tim" in st.secrets:
            block = st.secrets["coach_tim"]
            for k in ("telegram_bot_token", "bot_token", "telegram_token"):
                v = block.get(k) if hasattr(block, "get") else None
                if v:
                    return str(v).strip()
        if "telegram" in st.secrets:
            block = st.secrets["telegram"]
            for k in ("bot_token", "token", "api_token"):
                v = block.get(k) if hasattr(block, "get") else None
                if v:
                    return str(v).strip()
    except Exception:
        pass
    return _settings_get(SETTING_BOT_TOKEN, "")


def save_bot_token(token: str) -> bool:
    return _settings_set(SETTING_BOT_TOKEN, str(token or "").strip())


def clear_bot_token() -> bool:
    return _settings_set(SETTING_BOT_TOKEN, "")


def mask_token(token: str) -> str:
    t = str(token or "").strip()
    if len(t) < 12:
        return "••••" if t else ""
    return f"{t[:6]}…{t[-4:]}"


def bot_configured() -> bool:
    return bool(get_bot_token())


def load_user_map() -> dict[str, str]:
    raw = _settings_get(SETTING_USER_MAP, "")
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items() if str(v).strip()}
    except Exception:
        pass
    return {}


def save_user_map(mapping: dict[str, str]) -> bool:
    clean = {str(k).strip(): str(v).strip() for k, v in (mapping or {}).items() if str(v).strip()}
    return _settings_set(SETTING_USER_MAP, json.dumps(clean, ensure_ascii=False))


def link_telegram_user(telegram_user_id: int | str, m2_username: str) -> bool:
    mapping = load_user_map()
    mapping[str(telegram_user_id)] = str(m2_username or "").strip()
    return save_user_map(mapping)


def resolve_m2_username(telegram_user_id: int | str, *, fallback: str = "") -> str:
    mapping = load_user_map()
    hit = mapping.get(str(telegram_user_id), "").strip()
    return hit or str(fallback or "").strip()


def _api(method: str, payload: dict[str, Any] | None = None, *, token: str | None = None) -> dict[str, Any]:
    tok = (token or get_bot_token()).strip()
    if not tok:
        return {"ok": False, "description": "missing bot token"}
    url = f"{_API}/bot{tok}/{method}"
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method="POST" if data else "GET")
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:400]
        try:
            return json.loads(body)
        except Exception:
            return {"ok": False, "description": body or str(e)}
    except Exception as e:
        return {"ok": False, "description": str(e)[:300]}


def get_me() -> dict[str, Any]:
    return _api("getMe")


def send_message(chat_id: int | str, text: str, *, reply_to: int | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "text": (text or "")[:4000],
        "disable_web_page_preview": True,
    }
    if reply_to is not None:
        payload["reply_to_message_id"] = reply_to
    return _api("sendMessage", payload)


def send_document(chat_id: int | str, file_bytes: bytes, filename: str, *, caption: str = "") -> dict[str, Any]:
    """Upload a small knowledge file to the chat (multipart)."""
    tok = get_bot_token().strip()
    if not tok:
        return {"ok": False, "description": "missing bot token"}
    boundary = "----TIMTeamBoundary7MA4YWxk"
    parts: list[bytes] = []

    def field(name: str, value: str) -> None:
        parts.append(
            (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
                f"{value}\r\n"
            ).encode("utf-8")
        )

    field("chat_id", str(chat_id))
    if caption:
        field("caption", caption[:900])
    parts.append(
        (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="document"; filename="{filename}"\r\n'
            f"Content-Type: application/octet-stream\r\n\r\n"
        ).encode("utf-8")
    )
    parts.append(file_bytes)
    parts.append(f"\r\n--{boundary}--\r\n".encode("utf-8"))
    body = b"".join(parts)
    url = f"{_API}/bot{tok}/sendDocument"
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"ok": False, "description": str(e)[:300]}


def _minimal_ctx(*, username: str = "同事", role: str = "Member") -> dict[str, Any]:
    return {
        "username": username or "同事",
        "role": role,
        "channel": "telegram",
        "ytd_fyc": 0,
        "extra10_open": False,
        "extra10_threshold": 88000,
        "extra10_remaining": 88000,
        "mdrt_progress": 0,
        "mdrt_pct": 0,
        "mdrt_remaining": 0,
        "mdrt_target": 512800,
        "wk_count": 0,
        "wk_score": 0,
        "wk_min": 3,
        "wk_need": 3,
        "recruit": 0,
        "due": [],
        "upcoming": [],
        "prospects": [],
        "tool_hits": {},
    }


def build_telegram_context(telegram_user_id: int | str, *, display_name: str = "") -> dict[str, Any]:
    from tt_core.coach_tim import build_coach_context

    m2 = resolve_m2_username(telegram_user_id, fallback="")
    if m2:
        try:
            ctx = build_coach_context(m2, role="Member")
            ctx["channel"] = "telegram"
            return ctx
        except Exception:
            pass
    name = m2 or display_name or "同事"
    return _minimal_ctx(username=name)


def answer_telegram(
    user_text: str,
    *,
    telegram_user_id: int | str,
    display_name: str = "",
    history: list[dict[str, str]] | None = None,
) -> tuple[str, str, dict[str, Any]]:
    """Reply using the same coach + product knowledge as in-app AI Tim."""
    from tt_core.coach_tim import reply
    from tt_core.product_knowledge import offline_product_reply, product_query_intent

    text = (user_text or "").strip()
    ctx = build_telegram_context(telegram_user_id, display_name=display_name)

    # Fast path: product questions work even without M+2 link / LLM
    if product_query_intent(text):
        try:
            from tt_core.product_knowledge import format_matched_briefs

            brief = format_matched_briefs(text)
            if brief:
                ctx["product_brief"] = brief
        except Exception:
            pass

    result = reply(text, list(history or []), ctx)
    if isinstance(result, tuple) and len(result) >= 2:
        answer, mode = result[0], result[1]
        meta = result[2] if len(result) > 2 and isinstance(result[2], dict) else {}
    else:
        answer, mode, meta = str(result), "offline", {}

    if (not answer or not str(answer).strip()) and product_query_intent(text):
        offline = offline_product_reply(text, username=str(ctx.get("username") or "你"))
        if offline:
            return offline, "offline", meta
    return str(answer), str(mode), meta


def telegram_start_message() -> str:
    from tt_core.product_knowledge import product_pack_labels

    packs = product_pack_labels()
    pack_line = "、".join(packs) if packs else "產品知識"
    return (
        "你好，我係 **Coach Tim／AI Tim**（Telegram）。\n\n"
        f"而家已載入產品知識：**{pack_line}**。\n"
        "可以問例如「危疾全應援點賣」「所需全同更周全分別」「家添守護點講」。\n\n"
        "若要跟住你嘅業績／準客戶傾下一步，叫 Leader 喺 M+2 將你嘅 Telegram "
        "綁定 M+2 帳號。"
    )


def handle_update(update: dict[str, Any]) -> dict[str, Any]:
    """Process one Telegram update; send reply if it's a text message."""
    msg = update.get("message") or update.get("edited_message") or {}
    if not msg:
        return {"ok": True, "skipped": "no message"}
    chat = msg.get("chat") or {}
    chat_id = chat.get("id")
    text = str(msg.get("text") or "").strip()
    from_user = msg.get("from") or {}
    uid = from_user.get("id")
    display = (
        str(from_user.get("first_name") or "").strip()
        or str(from_user.get("username") or "").strip()
        or "同事"
    )
    if chat_id is None:
        return {"ok": False, "error": "no chat_id"}

    if text in ("/start", "/help", "開始", "你好"):
        out = send_message(chat_id, telegram_start_message(), reply_to=msg.get("message_id"))
        return {"ok": bool(out.get("ok")), "kind": "start", "api": out}

    if text.startswith("/link "):
        # /link <M+2 username> — self-serve bind
        m2 = text.split(None, 1)[1].strip()
        if uid is not None and m2:
            link_telegram_user(uid, m2)
            out = send_message(
                chat_id,
                f"已綁定 M+2 帳號 **{m2}**。之後問業績／跟進會讀你嘅數據。",
                reply_to=msg.get("message_id"),
            )
            return {"ok": bool(out.get("ok")), "kind": "link", "api": out}

    if text in ("/products", "/產品", "產品知識"):
        from tt_core.product_knowledge import export_telegram_knowledge, product_pack_labels

        labels = "、".join(product_pack_labels()) or "（未有）"
        body = (
            f"已載入：**{labels}**\n\n"
            "問「危疾全應援點賣」或「所需全 vs 更周全」就得。\n\n"
            "——\n"
            + export_telegram_knowledge(max_chars=3200)
        )
        out = send_message(chat_id, body, reply_to=msg.get("message_id"))
        return {"ok": bool(out.get("ok")), "kind": "products", "api": out}

    if not text:
        return {"ok": True, "skipped": "non-text"}

    answer, mode, meta = answer_telegram(
        text,
        telegram_user_id=uid or chat_id,
        display_name=display,
    )
    footer = ""
    if mode == "offline" and meta.get("tools_used"):
        footer = ""
    out = send_message(chat_id, answer + footer, reply_to=msg.get("message_id"))
    return {
        "ok": bool(out.get("ok")),
        "kind": "chat",
        "mode": mode,
        "api": out,
        "meta": {"tools_used": meta.get("tools_used") or []},
    }


def get_update_offset() -> int:
    raw = _settings_get(SETTING_UPDATE_OFFSET, "0")
    try:
        return int(raw or 0)
    except Exception:
        return 0


def set_update_offset(offset: int) -> bool:
    return _settings_set(SETTING_UPDATE_OFFSET, str(int(offset)))


def poll_once(*, limit: int = 20, timeout: int = 0) -> dict[str, Any]:
    """Long/short poll getUpdates, handle each, advance offset."""
    offset = get_update_offset()
    params = {"offset": offset, "limit": max(1, min(int(limit), 100)), "timeout": max(0, int(timeout))}
    # GET with query string
    tok = get_bot_token().strip()
    if not tok:
        return {"ok": False, "error": "missing bot token", "handled": 0}
    qs = urllib.parse.urlencode(params)
    url = f"{_API}/bot{tok}/getUpdates?{qs}"
    try:
        with urllib.request.urlopen(url, timeout=max(30, timeout + 10)) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"ok": False, "error": str(e)[:300], "handled": 0}

    if not data.get("ok"):
        return {"ok": False, "error": data.get("description") or "getUpdates failed", "handled": 0}

    results = list(data.get("result") or [])
    handled = []
    max_id = offset
    for upd in results:
        uid = int(upd.get("update_id") or 0)
        if uid >= max_id:
            max_id = uid + 1
        try:
            handled.append(handle_update(upd))
        except Exception as e:
            handled.append({"ok": False, "error": str(e)[:200]})
    if max_id > offset:
        set_update_offset(max_id)
    return {
        "ok": True,
        "handled": len(handled),
        "offset": max_id,
        "results": handled,
    }


def knowledge_status() -> dict[str, Any]:
    from tt_core.product_knowledge import (
        export_telegram_knowledge,
        list_product_packs,
        telegram_knowledge_path,
        write_telegram_knowledge_file,
    )

    packs = list_product_packs()
    path = telegram_knowledge_path()
    if not path.is_file():
        try:
            write_telegram_knowledge_file()
        except Exception:
            pass
    return {
        "pack_count": len(packs),
        "pack_names": [str(p.get("name_zh") or p.get("id")) for p in packs],
        "knowledge_file": str(path) if path.is_file() else "",
        "knowledge_chars": len(export_telegram_knowledge()),
        "bot_configured": bot_configured(),
    }


def push_knowledge_to_chat(chat_id: int | str) -> dict[str, Any]:
    """Send the knowledge markdown (+ note) into a Telegram chat for Tim to pin/forward."""
    from tt_core.product_knowledge import export_telegram_knowledge, write_telegram_knowledge_file

    path = write_telegram_knowledge_file()
    raw = path.read_bytes()
    caption = (
        "Telegram Coach Tim 產品知識庫（含危疾全應援）。"
        "可轉發／上載去 Custom GPT knowledge，或問 bot「危疾全應援點賣」。"
    )
    return send_document(chat_id, raw, path.name, caption=caption)
