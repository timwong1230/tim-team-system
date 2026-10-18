"""iPhone / iPad helpers: device detect, PWA meta, install guidance."""

from __future__ import annotations

import json

import streamlit as st

_APP_URL = "https://tim-team-system.streamlit.app/"


def _brand_bits():
    """Lazy brand load so a stale branding.py cannot break login."""
    name = "TIM TEAM"
    system = "TIM TEAM SYSTEM"
    try:
        import tt_core.branding as b

        name = getattr(b, "BRAND_NAME", name) or name
        system = getattr(b, "BRAND_SYSTEM", system) or system
    except Exception:
        pass
    return name, system


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
    """Inject light iOS meta (viewport / title / standalone). Leave Streamlit crown icon alone."""
    brand_name, _brand_system = _brand_bits()
    payload = {"brand": brand_name, "version": "tt-meta-v1"}
    payload_js = json.dumps(payload)

    script = f"""
<script>
(function () {{
  var P = {payload_js};
  var doc = document;
  var head = doc.head || doc.getElementsByTagName('head')[0];
  if (!head) return;
  if (head.getAttribute('data-tt-pwa') === P.version) return;

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

  upsertMeta('name', 'viewport',
    'width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover, user-scalable=no');
  upsertMeta('name', 'apple-mobile-web-app-capable', 'yes');
  upsertMeta('name', 'mobile-web-app-capable', 'yes');
  upsertMeta('name', 'apple-mobile-web-app-status-bar-style', 'black-translucent');
  upsertMeta('name', 'apple-mobile-web-app-title', P.brand);
  upsertMeta('name', 'application-name', P.brand);
  upsertMeta('name', 'theme-color', '#F3F1EB', '(prefers-color-scheme: light)');
  upsertMeta('name', 'theme-color', '#0F1419', '(prefers-color-scheme: dark)');
  upsertMeta('name', 'theme-color', '#0F1419');
  upsertMeta('property', 'og:title', P.brand);

  try {{ doc.title = P.brand; }} catch (e) {{}}
  head.setAttribute('data-tt-pwa', P.version);

  var standalone = (window.navigator.standalone === true)
    || window.matchMedia('(display-mode: standalone)').matches;
  if (standalone) {{
    doc.documentElement.setAttribute('data-tt-standalone', '1');
  }}
}})();
</script>
"""

    try:
        st.html(script, unsafe_allow_javascript=True)
        return
    except Exception:
        pass
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
    """Safari Add to Home Screen — Streamlit Cloud keeps the crown icon (accepted)."""
    brand_name, _ = _brand_bits()
    body_zh = (
        f"1. 用 **Safari** 打開 {_APP_URL}\n"
        "2. 撳底部分享 → **加到主畫面**\n"
        f"3. 名稱改成 **{brand_name}** → 新增\n"
        "4. 圖示會係 Streamlit 皇冠（Cloud 平台限制，正常）\n"
    )
    if compact:
        with st.expander("加到 iPhone 主畫面", expanded=False):
            st.markdown(body_zh)
            st.caption("iPad 同樣步驟。")
    else:
        st.markdown("### 加到 iPhone 主畫面")
        st.markdown(body_zh)
        st.info(f"加好之後喺主畫面撳圖示就可以快啲開 {brand_name}。")


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
