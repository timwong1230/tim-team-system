"""iPhone / iPad helpers: device detect, PWA meta, install guidance."""

from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

# Public icon URLs — iOS Add to Home Screen often re-fetches icons WITHOUT
# Streamlit auth cookies, so same-origin /app/static can 303 to login and
# fall back to the Streamlit crown. jsDelivr serves repo files anonymously.
_REPO_CDN = "https://cdn.jsdelivr.net/gh/timwong1230/tim-team-system@main/static"
# Use filenames already present on main when possible so CDN works immediately
_ICON_PUBLIC_180 = f"{_REPO_CDN}/app_icon_180.png"
_ICON_PUBLIC_192 = f"{_REPO_CDN}/app_icon_192.png"
_ICON_PUBLIC_512 = f"{_REPO_CDN}/app_icon_512.png"
_ICON_PUBLIC_32 = f"{_REPO_CDN}/app_icon_32.png"

# Same-origin paths when server.enableStaticServing=true
_ICON_LOCAL_180 = "/app/static/apple-touch-icon.png"
_ICON_LOCAL_192 = "/app/static/android-chrome-192.png"
_ICON_LOCAL_512 = "/app/static/android-chrome-512.png"
_ICON_LOCAL_32 = "/app/static/app_icon_32.png"


def _static_icon_data_uri(filename: str) -> str:
    """Load icon bytes from repo static/ — never rely on Cloud-cached branding helpers."""
    import base64

    path = Path(__file__).resolve().parents[1] / "static" / filename
    if not path.exists():
        return ""
    mime = "image/jpeg" if path.suffix.lower() in {".jpg", ".jpeg"} else "image/png"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


def _brand_bits():
    """Lazy brand/icon load so a stale branding.py cannot break login."""
    name = "TIM TEAM"
    system = "TIM TEAM SYSTEM"
    try:
        import tt_core.branding as b

        name = getattr(b, "BRAND_NAME", name) or name
        system = getattr(b, "BRAND_SYSTEM", system) or system
    except Exception:
        pass

    # Prefer HTTP(S) URLs for iOS home-screen icons (data: URIs are ignored by Safari)
    favicon = _ICON_PUBLIC_32
    icon = _ICON_PUBLIC_180
    icon_big = _ICON_PUBLIC_512
    # Local static paths as extras (authenticated session / desktop)
    icon_local = _ICON_LOCAL_180 if (Path(__file__).resolve().parents[1] / "static" / "apple-touch-icon.png").exists() else ""
    icon_local_big = _ICON_LOCAL_512 if (Path(__file__).resolve().parents[1] / "static" / "android-chrome-512.png").exists() else ""
    # data URI last-resort for tab favicon when offline / CDN blocked
    data_icon = (
        _static_icon_data_uri("apple-touch-icon.png")
        or _static_icon_data_uri("app_icon_180.png")
        or _static_icon_data_uri("ace_team_logo.jpg")
    )
    return name, system, favicon, icon, icon_big, icon_local, icon_local_big, data_icon


def _user_agent() -> str:
    try:
        return (st.context.headers.get("User-Agent") or "") if hasattr(st, "context") else ""
    except Exception:
        return ""


def is_mobile() -> bool:
    """Best-effort mobile/tablet detect from request User-Agent."""
    ua_l = _user_agent().lower()
    return any(
        k in ua_l
        for k in (
            "iphone",
            "ipad",
            "ipod",
            "android",
            "mobile",
            "crios",
            "fxios",
        )
    )


def is_tablet() -> bool:
    """iPad / Android tablet — prefer left sidebar nav over phone top selectbox."""
    ua_l = _user_agent().lower()
    if "ipad" in ua_l or "tablet" in ua_l:
        return True
    # Android tablets often omit "mobile" in UA
    if "android" in ua_l and "mobile" not in ua_l:
        return True
    return False


def is_phone() -> bool:
    """True phones only — not iPad/tablet."""
    return bool(is_mobile() and not is_tablet())


def is_ios() -> bool:
    ua_l = _user_agent().lower()
    return any(k in ua_l for k in ("iphone", "ipad", "ipod"))


