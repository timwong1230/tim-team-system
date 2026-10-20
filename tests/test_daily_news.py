"""Homepage daily headlines — 3 pillars, 5 items, WhatsApp openers."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
<title>Test</title>
<item>
  <title>港府公布新措施</title>
  <link>https://example.com/a</link>
  <pubDate>Sun, 18 Oct 2026 01:00:00 GMT</pubDate>
</item>
<item>
  <title>國際峰會閉幕</title>
  <link>https://example.com/b</link>
  <pubDate>Sun, 18 Oct 2026 00:30:00 GMT</pubDate>
</item>
</channel></rss>
"""

_FINANCE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
<title>Finance</title>
<item>
  <title>港股收市升逾二百點 銀行股帶動</title>
  <link>https://example.com/fin1</link>
  <pubDate>Sun, 18 Oct 2026 02:00:00 GMT</pubDate>
</item>
<item>
  <title>Concert ticket frenzy fills arena</title>
  <link>https://example.com/noise</link>
  <pubDate>Sun, 18 Oct 2026 01:45:00 GMT</pubDate>
</item>
</channel></rss>
"""


def test_fetch_feed_parses_items():
    from tt_core import daily_news as dn

    class FakeResp:
        def read(self):
            return _SAMPLE_RSS.encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    with patch.object(dn, "urlopen", return_value=FakeResp()):
        rows = dn._fetch_feed("society", "港聞", "https://example.com/rss", limit=5)
    assert len(rows) == 2
    assert rows[0]["title"] == "港府公布新措施"
    assert rows[0]["url"] == "https://example.com/a"
    assert rows[0]["source"] == "港聞"
    assert rows[0]["pillar"] == "society"


def test_finance_feed_skips_non_economic():
    from tt_core import daily_news as dn

    class FakeResp:
        def read(self):
            return _FINANCE_RSS.encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    with patch.object(dn, "urlopen", return_value=FakeResp()):
        rows = dn._fetch_feed("finance", "港台財經", "https://example.com/fin", limit=5)
    assert len(rows) == 1
    assert rows[0]["pillar"] == "finance"
    assert "港股" in rows[0]["title"]


def test_pick_balanced_five_across_pillars():
    from tt_core.daily_news import _pick_balanced

    items = [
        {"title": "公屋輪候民生壓力升", "url": "https://a1", "source": "港聞", "pillar": "society", "ts": 10},
        {"title": "公立醫院急症室逼爆", "url": "https://a2", "source": "港聞", "pillar": "society", "ts": 9},
        {"title": "本地社會花邊甲", "url": "https://a3", "source": "港聞", "pillar": "society", "ts": 8},
        {"title": "利率決議影響股市", "url": "https://f1", "source": "財經", "pillar": "finance", "ts": 7},
        {"title": "銀行公布業績", "url": "https://f2", "source": "財經", "pillar": "finance", "ts": 6},
        {"title": "國務院發布新政策", "url": "https://c1", "source": "中國", "pillar": "china", "ts": 5},
        {"title": "內地另一政策", "url": "https://c2", "source": "中國", "pillar": "china", "ts": 4},
    ]
    picked = _pick_balanced(items, limit=5)
    assert len(picked) == 5
    pillars = [p["pillar"] for p in picked]
    assert pillars.count("society") == 2
    assert pillars.count("finance") == 2
    assert pillars.count("china") == 1
    society_titles = [p["title"] for p in picked if p["pillar"] == "society"]
    assert "公屋輪候民生壓力升" in society_titles
    assert "公立醫院急症室逼爆" in society_titles
    for row in picked:
        assert row["wa_text"]
        assert "wa.me" in row["wa_url"]
        assert row["pillar_label"] in ("社會問題", "金融經濟", "內地政經")


def test_pick_priority_prefers_substance_over_recency():
    from tt_core.daily_news import _pick_priority

    items = [
        # Fresh but fluff society
        {"title": "商場展覽人流升", "url": "https://fluff", "source": "港聞", "pillar": "society", "ts": 999},
        # Older but real social issue
        {"title": "公屋輪候時間再創新高", "url": "https://s", "source": "港台", "pillar": "society", "ts": 1},
        {"title": "聯儲局議息市場觀望", "url": "https://f", "source": "財經", "pillar": "finance", "ts": 2},
        {"title": "港股成交萎縮", "url": "https://f2", "source": "財經", "pillar": "finance", "ts": 3},
        {"title": "國務院會議部署穩增長", "url": "https://cn", "source": "中國", "pillar": "china", "ts": 4},
    ]
    picked = _pick_priority(items, limit=5)
    society = [p for p in picked if p["pillar"] == "society"]
    assert society
    assert "公屋" in society[0]["title"]


def test_pick_balanced_prefers_cjk():
    from tt_core.daily_news import _pick_balanced

    items = [
        {"title": "English only housing shortage story", "url": "https://e", "source": "SCMP", "pillar": "society", "ts": 99},
        {"title": "港府公布民生房屋措施", "url": "https://c", "source": "港台", "pillar": "society", "ts": 1},
        {"title": "股市創新高", "url": "https://f", "source": "財經", "pillar": "finance", "ts": 2},
        {"title": "銀行加息預期", "url": "https://f2", "source": "財經", "pillar": "finance", "ts": 3},
        {"title": "國務院會議部署", "url": "https://cn", "source": "中國", "pillar": "china", "ts": 4},
    ]
    picked = _pick_balanced(items, limit=5)
    society = [p for p in picked if p["pillar"] == "society"]
    assert society
    assert "港府" in society[0]["title"]


def test_whatsapp_opener_has_viewpoint_not_just_seen():
    from tt_core.daily_news import whatsapp_opener, wa_opener_url, _opener_angle

    border = whatsapp_opener("皇崗口岸通關人流上升", "society")
    rates = whatsapp_opener("聯儲局議息市場觀望", "finance")
    china = whatsapp_opener("國務院發布大灣區新措施", "china")

    # Must name the story…
    assert "皇崗" in border or "口岸" in border
    assert "聯儲" in rates or "議息" in rates
    # …and carry a real angle (not bare「睇過未／想聽下你點睇」only)
    assert "方便" in border or "生活圈" in border
    assert "閒置現金" in rates or "放錯位" in rates or "存款" in rates
    assert "跨境" in china or "政策" in china
    assert "想聽下你點睇" in border
    # Soft chat — not hard-sell insurance
    assert "投保" not in border and "保單" not in rates
    assert "wa.me" in wa_opener_url("皇崗口岸通關人流上升", "society")

    view, ask = _opener_angle("港股急跌", "finance")
    assert view and ask
    assert "？" in ask


def test_app_home_renders_daily_news():
    src = (_ROOT / "app.py").read_text(encoding="utf-8")
    home = src[src.index("def page_home") : src.index("def page_coach_tim")]
    assert "render_daily_news" in home
    assert "limit=5" in home
    news = (_ROOT / "tt_core" / "daily_news.py").read_text(encoding="utf-8")
    assert "今日重點新聞" in news
    assert "tt-news-row" in news
    assert "WhatsApp 開話題" in news
    assert "_news_panel_html" in news
    assert "PILLAR_LABELS" in news
    assert "_opener_angle" in news
    assert "<details" in news
    assert "tt-news-detail" in news
    assert "睇原文" in news
    render_src = news[news.index("def render_daily_news") :]
    assert "components.html" in render_src
    assert "st.link_button" not in render_src


def test_fetch_daily_headlines_dedupes_and_limits():
    from tt_core import daily_news as dn

    sample = [
        {
            "title": "同一標題",
            "url": "https://a",
            "source": "港聞",
            "pillar": "society",
            "published": None,
            "ts": 2,
        },
        {
            "title": "同一標題",
            "url": "https://b",
            "source": "國際",
            "pillar": "society",
            "published": None,
            "ts": 1,
        },
        {
            "title": "另一則社會",
            "url": "https://c",
            "source": "國際",
            "pillar": "society",
            "published": None,
            "ts": 3,
        },
        {
            "title": "利率消息",
            "url": "https://d",
            "source": "財經",
            "pillar": "finance",
            "published": None,
            "ts": 4,
        },
        {
            "title": "銀行消息",
            "url": "https://e",
            "source": "財經",
            "pillar": "finance",
            "published": None,
            "ts": 5,
        },
        {
            "title": "國務院政策",
            "url": "https://f",
            "source": "中國",
            "pillar": "china",
            "published": None,
            "ts": 6,
        },
    ]

    with patch.object(dn, "_fetch_feed", side_effect=[sample[:2], sample[2:3], sample[3:4], sample[4:5], sample[5:], [], []]):
        try:
            dn.fetch_daily_headlines.clear()
        except Exception:
            pass
        data = dn.fetch_daily_headlines(limit=5)
    titles = [i["title"] for i in data["items"]]
    assert "同一標題" in titles
    assert titles.count("同一標題") == 1
    assert len(data["items"]) <= 5
    assert data["ok"] is True


def test_news_panel_html_collapsed_accordion_and_escapes():
    from tt_core.daily_news import _news_panel_html

    html = _news_panel_html(
        [
            {
                "title": '測試 <b>XSS</b> & "quote"',
                "url": "https://example.com/x?a=1&b=2",
                "pillar_label": "社會關注",
                "wa_text": "嗨！想聽下你點睇？",
                "wa_url": "https://wa.me/?text=hi",
            },
            {
                "title": "財經第二則",
                "url": "https://example.com/y",
                "pillar_label": "財經經濟",
                "wa_text": "角度測試",
                "wa_url": "https://wa.me/?text=y",
            },
        ],
        fetched_at="2026-10-18 07:34",
    )
    assert "tt-news" in html
    assert html.count("<details") == 2
    assert "<summary" in html
    assert "tt-news-detail" in html
    assert "睇原文" in html
    assert "<b>XSS</b>" not in html
    assert "&lt;b&gt;XSS&lt;/b&gt;" in html
    assert "社會問題" in html or "社會關注" in html
    assert "金融經濟" in html or "財經經濟" in html
    assert "WhatsApp 開話題" in html
    assert "嗨！想聽下你點睇？" in html
    assert "wa.me" in html
    assert "01" in html
    assert "撳標題展開" in html
    assert "重中之重" in html or "今日" in html
    # Collapsed by default — no open attribute on details
    assert "<details open" not in html


def test_fetch_daily_headlines_uses_parallel_short_timeout():
    """Home must not chain slow RSS feeds after login."""
    import inspect

    from tt_core import daily_news as dn

    src = inspect.getsource(dn.fetch_daily_headlines)
    assert "ThreadPoolExecutor" in src
    assert "as_completed" in src
    assert "_load_daily_pin" in src or "_save_daily_pin" in src
    assert dn._FEED_TIMEOUT_SEC <= 5
    assert dn._FETCH_BUDGET_SEC <= 8


def test_daily_pin_keeps_same_five_across_calls(tmp_path, monkeypatch):
    """Same HK day → same locked pack (not reshuffled each login)."""
    from tt_core import daily_news as dn

    monkeypatch.setattr(dn, "_PIN_DIR", tmp_path)
    monkeypatch.setattr(dn, "_hk_today", lambda: "2026-10-20")

    pack = {
        "day": "2026-10-20",
        "fetched_at": "2026-10-20 08:00",
        "ok": True,
        "items": [
            {
                "title": "公屋輪候創新高",
                "url": "https://s1",
                "source": "港聞",
                "pillar": "society",
                "ts": 1,
            },
            {
                "title": "公立醫院逼爆",
                "url": "https://s2",
                "source": "港聞",
                "pillar": "society",
                "ts": 2,
            },
            {
                "title": "聯儲局議息",
                "url": "https://f1",
                "source": "財經",
                "pillar": "finance",
                "ts": 3,
            },
            {
                "title": "港股成交萎縮",
                "url": "https://f2",
                "source": "財經",
                "pillar": "finance",
                "ts": 4,
            },
            {
                "title": "國務院部署穩增長",
                "url": "https://c1",
                "source": "中國",
                "pillar": "china",
                "ts": 5,
            },
        ],
    }
    (tmp_path / "daily_news_2026-10-20.json").write_text(
        __import__("json").dumps(pack, ensure_ascii=False), encoding="utf-8"
    )

    def _boom(*a, **k):
        raise AssertionError("RSS must not be called when pin exists")

    with patch.object(dn, "_fetch_feed_safe", side_effect=_boom):
        try:
            dn.fetch_daily_headlines.clear()
        except Exception:
            pass
        a = dn.fetch_daily_headlines(limit=5, day="2026-10-20")
        try:
            dn.fetch_daily_headlines.clear()
        except Exception:
            pass
        b = dn.fetch_daily_headlines(limit=5, day="2026-10-20")

    assert a["pinned"] is True
    assert [i["title"] for i in a["items"]] == [i["title"] for i in b["items"]]
    assert len(a["items"]) == 5
    assert a["items"][0]["wa_url"].startswith("https://wa.me/")


def test_live_rss_optional_smoke():
    """Network smoke — skip soft-fail if offline."""
    from tt_core.daily_news import _fetch_feed

    try:
        rows = _fetch_feed(
            "society",
            "BBC中文",
            "https://feeds.bbci.co.uk/zhongwen/trad/rss.xml",
            limit=2,
        )
    except Exception:
        return
    assert rows
    assert rows[0]["title"]
    assert rows[0]["url"].startswith("http")
    assert rows[0]["pillar"] in ("society", "finance", "china")
