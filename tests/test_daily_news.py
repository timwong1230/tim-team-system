"""Homepage daily headlines from public RSS."""

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
        rows = dn._fetch_feed("港聞", "https://example.com/rss", limit=5)
    assert len(rows) == 2
    assert rows[0]["title"] == "港府公布新措施"
    assert rows[0]["url"] == "https://example.com/a"
    assert rows[0]["source"] == "港聞"


def test_fetch_daily_headlines_dedupes_and_limits():
    from tt_core import daily_news as dn

    sample = [
        {"title": "同一標題", "url": "https://a", "source": "港聞", "published": None, "ts": 2},
        {"title": "同一標題", "url": "https://b", "source": "國際", "published": None, "ts": 1},
        {"title": "另一則", "url": "https://c", "source": "國際", "published": None, "ts": 3},
    ]

    with patch.object(dn, "_fetch_feed", side_effect=[sample[:1], sample[1:], []]):
        # Clear streamlit cache between runs
        try:
            dn.fetch_daily_headlines.clear()
        except Exception:
            pass
        data = dn.fetch_daily_headlines(limit=8)
    titles = [i["title"] for i in data["items"]]
    assert "同一標題" in titles
    assert titles.count("同一標題") == 1
    assert "另一則" in titles
    assert data["ok"] is True


def test_app_home_renders_daily_news():
    src = (_ROOT / "app.py").read_text(encoding="utf-8")
    home = src[src.index("def page_home") : src.index("def page_coach_tim")]
    assert "render_daily_news" in home
    news = (_ROOT / "tt_core" / "daily_news.py").read_text(encoding="utf-8")
    assert "今日重點新聞" in news
    assert "tt-news-row" in news
    assert "components.html" in news
    assert "_news_panel_html" in news


def test_news_panel_html_escapes_and_styles():
    from tt_core.daily_news import _news_panel_html

    html = _news_panel_html(
        [
            {
                "title": '測試 <b>XSS</b> & "quote"',
                "url": "https://example.com/x?a=1&b=2",
                "source": "港聞",
            }
        ],
        fetched_at="2026-10-18 07:34",
    )
    assert "tt-news" in html
    assert "<b>XSS</b>" not in html
    assert "&lt;b&gt;XSS&lt;/b&gt;" in html
    assert "港聞" in html
    assert "01" in html


def test_live_rss_optional_smoke():
    """Network smoke — skip soft-fail if offline."""
    from tt_core.daily_news import _fetch_feed

    try:
        rows = _fetch_feed(
            "國際",
            "https://feeds.bbci.co.uk/zhongwen/trad/rss.xml",
            limit=2,
        )
    except Exception:
        return
    assert rows
    assert rows[0]["title"]
    assert rows[0]["url"].startswith("http")
