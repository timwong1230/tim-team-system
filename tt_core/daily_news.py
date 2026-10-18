"""今日重點新聞 — 3 pillars, 5 headlines, WhatsApp openers for prospects."""

from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

import streamlit as st

# pillar → display label
PILLAR_LABELS = {
    "society": "社會關注",
    "finance": "財經經濟",
    "china": "內地政策",
}

# Feeds tagged by preferred pillar (verified public RSS)
_FEEDS: list[tuple[str, str, str]] = [
    # society — local + world attention
    ("society", "港台港聞", "https://rthk.hk/rthk/news/rss/c_expressnews_clocal.xml"),
    ("society", "港台國際", "https://rthk.hk/rthk/news/rss/c_expressnews_cinternational.xml"),
    ("society", "BBC中文", "https://feeds.bbci.co.uk/zhongwen/trad/rss.xml"),
    ("society", "SCMP港聞", "https://www.scmp.com/rss/2/feed"),
    # finance
    ("finance", "港台財經", "https://rthk.hk/rthk/news/rss/c_expressnews_cfinance.xml"),
    ("finance", "SCMP財經", "https://www.scmp.com/rss/91/feed"),
    # mainland China policy / China desk
    ("china", "SCMP中國", "https://www.scmp.com/rss/4/feed"),
]

_UA = "TIM-TEAM-News/1.0 (+https://tim-team-system.streamlit.app)"
_TAG_RE = re.compile(r"<[^>]+>")

_FINANCE_KW = re.compile(
    r"經濟|金融|財經|股市|樓市|利率|通脹|通縮|就業|GDP|匯市|港元|美元|聯儲|美聯儲|"
    r"加息|減息|財赤|預算|稅|關稅|貿易|出口|進口|銀行|保險|證券|IPO|債|基金|"
    r"economy|market|stock|inflation|interest|fed|tariff|bank|gdp",
    re.I,
)
_CHINA_KW = re.compile(
    r"中國|內地|北京|國務院|中央|習近平|人行|人民幣|一帶一路|粵港澳|大灣區|"
    r"政策|部委|發改委|商務部|國安|兩會|黨|省委|市政府|"
    r"china|beijing|xi jinping|pboc|yuan|cpc",
    re.I,
)
# Soft filter: drop obvious entertainment/sports noise from society picks
_NOISE_KW = re.compile(
    r"球賽|足球|籃球|演唱會|娛樂|明星|戀情|綜藝|電影票房|奧運金牌",
    re.I,
)


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
        for child in el:
            if child.tag.endswith("}" + tag) or child.tag == tag:
                if (child.text or "").strip():
                    return (child.text or "").strip()
    return ""


_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_CHINA_POLICY_KW = re.compile(
    r"國務院|中央|政策|人行|人民幣|兩會|部委|發改委|國安|粵港澳|大灣區|"
    r"習近平|商務部|白皮書|條例|法規|監管|刺激|穩增長",
    re.I,
)


def _has_cjk(text: str) -> bool:
    return bool(_CJK_RE.search(text or ""))


def _classify_pillar(title: str, feed_pillar: str) -> str:
    """Re-tag by keywords when feed is mixed; keep feed pillar as default."""
    t = title or ""
    has_finance = bool(_FINANCE_KW.search(t))
    has_china = bool(_CHINA_KW.search(t))
    has_policy = bool(_CHINA_POLICY_KW.search(t))

    # Mainland policy desk / clear China-policy angle
    if feed_pillar == "china":
        if has_finance and not has_policy:
            return "finance"
        return "china"
    if has_policy and has_china:
        return "china"

    # Finance feed / economic keywords
    if feed_pillar == "finance":
        if has_finance:
            return "finance"
        if has_china and has_policy:
            return "china"
        # Non-economic noise from a finance feed → drop later via skip flag
        return "skip"
    if has_finance:
        return "finance"

    if has_china and has_policy:
        return "china"
    return "society"


def _fetch_feed(pillar: str, source: str, url: str, *, limit: int = 8) -> list[dict[str, Any]]:
    req = Request(
        url,
        headers={
            "User-Agent": _UA,
            "Accept": "application/rss+xml, application/xml, text/xml, */*",
        },
    )
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
        if _NOISE_KW.search(title) and pillar == "society":
            continue
        pub = _parse_date(_local_text(item, "pubDate", "published", "updated"))
        final_pillar = _classify_pillar(title, pillar)
        if final_pillar == "skip":
            continue
        out.append(
            {
                "title": title[:160],
                "url": link,
                "source": source,
                "pillar": final_pillar,
                "pillar_label": PILLAR_LABELS.get(final_pillar, final_pillar),
                "published": pub.isoformat() if pub else None,
                "ts": pub.timestamp() if pub else 0.0,
            }
        )
        if len(out) >= limit:
            break
    return out