def inject_pwa_head() -> None:
    """
    Inject iOS / PWA meta + apple-touch-icon into the real document <head>.

    Uses st.html(unsafe_allow_javascript=True) so the script runs in the main
    page (not a sandboxed iframe). components.v1.html cannot reliably rewrite
    parent <head> on iPad Safari — that left users stuck with the Streamlit crown.
    """
    (
        brand_name,
        brand_system,
        favicon,
        icon,
        icon_big,
        icon_local,
        icon_local_big,
        data_icon,
    ) = _brand_bits()

    manifest = {
        "name": brand_system,
        "short_name": brand_name,
        "start_url": ".",
        "display": "standalone",
        "background_color": "#0A0D14",
        "theme_color": "#0A0D14",
        "lang": "zh-Hant",
        "icons": [
            {
                "src": icon,
                "sizes": "180x180",
                "type": "image/png",
                "purpose": "any",
            },
            {
                "src": _ICON_PUBLIC_192,
                "sizes": "192x192",
                "type": "image/png",
                "purpose": "any maskable",
            },
            {
                "src": icon_big,
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "any maskable",
            },
        ],
    }

    payload = {
        "favicon": favicon,
        "icon": icon,
        "iconBig": icon_big,
        "iconLocal": icon_local,
        "iconLocalBig": icon_local_big,
        "dataIcon": data_icon,
        "brand": brand_name,
        "manifest": manifest,
        # Bump when icon wiring changes — forces re-inject over cached crown links
        "version": "ace-v6",
    }
    payload_js = json.dumps(payload)

    script = f"""
<script>
(function () {{
  var P = {payload_js};
  var doc = document;
  var head = doc.head || doc.getElementsByTagName('head')[0];
  if (!head) return;

  var VERSION = P.version;
  var already = head.getAttribute('data-tt-pwa') === VERSION;

  function upsertMeta(attr, key, value, media) {{
    var sel = 'meta[' + attr + '="' + key + '"]';
    if (media) {{
      sel += '[media="' + media + '"]';
    }} else {{
      sel += ':not([media])';
    }}
    var el = head.querySelector(sel);
    if (!el) {{
      el = doc.createElement('meta');
      el.setAttribute(attr, key);
      if (media) el.setAttribute('media', media);
      head.appendChild(el);
    }}
    el.setAttribute('content', value);
  }}

  function isOurs(href) {{
    if (!href) return false;
    if (href.indexOf('data:image') === 0) return true;
    if (href.indexOf('apple-touch-icon') !== -1) return true;
    if (href.indexOf('app_icon_') !== -1) return true;
    if (href.indexOf('android-chrome') !== -1) return true;
    if (href.indexOf('tim-team-system') !== -1 && href.indexOf('/static/') !== -1) return true;
    if (href.indexOf('/app/static/') === 0) return true;
    return false;
  }}

  function hasCrownOrStale() {{
    var links = head.querySelectorAll(
      'link[rel="icon"], link[rel="shortcut icon"], link[rel="apple-touch-icon"], link[rel="apple-touch-icon-precomposed"]'
    );
    if (!links.length) return true;
    for (var i = 0; i < links.length; i++) {{
      var href = links[i].getAttribute('href') || '';
      if (!isOurs(href)) return true;
      if (/streamlit|favicon\\.png|favicon\\.ico/i.test(href) && href.indexOf('app_icon') === -1) return true;
    }}
    // Must have at least one apple-touch-icon for iOS home screen
    if (!head.querySelector('link[rel="apple-touch-icon"]')) return true;
    return false;
  }}

  function applyFavicon() {{
    head.querySelectorAll(
      'link[rel="icon"], link[rel="shortcut icon"], link[rel="apple-touch-icon"], link[rel="apple-touch-icon-precomposed"]'
    ).forEach(function (el) {{
      try {{ el.parentNode.removeChild(el); }} catch (e) {{}}
    }});

    function add(rel, href, sizes, type) {{
      if (!href) return;
      var el = doc.createElement('link');
      el.setAttribute('rel', rel);
      if (sizes) el.setAttribute('sizes', sizes);
      if (type) el.setAttribute('type', type);
      el.setAttribute('href', href);
      el.setAttribute('data-tt-icon', VERSION);
      head.appendChild(el);
    }}

    // apple-touch-icon MUST be public HTTPS only.
    // iOS "Add to Home Screen" fetches WITHOUT Streamlit cookies;
    // /app/static often 303→login and Safari falls back to the Streamlit crown.
    add('apple-touch-icon', P.icon, '180x180', 'image/png');
    add('apple-touch-icon-precomposed', P.icon, '180x180', 'image/png');
    // Tab / Android favicons (session may use same-origin extras)
    add('icon', P.favicon, '32x32', 'image/png');
    add('shortcut icon', P.favicon, null, 'image/png');
    add('icon', P.icon, '180x180', 'image/png');
    add('icon', P.iconBig, '512x512', 'image/png');
    if (P.iconLocal) add('icon', P.iconLocal, '180x180', 'image/png');
    if (P.iconLocalBig) add('icon', P.iconLocalBig, '512x512', 'image/png');
    // data URI last for desktop tab when CDN blocked (Safari ignores data: for home screen)
    add('icon', P.dataIcon, '180x180', 'image/png');
  }}

  upsertMeta('name', 'viewport',
    'width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover, user-scalable=no');
  upsertMeta('name', 'apple-mobile-web-app-capable', 'yes');
  upsertMeta('name', 'mobile-web-app-capable', 'yes');
  upsertMeta('name', 'apple-mobile-web-app-status-bar-style', 'black-translucent');
  upsertMeta('name', 'apple-mobile-web-app-title', P.brand);
  upsertMeta('name', 'application-name', P.brand);
  // Match phone light/dark so status bar + PWA chrome follow system
  upsertMeta('name', 'theme-color', '#F3F1EB', '(prefers-color-scheme: light)');
  upsertMeta('name', 'theme-color', '#0F1419', '(prefers-color-scheme: dark)');
  // Fallback for browsers that ignore media on theme-color
  upsertMeta('name', 'theme-color', '#0F1419');

  // Help share sheet / scrapers (Streamlit Cloud may still override)
  upsertMeta('property', 'og:title', P.brand);
  upsertMeta('property', 'og:image', P.iconBig);

  applyFavicon();
  try {{ doc.title = P.brand; }} catch (e) {{}}
  head.setAttribute('data-tt-pwa', VERSION);

  var blob = new Blob([JSON.stringify(P.manifest)], {{ type: 'application/manifest+json' }});
  var url = URL.createObjectURL(blob);
  var link = head.querySelector('link[rel="manifest"]');
  if (!link) {{
    link = doc.createElement('link');
    link.rel = 'manifest';
    head.appendChild(link);
  }}
  link.href = url;

  if (already) return;

  var obs = new MutationObserver(function () {{
    if (hasCrownOrStale()) applyFavicon();
  }});
  try {{ obs.observe(head, {{ childList: true, subtree: true }}); }} catch (e) {{}}
  var n = 0;
  var timer = setInterval(function () {{
    if (hasCrownOrStale()) applyFavicon();
    n += 1;
    if (n >= 60) clearInterval(timer);
  }}, 250);

  var standalone = (window.navigator.standalone === true)
    || window.matchMedia('(display-mode: standalone)').matches;
  if (standalone) {{
    doc.documentElement.setAttribute('data-tt-standalone', '1');
  }}
}})();
</script>
"""

    # st.html runs in the main document (not iframe) — required for iPad Safari
    try:
        st.html(script, unsafe_allow_javascript=True)
        return
    except Exception:
        pass

    # Fallback for older Streamlit: iframe inject (desktop only reliability)
    try:
        import streamlit.components.v1 as components

        components.html(
            f"<!DOCTYPE html><html><head></head><body>{script.replace('var doc = document;', 'var doc = window.parent.document;')}</body></html>",
            height=0,
            width=0,
        )
    except Exception:
        pass


