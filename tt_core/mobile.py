"""iPhone / iPad helpers: device detect, PWA meta, install guidance."""

from __future__ import annotations

import json

import streamlit as st
import streamlit.components.v1 as components


def _static_icon_data_uri(filename: str) -> str:
    """Load icon bytes from repo static/ — never rely on Cloud-cached branding helpers."""
    import base64
    from pathlib import Path

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

    favicon = _static_icon_data_uri("app_icon_32.png") or _static_icon_data_uri(
        "app_icon_48.png"
    )
    icon = (
        _static_icon_data_uri("app_icon_180.png")
        or _static_icon_data_uri("app_icon_192.png")
        or _static_icon_data_uri("ace_team_logo.jpg")
    )
    icon_big = (
        _static_icon_data_uri("app_icon_512.png")
        or _static_icon_data_uri("app_icon_192.png")
        or icon
    )
    # Last resort: branding helper (may be stale on Cloud)
    if not icon:
        try:
            import tt_core.branding as b

            fn = getattr(b, "icon_data_uri", None)
            if callable(fn):
                icon = fn(180) or ""
                icon_big = fn(512) or icon
        except Exception:
            pass
    favicon = favicon or icon
    return name, system, favicon, icon, icon_big


def is_mobile() -> bool:
    """Best-effort mobile/tablet detect from request User-Agent."""
    try:
        ua = (st.context.headers.get("User-Agent") or "") if hasattr(st, "context") else ""
    except Exception:
        ua = ""
    ua_l = ua.lower()
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


def is_ios() -> bool:
    try:
        ua = (st.context.headers.get("User-Agent") or "") if hasattr(st, "context") else ""
    except Exception:
        ua = ""
    ua_l = ua.lower()
    return any(k in ua_l for k in ("iphone", "ipad", "ipod"))