def whatsapp_opener(title: str, pillar: str) -> str:
    """Cantonese WhatsApp icebreaker — start a chat, not a hard sell."""
    t = _strip_html(title).strip()
    if len(t) > 42:
        t = t[:40] + "…"
    if pillar == "finance":
        return (
            f"嗨！早晨🙂 今日睇到「{t}」，"
            f"想聽下你點睇？呢類消息對你哋最近有冇影響？"
        )
    if pillar == "china":
        return (
            f"嗨！🙂 睇到一則關於內地「{t}」，"
            f"你點睇？會唔會同你哋業務／家人計劃有關？"
        )
    return (
        f"嗨！早晨🙂 今日好多人傾緊「{t}」，"
        f"想聽下你點睇？有冇特別感覺？"
    )


def wa_opener_url(title: str, pillar: str) -> str:
    return f"https://wa.me/?text={quote(whatsapp_opener(title, pillar))}"


def _pick_balanced(items: list[dict[str, Any]], *, limit: int = 5) -> list[dict[str, Any]]:
    """Prefer 2 society + 2 finance + 1 china; backfill if a pillar is thin.

    Prefer Traditional/Simplified Chinese titles (better for HK WhatsApp openers).
    """
    by: dict[str, list[dict[str, Any]]] = {"society": [], "finance": [], "china": []}
    seen: set[str] = set()

    def _rank_key(row: dict[str, Any]) -> tuple:
        # Higher = better: CJK first, then recency
        return (1 if _has_cjk(row.get("title") or "") else 0, row.get("ts") or 0.0)

    for row in sorted(items, key=_rank_key, reverse=True):
        key = re.sub(r"\s+", "", row["title"]).lower()
        if key in seen:
            continue
        seen.add(key)
        p = row.get("pillar") or "society"
        if p not in by:
            p = "society"
        by[p].append(row)

    # Within each pillar, keep CJK + newest order
    for p in by:
        by[p].sort(key=_rank_key, reverse=True)

    quotas = {"society": 2, "finance": 2, "china": 1}
    picked: list[dict[str, Any]] = []
    used: set[str] = set()

    def _take(pillar: str, n: int) -> None:
        for row in by.get(pillar, []):
            if len([x for x in picked if x["pillar"] == pillar]) >= n:
                break
            k = re.sub(r"\s+", "", row["title"]).lower()
            if k in used:
                continue
            used.add(k)
            picked.append(row)

    for pillar, n in quotas.items():
        _take(pillar, n)

    # Backfill to `limit` from remaining (CJK-first)
    if len(picked) < limit:
        rest: list[dict[str, Any]] = []
        for pillar in ("society", "finance", "china"):
            rest.extend(by[pillar])
        rest.sort(key=_rank_key, reverse=True)
        for row in rest:
            if len(picked) >= limit:
                break
            k = re.sub(r"\s+", "", row["title"]).lower()
            if k in used:
                continue
            used.add(k)
            picked.append(row)

    for row in picked:
        pillar = row.get("pillar") or "society"
        row["wa_text"] = whatsapp_opener(row["title"], pillar)
        row["wa_url"] = wa_opener_url(row["title"], pillar)
        row["pillar_label"] = PILLAR_LABELS.get(pillar, "社會關注")

    return picked[:limit]


@st.cache_data(ttl=30 * 60, show_spinner=False)
def fetch_daily_headlines(limit: int = 5) -> dict[str, Any]:
    """Return up to 5 headlines across 3 pillars. Cached 30 minutes."""
    collected: list[dict[str, Any]] = []
    errors: list[str] = []
    for pillar, source, url in _FEEDS:
        try:
            # Pull a bit deeper so CJK china/finance signals aren't cut off
            collected.extend(_fetch_feed(pillar, source, url, limit=10))
        except (HTTPError, URLError, ET.ParseError, TimeoutError, OSError) as e:
            errors.append(f"{source}:{type(e).__name__}")
        except Exception as e:
            errors.append(f"{source}:{type(e).__name__}")

    items = _pick_balanced(collected, limit=limit)
    return {
        "items": items,
        "fetched_at": datetime.now().astimezone().strftime("%Y-%m-%d %H:%M"),
        "errors": errors,
        "ok": bool(items),
    }


