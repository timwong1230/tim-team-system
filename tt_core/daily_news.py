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


def render_daily_news(*, limit: int = 8) -> None:
    """Homepage block: 今日重點新聞."""
    st.markdown("### 今日重點新聞")
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

    st.caption(f"更新於 {data.get('fetched_at')} · 港台／BBC 中文")
    for row in items:
        title = html.escape(str(row.get("title") or ""))
        url = str(row.get("url") or "").replace('"', "%22")
        source = html.escape(str(row.get("source") or ""))
        st.markdown(
            f'- <a href="{url}" target="_blank" rel="noopener noreferrer">{title}</a>'
            f' <span style="color:#6B7280;font-size:0.85em;">· {source}</span>',
            unsafe_allow_html=True,
        )