def render_install_guide(*, compact: bool = False) -> None:
    """Safari Add to Home Screen instructions."""
    brand_name, _, _, _, _, _, _, _ = _brand_bits()
    body_zh = (
        "1. 如果主畫面已有舊圖示（Streamlit 皇冠）：**先長按刪除**\n"
        "2. 用 **Safari** 打開本網站（唔好用 Chrome）\n"
        "3. 撳底部分享按鈕 → **加到主畫面 / Add to Home Screen**\n"
        f"4. 名稱改成 **{brand_name}**（如果顯示 Streamlit）→ 新增\n"
        "5. 正確圖示係金 **ACE TEAM** 牌面（唔係皇冠）\n"
        "6. 之後喺主畫面撳圖示，就會好似 App 咁開（全螢幕）\n"
        "\n"
        "註：iPhone **唔會自動更新**舊 bookmark 圖示，一定要刪舊再加新。\n"
    )
    if compact:
        with st.expander("加到 iPhone 主畫面（變 App）", expanded=False):
            st.markdown(body_zh)
            st.caption("iPad 同樣步驟。Android：Chrome 選單 → 安裝應用程式。")
    else:
        st.markdown("### 加到 iPhone 主畫面（變 App）")
        st.markdown(body_zh)
        st.info(f"一次加好，成隊同事主畫面都有 {brand_name}，打卡會快好多。")


