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


def _short_title(title: str, *, n: int = 36) -> str:
    t = _strip_html(title).strip()
    return (t[: n - 1] + "…") if len(t) > n else t


def _opener_angle(title: str, pillar: str) -> tuple[str, str]:
    """Return (viewpoint, soft_question) — a real take, not「睇過未」."""
    t = title or ""

    # --- theme detectors (order matters: more specific first) ---
    if re.search(r"口岸|通關|邊境|過關|皇崗|羅湖|高鐵|大橋", t):
        return (
            "感覺通關愈來愈方便，香港同內地生活圈真係愈嚟愈近；"
            "近排好多朋友都將「北上食飯／weekend」當日常。",
            "你哋近排會唔會多咗過關計劃？定係反而更珍惜留喺香港嘅時間？",
        )
    if re.search(r"樓市|樓價|成交|按揭|租金|住宅|二手樓|新盤", t):
        return (
            "樓市呢排氣氛仲係好審慎，買同租都有人喺度等訊號；"
            "我覺得關鍵唔係追頂或抄底，而係自己嘅現金流同持貨能力撐唔撐得住。",
            "你身邊朋友而家偏觀望多，定係已經開始行動？",
        )
    if re.search(r"利率|加息|減息|聯儲|美聯儲|息口|按揭息|存款息", t):
        return (
            "息口一有風吹草動，存款、貸款同投資部署都會跟住郁；"
            "我反而覺得呢段時間最值得檢視嘅，係閒置現金有冇「放錯位」。",
            "你而家較多睇存款穩陣，定係開始諗點樣再配置？",
        )
    if re.search(r"股市|港股|美股|恒指|納指|IPO|證券|牛熊|回調|反彈", t):
        return (
            "市況一波動，最易係情緒先行；"
            "我哋團隊近排同客戶傾得多係：分清短期噪音同中長線目標，先至唔會被標題牽着走。",
            "你睇呢輪波動係入市機會，定係先觀望為上？",
        )
    if re.search(r"通脹|通縮|物價|消費|零售|就業|失業|人工|薪金", t):
        return (
            "生活成本同收入預期一齊變，家庭同公司都要重新計帳；"
            "我覺得而家好多人其實唔係「冇錢」，而係現金流被切得太碎。",
            "你近排感覺開支壓力大咗，定係收入端變化更明顯？",
        )
    if re.search(r"財赤|預算|稅|關稅|貿易戰|貿易|出口|進口|赤字", t):
        return (
            "財政同貿易消息一出，資金同企業都會重新評估成本；"
            "對香港嚟講，我睇重點係我哋點樣喺不穩定外圍入面保住自己嘅彈性。",
            "你哋行業近排有冇因為成本／訂單受影響？",
        )
    if re.search(r"銀行|保險|基金|理財|財富|資產|美元|港元|匯價|匯率", t):
        return (
            "金融消息一多，最緊要係分清「市場噪音」同「同自己有關嘅決策」；"
            "我哋近排提醒朋友：先睇流動性同目標年期，再決定動唔動。",
            "你而家較多關注保值，定係增長？",
        )
    if re.search(r"大灣區|粵港澳|內地政策|國務院|人行|人民幣|兩會|發改委|部委|白皮書", t) or (
        pillar == "china"
    ):
        return (
            "內地政策一有新風向，跨境業務同家庭安排往往會跟住調整；"
            "我覺得值得留意嘅唔係標題本身，而係佢對你哋往來內地嘅節奏有冇實質影響。",
            "你哋近排業務／家人計劃有冇因為政策消息而改過部署？",
        )
    if re.search(r"醫療|醫院|健康|疫情|流感|疫苗", t):
        return (
            "健康議題一上新聞，好多家庭先驚覺「備用方案」其實未齊；"
            "我覺得提前傾清楚照顧同開支安排，往往比事到臨頭先驚有用。",
            "你哋屋企近排有冇特別關注健康／照顧方面嘅安排？",
        )
    if re.search(r"教育|學校|大學|學費|子女", t):
        return (
            "教育同子女安排愈早傾愈主動，等新聞催谷先部署往往會趕。",
            "你哋屋企而家最關心升學，定係生活節奏同開支平衡？",
        )
    if re.search(r"晤|外訪|外長|雙邊|建交|峰會|外交", t):
        return (
            "外交動態好多時係氣氛指標多過即時影響生活；"
            "不過外圍關係一變，貿易同投資情緒有時會跟住郁，值得輕輕記一筆。",
            "你平時會追呢類國際消息，定係多數睇完就算？",
        )
    if re.search(r"戰爭|衝突|制裁|地緣|導彈|停火", t):
        return (
            "外圍一不穩定，市場同情緒都會放大；"
            "我反而覺得平時備好現金流同應急安排，先至唔會被突發消息追住走。",
            "你近排對呢類國際消息敏感，定係多數當背景音？",
        )
    if pillar == "finance":
        return (
            "財經新聞一密，最易令人覺得一定要即刻做決定；"
            "我嘅角度係：先問呢則消息有冇改到你原本嘅時間表同風險承受，冇就唔使被帶節奏。",
            "你睇完會調整部署，定係暫時只係記低觀察？",
        )
    # society default — still give a view
    return (
        "呢類本地／國際消息一出，通常反映社會氣氛同生活節奏正在變；"
        "我覺得值得一問嘅係：佢對你日常安排有冇實質影響，定係純粹大家都喺度傾。",
        "你身邊朋友討論得多，定係大家其實都幾平淡睇？",
    )


def whatsapp_opener(title: str, pillar: str) -> str:
    """Cantonese WhatsApp icebreaker with a clear viewpoint + soft question."""
    short = _short_title(title)
    view, ask = _opener_angle(title, pillar)
    return (
        f"嗨！早晨🙂 今日睇到「{short}」。\n\n"
        f"{view}\n\n"
        f"想聽下你點睇—{ask}"
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


@st.cache_data(ttl=20 * 60, show_spinner=False)
def fetch_daily_headlines(limit: int = 5, _cache_ver: int = 4) -> dict[str, Any]:
    """Return up to 5 headlines across 3 pillars. Cached ~20 minutes.

    `_cache_ver` busts stale Streamlit caches after deploy.
    """
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
        "pillars": {
            "society": sum(1 for x in items if x.get("pillar") == "society"),
            "finance": sum(1 for x in items if x.get("pillar") == "finance"),
            "china": sum(1 for x in items if x.get("pillar") == "china"),
        },
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
    font-size: 0.84rem; line-height: 1.5; color: #374151; margin-bottom: 8px;
    white-space: pre-wrap; word-break: break-word;
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
    """Homepage block: 今日重點新聞 — branded briefing panel + WhatsApp angles."""
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
    # Longer openers (viewpoint + question) need more vertical room
    height = 110 + (210 * len(items))
    components.html(panel, height=min(height, 1200), scrolling=True)
