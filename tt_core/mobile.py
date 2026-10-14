"""iPhone / iPad helpers: device detect, PWA meta, install guidance."""

from __future__ import annotations

import streamlit as st
import streamlit.components.v1 as components


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
    Inject iOS / PWA meta tags into <head> so Safari「加到主畫面」
    opens as a standalone app (no browser chrome).
    """
    components.html(
        """
<!DOCTYPE html>
<html><head></head><body>
<script>
(function () {
  const doc = window.parent.document;
  const head = doc.head || doc.getElementsByTagName('head')[0];
  if (!head || head.getAttribute('data-tt-pwa') === '1') return;
  head.setAttribute('data-tt-pwa', '1');

  function upsertMeta(attr, key, value) {
    let el = head.querySelector('meta[' + attr + '="' + key + '"]');
    if (!el) {
      el = doc.createElement('meta');
      el.setAttribute(attr, key);
      head.appendChild(el);
    }
    el.setAttribute('content', value);
  }

  function upsertLink(rel, href, sizes) {
    let el = head.querySelector('link[rel="' + rel + '"]' + (sizes ? '[sizes="' + sizes + '"]' : ''));
    if (!el) {
      el = doc.createElement('link');
      el.setAttribute('rel', rel);
      if (sizes) el.setAttribute('sizes', sizes);
      head.appendChild(el);
    }
    el.setAttribute('href', href);
  }

  upsertMeta('name', 'viewport',
    'width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover, user-scalable=no');
  upsertMeta('name', 'apple-mobile-web-app-capable', 'yes');
  upsertMeta('name', 'mobile-web-app-capable', 'yes');
  upsertMeta('name', 'apple-mobile-web-app-status-bar-style', 'black-translucent');
  upsertMeta('name', 'apple-mobile-web-app-title', 'TIM TEAM');
  upsertMeta('name', 'application-name', 'TIM TEAM');
  upsertMeta('name', 'theme-color', '#1C2430');

  // Gold TIM icon (SVG data URI) — works as home-screen icon
  const icon =
    'data:image/svg+xml,' + encodeURIComponent(
      '<svg xmlns="http://www.w3.org/2000/svg" width="180" height="180" viewBox="0 0 180 180">' +
      '<rect width="180" height="180" rx="40" fill="#1C2430"/>' +
      '<circle cx="90" cy="90" r="62" fill="none" stroke="#D4AF37" stroke-width="6"/>' +
      '<text x="90" y="104" text-anchor="middle" font-family="Georgia, serif" font-size="42" font-weight="700" fill="#D4AF37">TIM</text>' +
      '</svg>'
    );
  upsertLink('apple-touch-icon', icon, '180x180');
  upsertLink('icon', icon, '180x180');

  // Minimal web manifest via blob URL
  const manifest = {
    name: 'TIM TEAM System',
    short_name: 'TIM TEAM',
    start_url: '.',
    display: 'standalone',
    background_color: '#1C2430',
    theme_color: '#1C2430',
    lang: 'zh-Hant',
    icons: [{ src: icon, sizes: '180x180', type: 'image/svg+xml', purpose: 'any maskable' }]
  };
  const blob = new Blob([JSON.stringify(manifest)], { type: 'application/manifest+json' });
  const url = URL.createObjectURL(blob);
  let link = head.querySelector('link[rel="manifest"]');
  if (!link) {
    link = doc.createElement('link');
    link.rel = 'manifest';
    head.appendChild(link);
  }
  link.href = url;

  // Hide Streamlit chrome a bit when launched from home screen
  const standalone = window.parent.navigator.standalone === true
    || window.parent.matchMedia('(display-mode: standalone)').matches;
  if (standalone) {
    doc.documentElement.setAttribute('data-tt-standalone', '1');
  }
})();
</script>
</body></html>
        """,
        height=0,
        width=0,
    )


def render_install_guide(*, compact: bool = False) -> None:
    """Safari → Add to Home Screen instructions."""
    title = "加到 iPhone 主畫面（變 App）"
    body = """
1. 用 **Safari** 打開本網站（唔好用 Chrome）
2. 撳底部分享按鈕 **□↑**
3. 向下滑，揀 **「加到主畫面」/ Add to Home Screen**
4. 名稱用 **TIM TEAM** → 新增
5. 之後喺主畫面撳圖示，就會好似 App 咁開（全螢幕）
"""
    if compact:
        with st.expander(title, expanded=False):
            st.markdown(body)
            st.caption("iPad 同樣步驟。Android：Chrome 選單 →「安裝應用程式」。")
    else:
        st.markdown(f"### {title}")
        st.markdown(body)
        st.info("一次加好，成隊同事主畫面都有 TIM TEAM，打卡會快好多。")


def mobile_top_nav(menu_items: list[str], current: str | None = None) -> str:
    """Compact top navigation for phones (avoids opening sidebar every time)."""
    # Prefer short labels on mobile
    labels = []
    for item in menu_items:
        # keep emoji + first phrase
        labels.append(item)
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