def _news_panel_html(items: list[dict[str, Any]], *, fetched_at: str) -> str:
    """Self-contained briefing panel with WhatsApp openers."""
    rows = []
    for i, row in enumerate(items, start=1):
        title = html.escape(str(row.get("title") or ""))
        url = html.escape(str(row.get("url") or ""), quote=True)
        pillar = html.escape(str(row.get("pillar_label") or row.get("source") or ""))
        wa_text = html.escape(str(row.get("wa_text") or ""))
        wa_url = html.escape(str(row.get("wa_url") or ""), quote=True)
        idx = f"{i:02d}"
        rows.append(
            f'<div class="tt-news-row">'
            f'<span class="tt-news-idx">{idx}</span>'
            f'<div class="tt-news-body">'
            f'<span class="tt-news-src">{pillar}</span>'
            f'<a class="tt-news-title" href="{url}" target="_blank" rel="noopener noreferrer">{title}</a>'
            f'<div class="tt-news-wa">'
            f'<div class="tt-news-wa-label">WhatsApp 開話題</div>'
            f'<div class="tt-news-wa-text">{wa_text}</div>'
            f'<a class="tt-news-wa-btn" href="{wa_url}" target="_blank" rel="noopener noreferrer">開 WhatsApp</a>'
            f"</div>"
            f"</div>"
            f"</div>"
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
    padding: 16px 16px 12px;
    box-shadow: 0 10px 28px rgba(28, 36, 48, 0.05);
  }}
  .tt-news-head {{
    display: flex; align-items: flex-end; justify-content: space-between;
    gap: 12px; margin-bottom: 10px; padding: 0 2px 10px;
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
    line-height: 1.35; padding-bottom: 2px;
  }}
  .tt-news-list {{ display: flex; flex-direction: column; gap: 8px; }}
  .tt-news-row {{
    display: grid; grid-template-columns: 36px 1fr;
    gap: 10px; align-items: start;
    padding: 10px 8px 12px; border-radius: 12px;
    background: rgba(255,255,255,0.55);
    border: 1px solid #EEE9DF;
  }}
  .tt-news-idx {{
    font-family: 'Instrument Serif', Georgia, serif;
    font-size: 1.15rem; color: #C5A028; line-height: 1.2;
    padding-top: 2px;
  }}
  .tt-news-body {{ display: flex; flex-direction: column; gap: 6px; min-width: 0; }}
  .tt-news-src {{
    display: inline-block; align-self: flex-start;
    font-size: 0.66rem; letter-spacing: 0.08em; font-weight: 650;
    color: #7A6420; background: #F7F1DE;
    border: 1px solid #E2D4A8; border-radius: 999px;
    padding: 2px 8px; line-height: 1.3;
  }}
  .tt-news-title {{
    font-size: 0.98rem; font-weight: 650; line-height: 1.4;
    color: #1C2430; text-decoration: none;
  }}
  .tt-news-title:hover {{ color: #9A7B1A; }}
  .tt-news-wa {{
    margin-top: 2px; padding: 10px 12px;
    background: #F3F1EB; border-radius: 10px;
    border-left: 3px solid #C5A028;
  }}
  .tt-news-wa-label {{
    font-size: 0.68rem; letter-spacing: 0.1em; text-transform: uppercase;
    color: #9A7B1A; font-weight: 700; margin-bottom: 4px;
  }}
  .tt-news-wa-text {{
    font-size: 0.86rem; line-height: 1.45; color: #374151; margin-bottom: 8px;
  }}
  .tt-news-wa-btn {{
    display: inline-block; font-size: 0.82rem; font-weight: 650;
    color: #1C2430; background: linear-gradient(135deg, #D4AF37, #B38F21);
    padding: 7px 12px; border-radius: 8px; text-decoration: none;
  }}
  @media (prefers-color-scheme: dark) {{
    body {{ color: #E8EAED; }}
    .tt-news {{
      background: linear-gradient(165deg, #1A222D 0%, #151C26 100%);
      border-color: #2F3A48; box-shadow: none;
    }}
    .tt-news-head {{ border-bottom-color: #2F3A48; }}
    .tt-news-title-main, .tt-news-title {{ color: #E8EAED; }}
    .tt-news-meta {{ color: #9CA3AF; }}
    .tt-news-row {{ background: #121820; border-color: #2F3A48; }}
    .tt-news-src {{
      color: #F5E6B8; background: #3A3420; border-color: #5C4A12;
    }}
    .tt-news-idx {{ color: #E0C15A; }}
    .tt-news-wa {{ background: #0F1419; border-left-color: #E0C15A; }}
    .tt-news-wa-label {{ color: #E0C15A; }}
    .tt-news-wa-text {{ color: #C5CAD3; }}
  }}
</style></head><body>
<div class="tt-news">
  <div class="tt-news-head">
    <div>
      <div class="tt-news-kicker">Morning briefing</div>
      <h2 class="tt-news-title-main">今日重點新聞</h2>
    </div>
    <div class="tt-news-meta">{when}<br/>社會 · 財經 · 內地<br/>每日 5 則</div>
  </div>
  <div class="tt-news-list">{body}</div>
</div>
</body></html>"""


def render_daily_news(*, limit: int = 5) -> None:
    """Homepage block: 今日重點新聞 (3 pillars + WhatsApp openers)."""
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
    # header ~90 + ~150 per item with WhatsApp opener block
    height = 100 + (150 * len(items))
    components.html(panel, height=min(height, 900), scrolling=True)
