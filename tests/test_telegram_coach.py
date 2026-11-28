"""Telegram Coach Tim — product knowledge + bot bridge."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def test_telegram_knowledge_export_includes_allsupporter():
    from tt_core.product_knowledge import (
        export_telegram_knowledge,
        telegram_knowledge_path,
        write_telegram_knowledge_file,
    )

    text = export_telegram_knowledge()
    assert "Telegram Coach Tim" in text
    assert "危疾全應援" in text
    assert "所需全" in text
    assert "更周全" in text
    assert "摯齊全" in text
    path = write_telegram_knowledge_file()
    assert path == telegram_knowledge_path()
    assert path.is_file()
    assert "危疾全應援" in path.read_text(encoding="utf-8")


def test_telegram_start_mentions_product():
    from tt_core.telegram_coach import telegram_start_message

    msg = telegram_start_message()
    assert "Coach Tim" in msg or "AI Tim" in msg
    assert "危疾全應援" in msg or "MDRT" in msg
    assert "基本功" in msg or "約唔到" in msg


def test_answer_telegram_mdrt_skills_offline():
    from tt_core.telegram_coach import answer_telegram

    with patch("tt_core.coach_tim._secret_gemini_key", return_value=""):
        with patch("tt_core.coach_tim._secret_openai_key", return_value=""):
            ans, mode, _meta = answer_telegram(
                "約唔到人有咩 Script？",
                telegram_user_id=999002,
                display_name="Ann",
            )
    assert mode == "offline"
    assert "約唔到" in ans or "小手信" in ans or "見面" in ans


def test_answer_telegram_product_offline():
    from tt_core.telegram_coach import answer_telegram

    with patch("tt_core.coach_tim._secret_gemini_key", return_value=""):
        with patch("tt_core.coach_tim._secret_openai_key", return_value=""):
            ans, mode, meta = answer_telegram(
                "危疾全應援點賣俾夾心家庭？",
                telegram_user_id=999001,
                display_name="Sam",
            )
    assert mode == "offline"
    assert "危疾全應援" in ans
    assert "所需全" in ans or "更周全" in ans or "摯齊全" in ans


def test_handle_start_and_products(monkeypatch):
    from tt_core import telegram_coach as tg

    sent: list[dict] = []

    def fake_send(chat_id, text, *, reply_to=None):
        sent.append({"chat_id": chat_id, "text": text, "reply_to": reply_to})
        return {"ok": True}

    monkeypatch.setattr(tg, "send_message", fake_send)

    out = tg.handle_update(
        {
            "update_id": 1,
            "message": {
                "message_id": 10,
                "chat": {"id": 42},
                "from": {"id": 7, "first_name": "Tim"},
                "text": "/start",
            },
        }
    )
    assert out.get("ok") is True
    assert out.get("kind") == "start"
    assert sent and "危疾全應援" in sent[0]["text"]

    sent.clear()
    out2 = tg.handle_update(
        {
            "update_id": 2,
            "message": {
                "message_id": 11,
                "chat": {"id": 42},
                "from": {"id": 7, "first_name": "Tim"},
                "text": "/products",
            },
        }
    )
    assert out2.get("ok") is True
    assert out2.get("kind") == "products"
    assert sent and "危疾全應援" in sent[0]["text"]


def test_handle_link_and_chat_product(monkeypatch):
    from tt_core import telegram_coach as tg

    sent: list[str] = []
    monkeypatch.setattr(
        tg,
        "send_message",
        lambda chat_id, text, *, reply_to=None: sent.append(text) or {"ok": True},
    )
    monkeypatch.setattr(tg, "link_telegram_user", lambda uid, name: True)
    monkeypatch.setattr(
        tg,
        "answer_telegram",
        lambda text, *, telegram_user_id, display_name="", history=None: (
            f"回覆：{text}",
            "offline",
            {},
        ),
    )

    out = tg.handle_update(
        {
            "message": {
                "message_id": 1,
                "chat": {"id": 1},
                "from": {"id": 55, "first_name": "A"},
                "text": "/link Tim",
            }
        }
    )
    assert out.get("kind") == "link"
    assert sent and "Tim" in sent[-1]

    sent.clear()
    out2 = tg.handle_update(
        {
            "message": {
                "message_id": 2,
                "chat": {"id": 1},
                "from": {"id": 55, "first_name": "A"},
                "text": "危疾全應援三個級別",
            }
        }
    )
    assert out2.get("kind") == "chat"
    assert sent and "危疾全應援" in sent[-1]


def test_system_prompt_telegram_channel():
    from tt_core.coach_tim import system_prompt

    ctx = {
        "username": "Tim",
        "role": "Member",
        "channel": "telegram",
        "ytd_fyc": 0,
        "extra10_open": False,
        "extra10_remaining": 88000,
        "mdrt_progress": 0,
        "mdrt_pct": 0,
        "mdrt_remaining": 512800,
        "mdrt_target": 512800,
        "wk_count": 0,
        "wk_min": 3,
        "wk_need": 3,
        "recruit": 0,
        "due": [],
        "upcoming": [],
        "prospects": [],
        "product_brief": "## 產品知識：危疾全應援保險計劃系列",
    }
    sp = system_prompt(ctx)
    assert "Telegram" in sp
    assert "危疾全應援" in sp


def test_app_has_telegram_coach_ui():
    src = (_ROOT / "app.py").read_text(encoding="utf-8")
    assert "telegram_coach" in src
    assert "telegram_coach_knowledge" in src or "下載知識庫" in src
    assert "BotFather" in src


def test_knowledge_status_shape():
    from tt_core.telegram_coach import knowledge_status

    st = knowledge_status()
    assert st["pack_count"] >= 1
    assert any("危疾全應援" in n for n in st["pack_names"])
    assert st["knowledge_chars"] > 500


def test_poll_once_without_token():
    from tt_core import telegram_coach as tg

    with patch.object(tg, "get_bot_token", return_value=""):
        res = tg.poll_once()
    assert res.get("ok") is False
    assert res.get("handled") == 0