def _bump_phone_nav_popover() -> int:
    """Remount popover with a new key so it starts closed after a pick."""
    n = int(st.session_state.get("phone_top_nav_pop_nonce") or 0) + 1
    st.session_state["phone_top_nav_pop_nonce"] = n
    return n


def mobile_top_nav(menu_items: list[str], current: str | None = None) -> str:
    """Compact top navigation for phones (avoids opening sidebar every time).

    Uses a popover + buttons — never a selectbox/input — so iPhone does not
    show the keyboard or Cut/Copy on the menu label.

    Programmatic jumps (Home CTAs via ``go_menu``) set ``_nav_pending`` for a
    one-shot sync into ``mobile_top_nav`` *before* the popover is rendered.
    We must NOT re-apply ``_menu_choice`` on every run — that locks users on
    the page they jumped to.

    After a menu pick (or pending jump), bump ``phone_top_nav_pop_nonce`` so
    the popover remounts closed instead of staying open across the rerun.
    """
    valid = list(menu_items or [])
    if not valid:
        return current or ""

    pending = st.session_state.pop("_nav_pending", None)
    existing = st.session_state.get("mobile_top_nav")
    if pending in valid:
        st.session_state["mobile_top_nav"] = pending
        _bump_phone_nav_popover()
    elif existing not in valid:
        fallback = current if current in valid else valid[0]
        st.session_state["mobile_top_nav"] = fallback

    current_label = str(st.session_state.get("mobile_top_nav") or valid[0])
    pop_nonce = int(st.session_state.get("phone_top_nav_pop_nonce") or 0)

    # Popover trigger is a real button (no text input → no iOS keyboard/copy).
    # Key includes nonce so a pick remounts the popover in the closed state.
    with st.popover(
        current_label,
        use_container_width=True,
        key=f"phone_top_nav_pop_{pop_nonce}",
    ):
        for i, item in enumerate(valid):
            if st.button(
                item,
                key=f"phone_top_nav_btn_{pop_nonce}_{i}",
                use_container_width=True,
                type="primary" if item == current_label else "secondary",
            ):
                st.session_state["mobile_top_nav"] = item
                _bump_phone_nav_popover()
                st.rerun()

    return str(st.session_state.get("mobile_top_nav") or current_label)


def go_menu(label: str, **extra) -> None:
    """Navigate to a menu page; phone top nav syncs on the next run.

    Only write ``_menu_choice`` + one-shot ``_nav_pending`` here. Do not assign
    widget keys that may already exist this run (legacy selectbox path raised
    ``StreamlitWidgetAlreadyInstantiatedError``). ``mobile_top_nav()`` applies
    ``_nav_pending`` before rendering the popover on the following rerun.
    """
    st.session_state["_menu_choice"] = label
    st.session_state["_nav_pending"] = label
    for k, v in extra.items():
        st.session_state[k] = v
    st.rerun()
