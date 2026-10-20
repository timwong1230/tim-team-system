"""今日重點新聞 — 每日鎖定 5 則重中之重（社會／財經／內地），WhatsApp openers."""

from __future__ import annotations

import html
import json
import os
import re
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

import streamlit as st

# Keep home snappy after login — never wait long on slow RSS hosts
_FEED_TIMEOUT_SEC = float(os.environ.get("TIM_TEAM_NEWS_FEED_TIMEOUT", "3"))
_FETCH_BUDGET_SEC = float(os.environ.get("TIM_TEAM_NEWS_BUDGET_SEC", "4.5"))
_HK_TZ = ZoneInfo("Asia/Hong_Kong")
_PIN_DIR = Path(os.environ.get("TIM_TEAM_CACHE_DIR", "/tmp/tim_team_cache"))
_SETTINGS_KEY_PREFIX = "daily_news_pack_"

# pillar → display label
PILLAR_LABELS = {
    "society": "社會問題",
    "finance": "金融經濟",
    "china": "內地政經",
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
# Drop entertainment / sports / lifestyle fluff — not「重中之重」
_NOISE_KW = re.compile(
    r"球賽|足球|籃球|網球|棒球|演唱會|娛樂|明星|戀情|戀愛|綜藝|電影票房|奧運|"
    r"選美|八卦|寵物|食評|食通街|旅遊推介|穿搭|時裝周|劇集|綜藝節目|"
    r"concert|celebrity|gossip|premier league|nba",
    re.I,
)
# Must-have theme signals for「重中之重」scoring
_PRIORITY_SOCIETY = re.compile(
    r"房屋|公屋|居屋|樓價|租金|劏房|醫療|醫院|公營醫療|教育|學費|學校|"
    r"就業|失業|最低工資|貧富|綜援|福利|民生|立法會|特首|特區政府|公務員|"
    r"港鐵|交通|重大意外|火災|爆炸|災難|颱風|暴雨|停電|食水|治安|毒品|"
    r"虐兒|性暴力|人口|移民|人才|通關|口岸|疫情|流感|疫苗|強制檢測|"
    r"退休|生果金|強積金|安老|貧窮|基層|工潮|罷工|裁員|"
    r"戰爭|衝突|制裁|地緣|停火|核|導彈",
    re.I,
)
_PRIORITY_FINANCE = re.compile(
    r"加息|減息|聯儲|美聯儲|利率|息口|恒指|港股|美股|樓市|成交|"
    r"GDP|通脹|通縮|財赤|預算案|財政預算|稅制|關稅|貿易戰|貿易|"
    r"銀行|保險業|匯控|中移動|騰訊|阿里|人行|人民幣|港元|聯繫匯率|"
    r"就業數據|零售銷售|出口|進口|IPO|債市|違約|破產|裁員|盈利警告|"
    r"金管局|證監|聯交所|股市|匯市|油價|金價",
    re.I,
)
_PRIORITY_CHINA = re.compile(
    r"國務院|中央|政治局|兩會|習近平|總理|李強|人行|人民幣|發改委|"
    r"商務部|證監會|監管|刺激|穩增長|地方債|房地產調控|大灣區|粵港澳|"
    r"國安|白皮書|條例|法規|部委|省委|市委|中央經濟工作|改革|"
    r"內地政策|中美|台海|解放軍",
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


def _hk_today() -> str:
    """Hong Kong calendar date — daily pack key (全日同一組新聞)."""
    return datetime.now(_HK_TZ).strftime("%Y-%m-%d")


def _fetch_feed(pillar: str, source: str, url: str, *, limit: int = 12) -> list[dict[str, Any]]:
    req = Request(
        url,
        headers={
            "User-Agent": _UA,
            "Accept": "application/rss+xml, application/xml, text/xml, */*",
        },
    )
    with urlopen(req, timeout=_FEED_TIMEOUT_SEC) as resp:
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
        # Entertainment/sports never make the daily 5
        if _NOISE_KW.search(title):
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


def _title_key(title: str) -> str:
    return re.sub(r"\s+", "", str(title or "")).lower()


def _importance_score(row: dict[str, Any], *, now_ts: float | None = None) -> float:
    """Score「重中之重」— theme priority first, recency only as tie-break."""
    title = str(row.get("title") or "")
    pillar = str(row.get("pillar") or "society")
    score = 0.0

    hit_s = bool(_PRIORITY_SOCIETY.search(title))
    hit_f = bool(_PRIORITY_FINANCE.search(title))
    hit_c = bool(_PRIORITY_CHINA.search(title))

    if pillar == "society" and hit_s:
        score += 55
    elif pillar == "finance" and hit_f:
        score += 55
    elif pillar == "china" and hit_c:
        score += 55

    # Cross-pillar substance still counts
    if hit_f:
        score += 18
    if hit_c:
        score += 18
    if hit_s:
        score += 12

    if _has_cjk(title):
        score += 6
    if _NOISE_KW.search(title):
        score -= 50

    # Recency: at most ~12 pts — never outrank a real priority story
    ts = float(row.get("ts") or 0.0)
    if ts > 0:
        now = now_ts if now_ts is not None else datetime.now(timezone.utc).timestamp()
        age_h = max(0.0, (now - ts) / 3600.0)
        score += max(0.0, 12.0 - age_h / 4.0)

    return score


def _attach_wa(row: dict[str, Any]) -> dict[str, Any]:
    pillar = row.get("pillar") or "society"
    out = dict(row)
    out["wa_text"] = whatsapp_opener(out["title"], pillar)
    out["wa_url"] = wa_opener_url(out["title"], pillar)
    out["pillar_label"] = PILLAR_LABELS.get(pillar, "社會問題")
    return out


def _pick_balanced(items: list[dict[str, Any]], *, limit: int = 5) -> list[dict[str, Any]]:
    """Pick up to 5「重中之重」: 2 社會 + 2 財經 + 1 內地, ranked by importance.

    Backfill by global importance if a pillar is thin. Skips low-substance fluff
    when higher-scored alternatives exist.
    """
    return _pick_priority(items, limit=limit)


def _pick_priority(items: list[dict[str, Any]], *, limit: int = 5) -> list[dict[str, Any]]:
    now_ts = datetime.now(timezone.utc).timestamp()
    by: dict[str, list[dict[str, Any]]] = {"society": [], "finance": [], "china": []}
    seen: set[str] = set()

    scored: list[tuple[float, dict[str, Any]]] = []
    for row in items:
        key = _title_key(row.get("title") or "")
        if not key or key in seen:
            continue
        seen.add(key)
        p = row.get("pillar") or "society"
        if p not in by:
            p = "society"
        enriched = dict(row)
        enriched["pillar"] = p
        enriched["_score"] = _importance_score(enriched, now_ts=now_ts)
        by[p].append(enriched)
        scored.append((float(enriched["_score"]), enriched))

    for p in by:
        by[p].sort(key=lambda r: (float(r.get("_score") or 0), float(r.get("ts") or 0)), reverse=True)
    scored.sort(key=lambda x: (x[0], float(x[1].get("ts") or 0)), reverse=True)

    quotas = {"society": 2, "finance": 2, "china": 1}
    picked: list[dict[str, Any]] = []
    used: set[str] = set()

    def _take(pillar: str, n: int, *, min_score: float = 20.0) -> None:
        for row in by.get(pillar, []):
            if sum(1 for x in picked if x["pillar"] == pillar) >= n:
                break
            # Prefer substance; allow softer fill only if pillar otherwise empty
            if float(row.get("_score") or 0) < min_score and any(
                float(r.get("_score") or 0) >= min_score for r in by.get(pillar, [])
            ):
                continue
            k = _title_key(row["title"])
            if k in used:
                continue
            used.add(k)
            picked.append(row)

    for pillar, n in quotas.items():
        _take(pillar, n, min_score=20.0)
        # If still empty for this pillar, take best available regardless
        if not any(x["pillar"] == pillar for x in picked):
            _take(pillar, 1, min_score=-999.0)

    if len(picked) < limit:
        for _score, row in scored:
            if len(picked) >= limit:
                break
            k = _title_key(row["title"])
            if k in used:
                continue
            used.add(k)
            picked.append(row)

    # Stable display order: society → finance → china, then score within
    order = {"society": 0, "finance": 1, "china": 2}
    picked.sort(
        key=lambda r: (
            order.get(str(r.get("pillar")), 9),
            -float(r.get("_score") or 0),
            -float(r.get("ts") or 0),
        )
    )

    out = [_attach_wa(r) for r in picked[:limit]]
    for r in out:
        r.pop("_score", None)
    return out


def _pin_path(day: str) -> Path:
    return _PIN_DIR / f"daily_news_{day}.json"


def _load_daily_pin(day: str) -> dict[str, Any] | None:
    """Load today's locked pack from disk (and best-effort system_settings)."""
    path = _pin_path(day)
    try:
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            items = data.get("items") or []
            if data.get("day") == day and isinstance(items, list) and items:
                return data
    except Exception:
        pass
    # Cross-replica best effort via Sheets settings
    try:
        from tt_core.coach_tim import _settings_get

        raw = _settings_get(f"{_SETTINGS_KEY_PREFIX}{day}", "")
        if raw:
            data = json.loads(raw)
            items = data.get("items") or []
            if data.get("day") == day and isinstance(items, list) and items:
                # Mirror to disk for faster subsequent reads on this worker
                try:
                    _PIN_DIR.mkdir(parents=True, exist_ok=True)
                    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
                except Exception:
                    pass
                return data
    except Exception:
        pass
    return None


def _save_daily_pin(day: str, payload: dict[str, Any]) -> None:
    """Persist today's pack so every login sees the same 5 headlines."""
    payload = dict(payload)
    payload["day"] = day
    try:
        _PIN_DIR.mkdir(parents=True, exist_ok=True)
        _pin_path(day).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass
    try:
        from tt_core.coach_tim import _settings_set

        # Keep payload compact for Sheets cell
        slim_items = []
        for row in payload.get("items") or []:
            slim_items.append(
                {
                    "title": row.get("title"),
                    "url": row.get("url"),
                    "source": row.get("source"),
                    "pillar": row.get("pillar"),
                    "pillar_label": row.get("pillar_label"),
                    "published": row.get("published"),
                    "ts": row.get("ts"),
                    "wa_text": row.get("wa_text"),
                    "wa_url": row.get("wa_url"),
                }
            )
        slim = {
            "day": day,
            "items": slim_items,
            "fetched_at": payload.get("fetched_at"),
            "ok": payload.get("ok"),
            "pillars": payload.get("pillars"),
            "pinned": True,
        }
        _settings_set(f"{_SETTINGS_KEY_PREFIX}{day}", json.dumps(slim, ensure_ascii=False))
    except Exception:
        pass


def _fetch_feed_safe(pillar: str, source: str, url: str) -> tuple[list[dict[str, Any]], str | None]:
    try:
        return _fetch_feed(pillar, source, url, limit=8), None
    except (HTTPError, URLError, ET.ParseError, TimeoutError, OSError) as e:
        return [], f"{source}:{type(e).__name__}"
    except Exception as e:
        return [], f"{source}:{type(e).__name__}"


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def fetch_daily_headlines(
    limit: int = 5,
    day: str = "",
    _cache_ver: int = 7,
) -> dict[str, Any]:
    """Return today's locked 5「重中之重」headlines (society / finance / china).

    ``day`` is the Hong Kong calendar date. The first successful pick for that
    day is pinned (disk + system_settings) so every login sees the same five —
    not a reshuffle on each cold start / RSS race.
    """
    import time

    day = (day or _hk_today()).strip()
    pinned = _load_daily_pin(day)
    if pinned and (pinned.get("items") or []):
        items = list(pinned["items"])[:limit]
        # Refresh WA copy in case opener templates changed mid-day
        items = [_attach_wa(r) for r in items]
        return {
            "items": items,
            "fetched_at": str(pinned.get("fetched_at") or ""),
            "errors": list(pinned.get("errors") or []),
            "ok": True,
            "day": day,
            "pinned": True,
            "pillars": {
                "society": sum(1 for x in items if x.get("pillar") == "society"),
                "finance": sum(1 for x in items if x.get("pillar") == "finance"),
                "china": sum(1 for x in items if x.get("pillar") == "china"),
            },
        }

    collected: list[dict[str, Any]] = []
    errors: list[str] = []
    started = time.monotonic()
    budget = max(1.5, _FETCH_BUDGET_SEC)

    with ThreadPoolExecutor(max_workers=min(8, len(_FEEDS))) as pool:
        futures = {
            pool.submit(_fetch_feed_safe, pillar, source, url): source
            for pillar, source, url in _FEEDS
        }
        try:
            for fut in as_completed(futures, timeout=budget):
                rows, err = fut.result()
                if err:
                    errors.append(err)
                elif rows:
                    collected.extend(rows)
                if time.monotonic() - started >= budget:
                    break
        except TimeoutError:
            errors.append("budget:TimeoutError")
        for fut in futures:
            if not fut.done():
                fut.cancel()

    items = _pick_priority(collected, limit=limit)
    payload = {
        "items": items,
        "fetched_at": datetime.now(_HK_TZ).strftime("%Y-%m-%d %H:%M"),
        "errors": errors,
        "ok": bool(items),
        "day": day,
        "pinned": False,
        "pillars": {
            "society": sum(1 for x in items if x.get("pillar") == "society"),
            "finance": sum(1 for x in items if x.get("pillar") == "finance"),
            "china": sum(1 for x in items if x.get("pillar") == "china"),
        },
    }
    if items:
        _save_daily_pin(day, payload)
        payload["pinned"] = True
    return payload


def _news_panel_html(items: list[dict[str, Any]], *, fetched_at: str) -> str:
    """Briefing panel: collapsed headlines; expand for link + WhatsApp angle."""
    rows = []
    for i, row in enumerate(items, start=1):
        title = html.escape(str(row.get("title") or ""))
        url = html.escape(str(row.get("url") or ""), quote=True)
        pillar = html.escape(str(row.get("pillar_label") or row.get("source") or ""))
        wa_text = html.escape(str(row.get("wa_text") or ""))
        wa_url = html.escape(str(row.get("wa_url") or ""), quote=True)
        idx = f"{i:02d}"
        rows.append(
            f'<details class="tt-news-row">'
            f'<summary class="tt-news-sum">'
            f'<span class="tt-news-idx">{idx}</span>'
            f'<div class="tt-news-body">'
            f'<span class="tt-news-src">{pillar}</span>'
            f'<span class="tt-news-title">{title}</span>'
            f'<span class="tt-news-hint">撳開 · 原文連結 + WhatsApp 開話題</span>'
            f"</div>"
            f'<span class="tt-news-chev" aria-hidden="true"></span>'
            f"</summary>"
            f'<div class="tt-news-detail">'
            f'<a class="tt-news-link" href="{url}" target="_blank" rel="noopener noreferrer">睇原文 ↗</a>'
            f'<div class="tt-news-wa">'
            f'<div class="tt-news-wa-label">WhatsApp 開話題</div>'
            f'<div class="tt-news-wa-text">{wa_text}</div>'
            f'<a class="tt-news-wa-btn" href="{wa_url}" target="_blank" rel="noopener noreferrer">開 WhatsApp</a>'
            f"</div>"
            f"</div>"
            f"</details>"
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
    border-radius: 12px;
    background: rgba(255,255,255,0.55);
    border: 1px solid #EEE9DF;
    overflow: hidden;
  }}
  .tt-news-row[open] {{
    background: rgba(255,255,255,0.92);
    border-color: #E2D4A8;
    box-shadow: 0 6px 18px rgba(28, 36, 48, 0.06);
  }}
  .tt-news-sum {{
    display: grid; grid-template-columns: 36px 1fr 18px;
    gap: 10px; align-items: start;
    padding: 12px 10px; cursor: pointer; list-style: none;
  }}
  .tt-news-sum::-webkit-details-marker {{ display: none; }}
  .tt-news-sum::marker {{ content: ""; }}
  .tt-news-idx {{
    font-family: 'Instrument Serif', Georgia, serif;
    font-size: 1.15rem; color: #C5A028; line-height: 1.2;
    padding-top: 2px;
  }}
  .tt-news-body {{ display: flex; flex-direction: column; gap: 5px; min-width: 0; }}
  .tt-news-src {{
    display: inline-block; align-self: flex-start;
    font-size: 0.66rem; letter-spacing: 0.08em; font-weight: 650;
    color: #7A6420; background: #F7F1DE;
    border: 1px solid #E2D4A8; border-radius: 999px;
    padding: 2px 8px; line-height: 1.3;
  }}
  .tt-news-title {{
    font-size: 0.98rem; font-weight: 650; line-height: 1.4;
    color: #1C2430;
  }}
  .tt-news-hint {{
    font-size: 0.7rem; color: #9CA3AF; line-height: 1.3;
  }}
  .tt-news-row[open] .tt-news-hint {{ display: none; }}
  .tt-news-chev {{
    width: 8px; height: 8px; margin-top: 10px;
    border-right: 2px solid #C5A028; border-bottom: 2px solid #C5A028;
    transform: rotate(45deg); transition: transform 0.15s ease;
    justify-self: end;
  }}
  .tt-news-row[open] .tt-news-chev {{
    transform: rotate(225deg); margin-top: 14px;
  }}
  .tt-news-detail {{
    padding: 0 12px 12px 46px;
    display: flex; flex-direction: column; gap: 10px;
  }}
  .tt-news-link {{
    display: inline-block; align-self: flex-start;
    font-size: 0.84rem; font-weight: 650; color: #9A7B1A;
    text-decoration: none; padding: 4px 0;
  }}
  .tt-news-link:hover {{ color: #7A6420; text-decoration: underline; }}
  .tt-news-wa {{
    padding: 10px 12px;
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
    .tt-news-meta, .tt-news-hint {{ color: #9CA3AF; }}
    .tt-news-row {{ background: #121820; border-color: #2F3A48; }}
    .tt-news-row[open] {{ background: #161E28; border-color: #5C4A12; }}
    .tt-news-src {{
      color: #F5E6B8; background: #3A3420; border-color: #5C4A12;
    }}
    .tt-news-idx, .tt-news-link {{ color: #E0C15A; }}
    .tt-news-wa {{ background: #0F1419; border-left-color: #E0C15A; }}
    .tt-news-wa-label {{ color: #E0C15A; }}
    .tt-news-wa-text {{ color: #C5CAD3; }}
    .tt-news-chev {{ border-color: #E0C15A; }}
  }}
</style></head><body>
<div class="tt-news">
  <div class="tt-news-head">
    <div>
      <div class="tt-news-kicker">Morning briefing</div>
      <h2 class="tt-news-title-main">今日重點新聞</h2>
    </div>
    <div class="tt-news-meta">{when}<br/>今日五則重中之重 · 全日不變<br/>社會問題 · 金融經濟 · 內地政經<br/>撳標題展開</div>
  </div>
  <div class="tt-news-list">{body}</div>
</div>
<script>
(function() {{
  var list = document.querySelector('.tt-news-list');
  if (!list) return;
  list.addEventListener('toggle', function(e) {{
    var t = e.target;
    if (!t || t.tagName !== 'DETAILS' || !t.open) return;
    list.querySelectorAll('details.tt-news-row').forEach(function(d) {{
      if (d !== t) d.open = false;
    }});
  }}, true);
}})();
</script>
</body></html>"""


def render_daily_news(*, limit: int = 5) -> None:
    """Homepage block: collapsed headlines; expand for link + WhatsApp angle."""
    import streamlit.components.v1 as components

    day = _hk_today()
    try:
        data = fetch_daily_headlines(limit=limit, day=day)
    except Exception:
        st.caption("新聞暫時載入唔到，稍後自動再試。")
        return

    items = data.get("items") or []
    if not items:
        st.caption("新聞暫時載入唔到，稍後自動再試。")
        if data.get("errors"):
            st.caption("（網絡／RSS 暫時唔穩定）")
        return

    when = str(data.get("fetched_at") or "")
    if data.get("pinned") and day:
        when = f"{day} · 今日鎖定" + (f" · {when}" if when else "")
    panel = _news_panel_html(items, fetched_at=when)
    # Collapsed list is compact; leave room so one expanded row + WA fits
    height = 110 + (78 * len(items)) + 220
    components.html(panel, height=min(height, 920), scrolling=True)