def inject_pwa_head() -> None:
    """
    Inject iOS / PWA meta tags into <head> so Safari Add to Home Screen
    opens as a standalone app (no browser chrome).
    """
    brand_name, brand_system, favicon, icon, icon_big = _brand_bits()
    icon_big = icon_big or icon
    if not icon:
        return

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
    favicon_js = json.dumps(favicon or icon)
    icon_js = json.dumps(icon)
    icon_big_js = json.dumps(icon_big)
    brand_js = json.dumps(brand_name)
    manifest_js = json.dumps(manifest)

    components.html(
        f"""
<!DOCTYPE html>
<html><head></head><body>
<script>
(function () {{
  const doc = window.parent.document;
  const head = doc.head || doc.getElementsByTagName('head')[0];
  if (!head) return;

  const favicon = {favicon_js};
  const icon = {icon_js};
  const iconBig = {icon_big_js};
  const brand = {brand_js};
  const VERSION = 'ace-v4';
  const already = head.getAttribute('data-tt-pwa') === VERSION;

  function upsertMeta(attr, key, value) {{
    let el = head.querySelector('meta[' + attr + '="' + key + '"]');
    if (!el) {{
      el = doc.createElement('meta');
      el.setAttribute(attr, key);
      head.appendChild(el);
    }}
    el.setAttribute('content', value);
  }}

  function isAceHref(href) {{
    return typeof href === 'string' && href.indexOf('data:image') === 0;
  }}

  function hasCrownOrStale() {{
    const links = head.querySelectorAll(
      'link[rel="icon"], link[rel="shortcut icon"], link[rel="apple-touch-icon"], link[rel="apple-touch-icon-precomposed"]'
    );
    if (!links.length) return true;
    for (let i = 0; i < links.length; i++) {{
      const href = links[i].getAttribute('href') || '';
      if (!isAceHref(href)) return true;
      if (/streamlit|favicon\\.png|favicon\\.ico|emoji/i.test(href)) return true;
    }}
    return false;
  }}

  function applyFavicon() {{
    // Remove Streamlit default crown / stale icons, then set ACE TEAM mark
    head.querySelectorAll(
      'link[rel="icon"], link[rel="shortcut icon"], link[rel="apple-touch-icon"], link[rel="apple-touch-icon-precomposed"]'
    ).forEach(function (el) {{
      try {{ el.parentNode.removeChild(el); }} catch (e) {{}}
    }});

    function add(rel, href, sizes, type) {{
      const el = doc.createElement('link');
      el.setAttribute('rel', rel);
      if (sizes) el.setAttribute('sizes', sizes);
      if (type) el.setAttribute('type', type);
      el.setAttribute('href', href);
      el.setAttribute('data-tt-icon', VERSION);
      head.appendChild(el);
    }}
    add('icon', favicon, '32x32', 'image/png');
    add('shortcut icon', favicon, null, 'image/png');
    add('icon', icon, '180x180', 'image/png');
    add('icon', iconBig, '512x512', 'image/png');
    add('apple-touch-icon', icon, '180x180', 'image/png');
    add('apple-touch-icon-precomposed', icon, '180x180', 'image/png');
  }}

  upsertMeta('name', 'viewport',
    'width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover, user-scalable=no');
  upsertMeta('name', 'apple-mobile-web-app-capable', 'yes');
  upsertMeta('name', 'mobile-web-app-capable', 'yes');
  upsertMeta('name', 'apple-mobile-web-app-status-bar-style', 'black-translucent');
  upsertMeta('name', 'apple-mobile-web-app-title', brand);
  upsertMeta('name', 'application-name', brand);
  upsertMeta('name', 'theme-color', '#0A0D14');

  applyFavicon();
  head.setAttribute('data-tt-pwa', VERSION);

  const manifest = {manifest_js};
  const blob = new Blob([JSON.stringify(manifest)], {{ type: 'application/manifest+json' }});
  const url = URL.createObjectURL(blob);
  let link = head.querySelector('link[rel="manifest"]');
  if (!link) {{
    link = doc.createElement('link');
    link.rel = 'manifest';
    head.appendChild(link);
  }}
  link.href = url;

  // Already wired this session — do not stack observers/timers
  if (already) return;

  // Streamlit often re-injects its crown favicon after load — keep replacing it
  const obs = new MutationObserver(function () {{
    if (hasCrownOrStale()) applyFavicon();
  }});
  try {{ obs.observe(head, {{ childList: true, subtree: true }}); }} catch (e) {{}}
  let n = 0;
  const timer = setInterval(function () {{
    if (hasCrownOrStale()) applyFavicon();
    n += 1;
    if (n >= 40) clearInterval(timer);
  }}, 250);

  const standalone = window.parent.navigator.standalone === true
    || window.parent.matchMedia('(display-mode: standalone)').matches;
  if (standalone) {{
    doc.documentElement.setAttribute('data-tt-standalone', '1');
  }}
}})();
</script>
</body></html>
        """,
        height=0,
        width=0,
    )


def render_install_guide(*, compact: bool = False) -> None:
    """Safari Add to Home Screen instructions."""
    brand_name, _, _, _, _ = _brand_bits()
    body_zh = (
        "1. 用 **Safari** 打開本網站（唔好用 Chrome）\n"
        "2. 撳底部分享按鈕\n"
        "3. 揀 **加到主畫面 / Add to Home Screen**\n"
        f"4. 名稱用 **{brand_name}** → 新增\n"
        "5. 之後喺主畫面撳圖示，就會好似 App 咁開（全螢幕）\n"
    )
    if compact:
        with st.expander("加到 iPhone 主畫面（變 App）", expanded=False):
            st.markdown(body_zh)
            st.caption("iPad 同樣步驟。Android：Chrome 選單 → 安裝應用程式。")
    else:
        st.markdown("### 加到 iPhone 主畫面（變 App）")
        st.markdown(body_zh)
        st.info(f"一次加好，成隊同事主畫面都有 {brand_name}，打卡會快好多。")


def mobile_top_nav(menu_items: list[str], current: str | None = None) -> str:
    """Compact top navigation for phones (avoids opening sidebar every time)."""
    idx = 0
    if current and current in menu_items:
        idx = menu_items.index(current)
    return st.selectbox(
        "功能選單",
        menu_items,
        index=idx,
        key="mobile_top_nav",
        label_visibility="collapsed",
    )
