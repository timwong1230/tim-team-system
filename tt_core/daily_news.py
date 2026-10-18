"""今日重點新聞 — fetch public RSS (no API key) for the homepage."""

from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import streamlit as st

# Public feeds that work without keys (verified)
_FEEDS: list[tuple[str, str]] = [
    ("港聞", "https://rthk.hk/rthk/news/rss/c_expressnews_clocal.xml"),
    ("國際", "https://rthk.hk/rthk/news/rss/c_expressnews_cinternational.xml"),
    ("國際", "https://feeds.bbci.co.uk/zhongwen/trad/rss.xml"),
]

_UA = "TIM-TEAM-News/1.0 (+https://tim-team-system.streamlit.app)"
_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    t = _TAG_RE.sub("", html.unescape(text or ""))
    return re.sub(r"\s+", " ", t).strip()


def _parse_date(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _local_text(el: ET.Element | None, *tags: str) -> str:
    if el is None:
        return ""
    for tag in tags:
        child = el.find(tag)
        if child is not None and (child.text or "").strip():
            return (child.text or "").strip()
        # RSS with namespaces: ignore ns prefix
        for child in el:
            if child.tag.endswith("}" + tag) or child.tag == tag:
                if (child.text or "").strip():
                    return (child.text or "").strip()
    return ""


def _fetch_feed(source: str, url: str, *, limit: int = 6) -> list[dict[str, Any]]:
    req = Request(url, headers={"User-Agent": _UA, "Accept": "application/rss+xml, application/xml, text/xml, */*"})
    with urlopen(req, timeout=10) as resp:
        raw = resp.read()
    root = ET.fromstring(raw)
    channel = root.find("channel")
    items = channel.findall("item") if channel is not None else root.findall(".//item")
    out: list[dict[str, Any]] = []
    for item in items:
        title = _strip_html(_local_text(item, "title"))
        link = _local_text(item, "link")
        if not title or not link:
            continue
        pub = _parse_date(_local_text(item, "pubDate", "published", "updated"))
        out.append(
            {
                "title": title[:160],
                "url": link,
                "source": source,
                "published": pub.isoformat() if pub else None,
                "ts": pub.timestamp() if pub else 0.0,
            }
        )
        if len(out) >= limit:
            break
    return out


@st.cache_data(ttl=30 * 60, show_spinner=False)
def fetch_daily_headlines(limit: int = 8) -> dict[str, Any]:
    """Return mixed HK + world headlines. Cached 30 minutes."""
    collected: list[dict[str, Any]] = []
    errors: list[str] = []
    for source, url in _FEEDS:
        try:
            # Take a few from each feed, then merge/sort
            collected.extend(_fetch_feed(source, url, limit=5))
        except (HTTPError, URLError, ET.ParseError, TimeoutError, OSError) as e:
            errors.append(f"{source}:{type(e).__name__}")
        except Exception as e:
            errors.append(f"{source}:{type(e).__name__}")

    # Dedupe by normalized title
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for row in sorted(collected, key=lambda r: r.get("ts") or 0.0, reverse=True):
        key = re.sub(r"\s+", "", row["title"]).lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
        if len(unique) >= limit:
            break

    return {
        "items": unique,
        "fetched_at": datetime.now().astimezone().strftime("%Y-%m-%d %H:%M"),
        "errors": errors,
        "ok": bool(unique),
    }


def _news_panel_html(items: list[dict[str, Any]], *, fetched_at: str) -> str:
    """Self-contained briefing panel (components.html keeps CSS)."""
    rows = []
    for i, row in enumerate(items, start=1):
        title = html.escape(str(row.get("title") or ""))
        url = html.escape(str(row.get("url") or ""), quote=True)
        source = html.escape(str(row.get("source") or ""))
        idx = f"{i:02d}"
        rows.append(
            f'<a class="tt-news-row" href="{url}" target="_blank" rel="noopener noreferrer">'
            f'<span class="tt-news-idx">{idx}</span>'
            f'<span class="tt-news-body">'
            f'<span class="tt-news-src">{source}</span>'
            f'<span class="tt-news-title">{title}</span>'
            f"</span>"
            f'<span class="tt-news-go" aria-hidden="true">↗</span>'
            f"</a>"
        )
    body = "".join(rows)
    when = html.escape(fetched_at or "")
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Instrument+Serif&display=swap');
  html, body {{
    margin: 0; padding: 0; background: transparent;
    font-family: 'DM Sans', -apple-system, BlinkMacSystemFont, sans-serif;
    color: #1C2430;
  }}
  .tt-news {{
    background: linear-gradient(165deg, #FFFEFA 0%, #F7F5F0 100%);
    border: 1px solid #E8E4D9;
    border-radius: 16px;
    padding: 16px 16px 10px;
    box-shadow: 0 10px 28px rgba(28, 36, 48, 0.05);
  }}
  .tt-news-head {{
    display: flex; align-items: flex-end; justify-content: space-between;
    gap: 12px; margin-bottom: 12px; padding: 0 2px 10px;
    border-bottom: 1px solid #E8E4D9;
  }}
  .tt-news-kicker {{
    font-size: 0.68rem; letter-spacing: 0.16em; text-transform: uppercase;
    color: #C5A028; font-weight: 650; margin: 0 0 4px;
  }}
  .tt-news-title-main {{
    font-family: 'Instrument Serif', Georgia, serif;
    font-size: 1.45rem; line-height: 1.15; margin: 0; color: #1C2430;
  }}
  .tt-news-meta {{
    font-size: 0.72rem; color: #6B7280; text-align: right;
    white-space: nowrap; padding-bottom: 2px;
  }}
  .tt-news-list {{ display: flex; flex-direction: column; gap: 2px; }}
  .tt-news-row {{
    display: grid; grid-template-columns: 36px 1fr 22px;
    gap: 10px; align-items: start;
    text-decoration: none; color: inherit;
    padding: 11px 8px; border-radius: 12px;
    transition: background 0.15s ease;
  }}
  .tt-news-row:hover, .tt-news-row:active {{
    background: rgba(197, 160, 40, 0.10);
  }}
  .tt-news-idx {{
    font-family: 'Instrument Serif', Georgia, serif;
    font-size: 1.15rem; color: #C5A028; line-height: 1.2;
    padding-top: 1px;
  }}
  .tt-news-body {{ display: flex; flex-direction: column; gap: 4px; min-width: 0; }}
  .tt-news-src {{
    display: inline-block; align-self: flex-start;
    font-size: 0.66rem; letter-spacing: 0.08em; font-weight: 650;
    color: #7A6420; background: #F7F1DE;
    border: 1px solid #E2D4A8; border-radius: 999px;
    padding: 2px 8px; line-height: 1.3;
  }}
  .tt-news-title {{
    font-size: 0.98rem; font-weight: 600; line-height: 1.4;
    color: #1C2430;
  }}
  .tt-news-go {{
    color: #C5A028; font-size: 0.95rem; padding-top: 14px; opacity: 0.85;
  }}
  @media (prefers-color-scheme: dark) {{
    body {{ color: #E8EAED; }}
    .tt-news {{
      background: linear-gradient(165deg, #1A222D 0%, #151C26 100%);
      border-color: #2F3A48;
      box-shadow: none;
    }}
    .tt-news-head {{ border-bottom-color: #2F3A48; }}
    .tt-news-title-main {{ color: #E8EAED; }}
    .tt-news-meta {{ color: #9CA3AF; }}
    .tt-news-row:hover, .tt-news-row:active {{
      background: rgba(224, 193, 90, 0.12);
    }}
    .tt-news-title {{ color: #E8EAED; }}
    .tt-news-src {{
      color: #F5E6B8; background: #3A3420; border-color: #5C4A12;
    }}
    .tt-news-idx, .tt-news-go {{ color: #E0C15A; }}
  }}
</style></head><body>
<div class="tt-news">
  <div class="tt-news-head">
    <div>
      <div class="tt-news-kicker">Morning briefing</div>
      <h2 class="tt-news-title-main">今日重點新聞</h2>
    </div>
    <div class="tt-news-meta">{when}<br/>港台／BBC</div>
  </div>
  <div class="tt-news-list">{body}</div>
</div>
</body></html>"""


def render_daily_news(*, limit: int = 8) -> None:
    """Homepage block: 今日重點新聞 (styled briefing panel)."""
    import streamlit.components.v1 as components

    try:
        data = fetch_daily_headlines(limit=limit)
    except Exception:
        st.caption("新聞暫時載入唔到，稍後自動再試。")
        return

    items = data.get("items") or []
    if not items:
        st.caption("新聞暫時載入唔到，稍後自動再試。")
        if data.get("errors"):
            st.caption("（網絡／RSS 暫時唔穩定）")
        return

    panel = _news_panel_html(items, fetched_at=str(data.get("fetched_at") or ""))
    # ~78px header + ~64px per row
    height = 88 + (64 * len(items))
    components.html(panel, height=min(height, 620), scrolling=False)
