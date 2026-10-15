"""iPhone / iPad helpers: device detect, PWA meta, install guidance."""

from __future__ import annotations

import json

import streamlit as st
import streamlit.components.v1 as components


def _brand_bits():
    """Lazy brand/icon load so a stale branding.py cannot break login."""
    name = "TIM TEAM"
    system = "TIM TEAM SYSTEM"
    icon = ""
    icon_big = ""
    try:
        import tt_core.branding as b

        name = getattr(b, "BRAND_NAME", name) or name
        system = getattr(b, "BRAND_SYSTEM", system) or system
        fn = getattr(b, "icon_data_uri", None)
        if callable(fn):
            icon = fn(180) or ""
            icon_big = fn(512) or icon
    except Exception:
        pass
    return name, system, icon, icon_big


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
    brand_name, brand_system, icon, icon_big = _brand_bits()
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
  if (head.getAttribute('data-tt-pwa') === 'ace-v2') return;
  head.setAttribute('data-tt-pwa', 'ace-v2');

  function upsertMeta(attr, key, value) {{
    let el = head.querySelector('meta[' + attr + '="' + key + '"]');
    if (!el) {{
      el = doc.createElement('meta');
      el.setAttribute(attr, key);
      head.appendChild(el);
    }}
    el.setAttribute('content', value);
  }}

  function upsertLink(rel, href, sizes) {{
    let el = head.querySelector('link[rel="' + rel + '"]' + (sizes ? '[sizes="' + sizes + '"]' : ''));
    if (!el) {{
      el = doc.createElement('link');
      el.setAttribute('rel', rel);
      if (sizes) el.setAttribute('sizes', sizes);
      head.appendChild(el);
    }}
    el.setAttribute('href', href);
  }}

  const icon = {icon_js};
  const iconBig = {icon_big_js};
  const brand = {brand_js};

  upsertMeta('name', 'viewport',
    'width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover, user-scalable=no');
  upsertMeta('name', 'apple-mobile-web-app-capable', 'yes');
  upsertMeta('name', 'mobile-web-app-capable', 'yes');
  upsertMeta('name', 'apple-mobile-web-app-status-bar-style', 'black-translucent');
  upsertMeta('name', 'apple-mobile-web-app-title', brand);
  upsertMeta('name', 'application-name', brand);
  upsertMeta('name', 'theme-color', '#0A0D14');

  upsertLink('apple-touch-icon', icon, '180x180');
  upsertLink('icon', icon, '180x180');
  upsertLink('icon', iconBig, '512x512');

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
    brand_name, _, _, _ = _brand_bits()
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
