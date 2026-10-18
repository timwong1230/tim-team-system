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
        {"title": "本地社會新聞甲", "url": "https://a1", "source": "港聞", "pillar": "society", "ts": 10},
        {"title": "本地社會新聞乙", "url": "https://a2", "source": "港聞", "pillar": "society", "ts": 9},
        {"title": "本地社會新聞丙", "url": "https://a3", "source": "港聞", "pillar": "society", "ts": 8},
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
    for row in picked:
        assert row["wa_text"]
        assert "wa.me" in row["wa_url"]
        assert row["pillar_label"] in ("社會關注", "財經經濟", "內地政策")


def test_pick_balanced_prefers_cjk():
    from tt_core.daily_news import _pick_balanced

    items = [
        {"title": "English only society story", "url": "https://e", "source": "SCMP", "pillar": "society", "ts": 99},
        {"title": "港府公布民生措施", "url": "https://c", "source": "港台", "pillar": "society", "ts": 1},
        {"title": "股市創新高", "url": "https://f", "source": "財經", "pillar": "finance", "ts": 2},
        {"title": "銀行加息預期", "url": "https://f2", "source": "財經", "pillar": "finance", "ts": 3},
        {"title": "國務院會議部署", "url": "https://cn", "source": "中國", "pillar": "china", "ts": 4},
    ]
    picked = _pick_balanced(items, limit=5)
    society = [p for p in picked if p["pillar"] == "society"]
    assert society
    assert "港府" in society[0]["title"]


def test_whatsapp_opener_by_pillar():
    from tt_core.daily_news import whatsapp_opener, wa_opener_url

    soc = whatsapp_opener("港鐵訊號故障", "society")
    fin = whatsapp_opener("聯儲局議息", "finance")
    chi = whatsapp_opener("國務院新措施", "china")
    assert "港鐵訊號故障" in soc
    assert "聯儲局議息" in fin
    assert "國務院新措施" in chi
    assert "保險" not in soc and "投保" not in soc
    assert "wa.me" in wa_opener_url("港鐵訊號故障", "society")


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


def test_app_home_renders_daily_news():
    src = (_ROOT / "app.py").read_text(encoding="utf-8")
    home = src[src.index("def page_home") : src.index("def page_coach_tim")]
    assert "render_daily_news" in home
    assert "limit=5" in home
    news = (_ROOT / "tt_core" / "daily_news.py").read_text(encoding="utf-8")
    assert "今日重點新聞" in news
    assert "WhatsApp 開話題" in news
    assert "link_button" in news
    assert "開 WhatsApp" in news
    assert "財經經濟" in news
    assert "內地政策" in news
    assert "PILLAR_LABELS" in news
    # Native Streamlit render (not iframe-only) so phone can open wa.me
    render_src = news[news.index("def render_daily_news") :]
    assert "st.link_button" in render_src
    assert "components.html" not in render_src


def test_news_panel_html_includes_wa_and_escapes():
    from tt_core.daily_news import _news_panel_html

    html = _news_panel_html(
        [
            {
                "title": '測試 <b>XSS</b> & "quote"',
                "url": "https://example.com/x?a=1&b=2",
                "pillar_label": "社會關注",
                "wa_text": "嗨！想聽下你點睇？",
                "wa_url": "https://wa.me/?text=hi",
            }
        ],
        fetched_at="2026-10-18 07:34",
    )
    assert "tt-news" in html
    assert "<b>XSS</b>" not in html
    assert "&lt;b&gt;XSS&lt;/b&gt;" in html
    assert "社會關注" in html
    assert "WhatsApp 開話題" in html
    assert "嗨！想聽下你點睇？" in html
    assert "wa.me" in html
    assert "01" in html
    assert "每日 5 則" in html


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
