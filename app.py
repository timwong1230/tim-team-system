"""TIM TEAM System — activity + performance hub."""
# redeploy_marker: force Streamlit Cloud restart


from __future__ import annotations

import datetime
import re
import sys
import urllib.parse
from pathlib import Path

# Streamlit Cloud: ensure project root is on sys.path
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from tt_core.constants import (
    ACTIVITY_TYPES,
    MDRT_TARGET,
    Q1_TARGET,
    WEEKLY_MIN_ACTS,
    WEEKLY_PENALTY,
)
from tt_core.data import (
    add_act,
    check_notifications,
    get_activity_style,
    get_all_act,
    get_clean_users,
    get_data,
    get_last_week_data,
    get_member_snapshot,
    get_note_template,
    get_q1_data,
    get_weekly_data,
    last_iris_sync,
    login,
    proc_img,
    upd_fyc,
    upd_rec,
    update_avt,
    update_pw,
)

try:
    from tt_core.data import scrub_notification_session_state
except Exception:

    def scrub_notification_session_state():
        pending = st.session_state.get("_notif_pending_payload")
        if pending is not None and not isinstance(pending, list):
            st.session_state["_notif_pending_payload"] = None
from tt_core.db import (
    connection_banner_state,
    init_db_gs,
    read_data,
    run_query_gs,
    warm_cache,
)

# Inline fallbacks — Streamlit Cloud may cache an older tt_core.data without
# quarterly helpers / miss tt_core.quarterly_offers on a partial reboot.
_QUARTERS_FALLBACK = {
    "Q1": {"label": "第一季", "period": "1月 – 3月", "months": (1, 2, 3)},
    "Q2": {"label": "第二季", "period": "4月 – 6月", "months": (4, 5, 6)},
    "Q3": {"label": "第三季", "period": "7月 – 9月", "months": (7, 8, 9)},
    "Q4": {"label": "第四季", "period": "10月 – 12月", "months": (10, 11, 12)},
}


def _quarterly_mod():
    try:
        import tt_core.quarterly_offers as m

        return m
    except Exception:
        return None


def _quarters_map() -> dict:
    m = _quarterly_mod()
    return getattr(m, "QUARTERS", None) or _QUARTERS_FALLBACK


def _current_quarter_key() -> str:
    m = _quarterly_mod()
    fn = getattr(m, "current_quarter_key", None) if m else None
    if callable(fn):
        try:
            return str(fn())
        except Exception:
            pass
    month = datetime.date.today().month
    if month <= 3:
        return "Q1"
    if month <= 6:
        return "Q2"
    if month <= 9:
        return "Q3"
    return "Q4"


def get_quarterly_offer_items(quarter: str, kind: str) -> list[dict]:
    """Prefer tt_core.data; fall back to sheet + quarterly_offers if Cloud is stale."""
    try:
        import tt_core.data as d

        fn = getattr(d, "get_quarterly_offer_items", None)
        if callable(fn):
            return list(fn(quarter, kind) or [])
    except Exception:
        pass

    q = str(quarter or "").strip().upper()
    k = str(kind or "").strip().lower()
    if k not in {"customer", "agent"}:
        return []
    try:
        df = read_data("quarterly_offers")
        if df is not None and not df.empty and "quarter" in df.columns:
            work = df.copy()
            work["quarter"] = work["quarter"].astype(str).str.strip().str.upper()
            work["kind"] = work["kind"].astype(str).str.strip().str.lower()
            hit = work[(work["quarter"] == q) & (work["kind"] == k)]
            if not hit.empty:
                rows = []
                for _, r in hit.iterrows():
                    title = str(r.get("title", "") or "").strip()
                    if not title:
                        continue
                    rows.append(
                        {
                            "id": r.get("id", ""),
                            "title": title,
                            "detail": str(r.get("detail", "") or "").strip(),
                            "note": str(r.get("note", "") or "").strip(),
                            "sort": int(pd.to_numeric(r.get("sort", 0), errors="coerce") or 0),
                        }
                    )
                if rows:
                    return sorted(rows, key=lambda x: x["sort"])
    except Exception:
        pass

    m = _quarterly_mod()
    default_items = getattr(m, "default_items", None) if m else None
    if callable(default_items):
        try:
            return list(default_items(q, k) or [])
        except Exception:
            return []
    return []


def _legacy_list_to_catalog(items: list, *, kind: str) -> dict:
    """Convert old title/detail card list into one table section."""
    rows = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "") or "").strip()
        if not title:
            continue
        rows.append(
            [
                title,
                str(item.get("detail", "") or "").strip(),
                str(item.get("note", "") or "").strip(),
            ]
        )
    if not rows:
        return {"banner": "", "footnote": "", "sections": []}
    label = "客戶優惠" if kind == "customer" else "營業員獎賞"
    return {
        "banner": "",
        "footnote": "",
        "sections": [
            {
                "title": label,
                "columns": ["項目", "詳情", "備註"],
                "rows": rows,
            }
        ],
    }


def get_quarterly_catalog(quarter: str, kind: str) -> dict:
    """Table catalog with lazy fallbacks for Streamlit Cloud cache lag."""
    empty = {"banner": "", "footnote": "", "sections": []}
    q = str(quarter or "").strip().upper()
    k = str(kind or "").strip().lower()
    if k not in {"customer", "agent"}:
        return empty

    # 1) Prefer tt_core.data helper when present and non-empty
    try:
        import tt_core.data as d

        fn = getattr(d, "get_quarterly_catalog", None)
        if callable(fn):
            cat = fn(q, k)
            if isinstance(cat, dict) and (cat.get("sections") or []):
                return cat
    except Exception:
        pass

    m = _quarterly_mod()
    from_flat = getattr(m, "catalog_from_flat_items", None) if m else None
    default_catalog = getattr(m, "default_catalog", None) if m else None

    # 2) Sheet override only when there are real titled rows
    try:
        df = read_data("quarterly_offers")
        if df is not None and not df.empty and "quarter" in df.columns:
            work = df.copy()
            work["quarter"] = work["quarter"].astype(str).str.strip().str.upper()
            work["kind"] = work["kind"].astype(str).str.strip().str.lower()
            hit = work[(work["quarter"] == q) & (work["kind"] == k)]
            sheet_items = []
            for _, r in hit.iterrows():
                title = str(r.get("title", "") or "").strip()
                if not title:
                    continue
                sheet_items.append(
                    {
                        "title": title,
                        "detail": str(r.get("detail", "") or "").strip(),
                        "note": str(r.get("note", "") or "").strip(),
                        "sort": int(pd.to_numeric(r.get("sort", 0), errors="coerce") or 0),
                    }
                )
            if sheet_items and callable(from_flat):
                cat = from_flat(sheet_items, kind=k)
                if cat.get("sections"):
                    return cat
            if sheet_items:
                return _legacy_list_to_catalog(sheet_items, kind=k)
    except Exception:
        pass

    # 3) New catalog API
    if callable(default_catalog):
        try:
            cat = default_catalog(q, k)
            if isinstance(cat, dict) and (cat.get("sections") or []):
                return cat
        except Exception:
            pass

    # 4) Direct DEFAULT_CATALOG / legacy DEFAULT_OFFERS on the module
    if m is not None:
        try:
            catalog_root = getattr(m, "DEFAULT_CATALOG", None) or getattr(m, "DEFAULT_OFFERS", None)
            block = (catalog_root or {}).get(q, {}).get(k)
            if isinstance(block, dict) and (block.get("sections") or []):
                return {
                    "banner": str(block.get("banner", "") or ""),
                    "footnote": str(block.get("footnote", "") or ""),
                    "sections": list(block.get("sections") or []),
                }
            if isinstance(block, dict) and isinstance(block.get("customer"), list):
                pass
            # Legacy: DEFAULT_OFFERS[Q4][customer] was a list of cards
            if isinstance(block, list) and block:
                return _legacy_list_to_catalog(block, kind=k)
            # Even older nested shape {"customer": [...]} already handled above
            if isinstance(catalog_root, dict):
                legacy = catalog_root.get(q, {})
                if isinstance(legacy, dict) and isinstance(legacy.get(k), list):
                    return _legacy_list_to_catalog(legacy.get(k), kind=k)
        except Exception:
            pass

    return empty


def add_quarterly_offer(
    quarter: str, kind: str, title: str, detail: str, note: str = "", sort: int = 0
) -> bool:
    try:
        import tt_core.data as d

        fn = getattr(d, "add_quarterly_offer", None)
        if callable(fn):
            return bool(fn(quarter, kind, title, detail, note, sort))
    except Exception:
        pass
    # Direct Sheets write if data helper missing on stale Cloud cache
    return bool(
        run_query_gs(
            "INSERT",
            "quarterly_offers",
            {
                "quarter": str(quarter).strip().upper(),
                "kind": str(kind).strip().lower(),
                "title": str(title or "").strip(),
                "detail": str(detail or "").strip(),
                "note": str(note or "").strip(),
                "sort": int(sort or 0),
                "updated_at": str(datetime.datetime.now()),
            },
        )
    )


def delete_quarterly_offer(row_id) -> bool:
    if row_id is None or str(row_id).strip() == "":
        return False
    try:
        import tt_core.data as d

        fn = getattr(d, "delete_quarterly_offer", None)
        if callable(fn):
            return bool(fn(row_id))
    except Exception:
        pass
    return bool(run_query_gs("DELETE", "quarterly_offers", row_id=row_id))


def get_team_sc(fallback: float = 0.0) -> float:
    """Leader Team SC from system_settings — no extra module imports at call time."""
    try:
        df = read_data("system_settings")
        if df is None or df.empty or "key" not in df.columns:
            return float(fallback or 0)
        hit = df[df["key"].astype(str) == "team_sc"]
        if hit.empty:
            return float(fallback or 0)
        raw = str(hit.iloc[0].get("value", "") or "").strip()
        if not raw:
            return float(fallback or 0)
        return float(
            raw.replace(",", "").replace("$", "").replace("HK$", "").replace(" ", "")
        )
    except Exception:
        return float(fallback or 0)


def set_team_sc(amount: float) -> bool:
    try:
        value = str(float(amount))
        now = str(datetime.datetime.now())
        df = read_data("system_settings")
        if df is not None and not df.empty and "key" in df.columns:
            hit = df[df["key"].astype(str) == "team_sc"]
            if (
                not hit.empty
                and "id" in df.columns
                and str(hit.iloc[0].get("id", "")).strip()
            ):
                return bool(
                    run_query_gs(
                        "UPDATE",
                        "system_settings",
                        {"value": value, "updated_at": now},
                        row_id=hit.iloc[0]["id"],
                    )
                )
        return bool(
            run_query_gs(
                "INSERT",
                "system_settings",
                {"key": "team_sc", "value": value, "updated_at": now},
            )
        )
    except Exception:
        return False


# Inline key — avoid late ImportError if Cloud caches an older constants.py
_MDRT_PROGRESS_MONTH = "MDRT_2027"


def get_mdrt_progress_map() -> dict[str, float]:
    """Per-member 2027 MDRT temporary progress (plan bonus + other credit)."""
    try:
        fyc_df = read_data("monthly_fyc")
        if fyc_df is None or fyc_df.empty or "amount" not in fyc_df.columns:
            return {}
        fyc_df = fyc_df.copy()
        fyc_df["month"] = fyc_df["month"].astype(str).str.strip()
        fyc_df["amount"] = pd.to_numeric(fyc_df["amount"], errors="coerce").fillna(0)
        rows = fyc_df[fyc_df["month"] == _MDRT_PROGRESS_MONTH]
        if rows.empty:
            return {}
        grouped = rows.groupby("username")["amount"].max()
        return {str(k).strip(): float(v) for k, v in grouped.items()}
    except Exception:
        return {}


def lookup_mdrt_progress(username: str, progress_map: dict[str, float] | None = None) -> float:
    """Same amount Leaderboard uses for a member (MDRT_2027), case-insensitive."""
    if progress_map is None:
        progress_map = get_mdrt_progress_map()
    key = str(username or "").strip()
    if not key:
        return 0.0
    if key in progress_map:
        return float(progress_map[key])
    lower = {str(k).strip().lower(): float(v) for k, v in progress_map.items()}
    return float(lower.get(key.lower(), 0.0))


def mdrt_card_metrics(username: str, progress_map: dict[str, float] | None = None) -> dict:
    """Home / Leaderboard shared MDRT progress, % and 尚欠."""
    progress = lookup_mdrt_progress(username, progress_map)
    target = float(MDRT_TARGET) if MDRT_TARGET else 0.0
    pct = min(progress / target * 100, 100.0) if target else 0.0
    remaining = max(target - progress, 0.0)
    met = target > 0 and progress >= target
    return {
        "mdrt_progress": progress,
        "mdrt_pct": pct,
        "mdrt_remaining": remaining,
        "mdrt_met": met,
    }


def set_mdrt_progress(username: str, amount: float) -> None:
    upd_fyc(username, _MDRT_PROGRESS_MONTH, float(amount), source="mdrt_progress")


def _iris():
    """Lazy-load iris module so login/home still boots if Cloud has a stale cache."""
    import tt_core.iris as m

    return m


_IRIS_UPLOAD_MAX_BYTES = 8 * 1024 * 1024  # 8MB — Cloud free tier OOM → sticky Oh-no
_FORMS_UPLOAD_MAX_BYTES = 8 * 1024 * 1024


def _bytes_from_upload(uploaded, *, max_bytes: int) -> tuple[bytes, str]:
    """Read uploader bytes safely; refuse oversized files before they kill Cloud."""
    name = str(getattr(uploaded, "name", "") or "upload.bin")
    raw = b""
    try:
        if hasattr(uploaded, "getvalue"):
            raw = uploaded.getvalue()
        else:
            raw = uploaded.read()
    except Exception as e:
        raise ValueError(f"讀取檔案失敗：{e}") from e
    if not raw:
        raise ValueError("檔案係空嘅")
    if len(raw) > max_bytes:
        mb = max_bytes / (1024 * 1024)
        raise ValueError(f"檔案太大（上限 {mb:.0f}MB）。請壓縮或用 Drive 同步。")
    return raw, name


def _json_safe_cell(v):
    """Convert one cell to a session_state-safe scalar."""
    try:
        if v is None:
            return None
        if isinstance(v, (bool, str)):
            return v
        if isinstance(v, int) and not isinstance(v, bool):
            return int(v)
        if isinstance(v, float):
            return None if pd.isna(v) else float(v)
        if hasattr(v, "item"):
            try:
                return _json_safe_cell(v.item())
            except Exception:
                pass
        # pandas NA / NaT
        try:
            if pd.isna(v):
                return None
        except Exception:
            pass
        return str(v)
    except Exception:
        return None


def _store_iris_preview(preview) -> None:
    """Persist iris preview as plain rows — never a DataFrame (Cloud Oh-no risk)."""
    st.session_state.pop("_iris_last_preview", None)  # drop legacy DF key
    if preview is None or getattr(preview, "empty", True):
        st.session_state["_iris_last_preview_rows"] = []
        return
    rows: list[dict] = []
    try:
        for rec in preview.to_dict("records"):
            rows.append({str(k): _json_safe_cell(v) for k, v in rec.items()})
    except Exception:
        rows = []
    st.session_state["_iris_last_preview_rows"] = rows


def _load_iris_preview():
    """Rebuild preview DataFrame from plain session rows (or clear legacy DF)."""
    legacy = st.session_state.get("_iris_last_preview")
    if legacy is not None:
        st.session_state.pop("_iris_last_preview", None)
        if hasattr(legacy, "to_dict"):
            try:
                _store_iris_preview(legacy)
            except Exception:
                pass
    rows = st.session_state.get("_iris_last_preview_rows")
    if not isinstance(rows, list) or not rows:
        return None
    try:
        return pd.DataFrame(rows)
    except Exception:
        return None


def _is_dataframe_like(obj) -> bool:
    try:
        return hasattr(obj, "to_dict") and hasattr(obj, "empty") and hasattr(obj, "columns")
    except Exception:
        return False


def _scrub_dataframe_session_keys() -> None:
    """Remove DataFrame payloads that OOM / hard-crash Streamlit Cloud."""
    try:
        scrub_notification_session_state()
    except Exception:
        st.session_state.pop("_notif_pending_payload", None)
    legacy = st.session_state.get("_iris_last_preview")
    if legacy is not None and not isinstance(legacy, list):
        st.session_state.pop("_iris_last_preview", None)
        if _is_dataframe_like(legacy) and not getattr(legacy, "empty", True):
            try:
                _store_iris_preview(legacy)
            except Exception:
                st.session_state["_iris_last_preview_rows"] = []
    # Drop every backup_* / accidental DF left by older builds
    for key in list(st.session_state.keys()):
        try:
            val = st.session_state.get(key)
            if str(key).startswith("backup_") or _is_dataframe_like(val):
                del st.session_state[key]
        except Exception:
            try:
                st.session_state.pop(key, None)
            except Exception:
                pass


def _iris_call(name: str, *args, **kwargs):
    """Call an iris helper; raise a clear error if Cloud still has a stale module."""
    import inspect

    m = _iris()
    fn = getattr(m, name, None)
    if fn is None:
        raise AttributeError(
            f"系統未更新完（缺少 {name}）。請去 Streamlit Manage app → Reboot 後再試。"
        )
    try:
        sig = inspect.signature(fn)
        if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()):
            return fn(*args, **kwargs)
        allowed = set(sig.parameters)
        # drop bound 'self' if present
        allowed.discard("self")
        filtered = {k: v for k, v in kwargs.items() if k in allowed}
        # positional overflow if old signature is shorter
        params = [
            p
            for p in sig.parameters.values()
            if p.kind
            in (
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
            )
        ]
        max_pos = len(params)
        if max_pos and len(args) > max_pos:
            args = args[:max_pos]
        return fn(*args, **filtered)
    except (TypeError, ValueError):
        # Last resort: positional-only for very old helpers
        return fn(*args)



def _drive():
    """Lazy-load Drive helpers with back-compat for older module shapes."""
    import tt_core.iris_drive as m

    return m


_DAILY_FOLDER_KEY = "iris_drive_folder_id"
_MDRT_FOLDER_KEY = "mdrt_drive_folder_id"

_DAILY_TEMPLATE_CSV = (
    "Agent Name,Agent Code,MTD_Sub_FYC,MTD_Comp_FYC,Month\n"
    "Tim,30947,60000,52000,2026-10\n"
    "Oscar,59164,40000,10000,2026-10\n"
)
_MDRT_TEMPLATE_CSV = (
    "Agent Name,Agent Code,Total Credit eligible for MDRT\n"
    "Tim,30947,398944\n"
    "Oscar,59164,162848\n"
)


def _normalize_folder_id(folder_id: str) -> str:
    folder_id = str(folder_id or "").strip()
    if "/folders/" in folder_id:
        folder_id = folder_id.split("/folders/")[1].split("?")[0].split("/")[0]
    return folder_id


def _get_setting(key: str, default: str = "") -> str:
    try:
        ss_key = f"_setting_{key}"
        if ss_key in st.session_state and str(st.session_state.get(ss_key) or "").strip():
            return str(st.session_state[ss_key]).strip()
    except Exception:
        pass
    try:
        df = read_data("system_settings")
        if df is None or df.empty or "key" not in df.columns:
            return default
        hit = df[df["key"].astype(str) == key]
        if hit.empty:
            return default
        return str(hit.iloc[0].get("value", default) or default).strip()
    except Exception:
        return default


def _set_setting(key: str, value: str) -> bool:
    """Persist setting via db; succeed if Sheets OK or local cache/session has it."""
    value = str(value or "").strip()
    if not value:
        return False
    now = str(datetime.datetime.now())
    try:
        st.session_state[f"_setting_{key}"] = value
    except Exception:
        pass
    try:
        df = read_data("system_settings")
        if df is not None and not df.empty and "key" in df.columns:
            hit = df[df["key"].astype(str) == key]
            if (
                not hit.empty
                and "id" in df.columns
                and str(hit.iloc[0].get("id", "")).strip()
            ):
                run_query_gs(
                    "UPDATE",
                    "system_settings",
                    {"value": value, "updated_at": now},
                    row_id=hit.iloc[0]["id"],
                )
            else:
                run_query_gs(
                    "INSERT",
                    "system_settings",
                    {"key": key, "value": value, "updated_at": now},
                )
        else:
            run_query_gs(
                "INSERT",
                "system_settings",
                {"key": key, "value": value, "updated_at": now},
            )
    except Exception:
        pass
    # Accept session/cache as success so UI works even when Sheets is slow
    return _get_setting(key, "") == value


def get_daily_folder_id() -> str:
    got = _get_setting(_DAILY_FOLDER_KEY, "")
    if got:
        return got
    try:
        d = _drive()
        fn = getattr(d, "get_daily_folder_id", None) or getattr(d, "get_folder_id", None)
        return str(fn() or "") if fn else ""
    except Exception:
        return ""


def get_mdrt_folder_id() -> str:
    got = _get_setting(_MDRT_FOLDER_KEY, "")
    if got:
        return got
    try:
        d = _drive()
        fn = getattr(d, "get_mdrt_folder_id", None)
        return str(fn() or "") if fn else ""
    except Exception:
        return ""


def save_daily_folder_id(folder_id: str) -> bool:
    return _set_setting(_DAILY_FOLDER_KEY, _normalize_folder_id(folder_id))


def save_mdrt_folder_id(folder_id: str) -> bool:
    return _set_setting(_MDRT_FOLDER_KEY, _normalize_folder_id(folder_id))


def sample_daily_template_csv() -> str:
    try:
        fn = getattr(_iris(), "sample_template_csv", None)
        if fn:
            return str(fn())
    except Exception:
        pass
    return _DAILY_TEMPLATE_CSV


def sample_mdrt_template_csv() -> str:
    try:
        fn = getattr(_iris(), "sample_mdrt_template_csv", None)
        if fn:
            return str(fn())
    except Exception:
        pass
    return _MDRT_TEMPLATE_CSV


def mark_daily_file_synced(file_id: str) -> None:
    d = _drive()
    fn = getattr(d, "mark_daily_file_synced", None) or getattr(d, "mark_file_synced", None)
    if fn:
        fn(file_id)


def mark_mdrt_file_synced(file_id: str) -> None:
    d = _drive()
    fn = getattr(d, "mark_mdrt_file_synced", None) or getattr(d, "mark_file_synced", None)
    if fn:
        fn(file_id)


def has_new_inbox_file():
    d = _drive()
    fn = getattr(d, "has_new_inbox_file", None)
    return fn() if fn else None


def list_inbox_files(folder_id: str | None = None, limit: int = 15):
    return _drive().list_inbox_files(folder_id=folder_id, limit=limit)


def download_file(file_id: str) -> bytes:
    return _drive().download_file(file_id)


def service_account_email():
    return _drive().service_account_email()

from tt_core.mobile import (
    inject_pwa_head,
    is_mobile,
    mobile_top_nav,
    render_install_guide,
)
from tt_core.styles import CUSTOM_CSS

# Inline brand fallbacks — Cloud may cache an older tt_core.branding without page_icon_arg
BRAND_NAME = "TIM TEAM"
BRAND_APP = "TIM TEAM APP"
BRAND_SYSTEM = "TIM TEAM SYSTEM"


def page_icon_arg():
    """Prefer a real image file path/PIL — Streamlit converts this to a media URL for the tab."""
    from pathlib import Path

    root = Path(__file__).resolve().parent
    for rel in (
        "static/apple-touch-icon.png",
        "static/app_icon_180.png",
        "static/app_icon_512.png",
        "static/app_icon_32.png",
        "static/ace_team_logo.jpg",
    ):
        path = root / rel
        if not path.exists():
            continue
        try:
            from PIL import Image

            return Image.open(path)
        except Exception:
            return str(path)
    # Public CDN fallback if static/ missing on a stale Cloud image
    return "https://cdn.jsdelivr.net/gh/timwong1230/tim-team-system@main/static/apple-touch-icon.png"


try:
    import tt_core.branding as _brand

    BRAND_NAME = getattr(_brand, "BRAND_NAME", BRAND_NAME) or BRAND_NAME
    BRAND_APP = getattr(_brand, "BRAND_APP", BRAND_APP) or BRAND_APP
    BRAND_SYSTEM = getattr(_brand, "BRAND_SYSTEM", BRAND_SYSTEM) or BRAND_SYSTEM
except Exception:
    pass

try:
    MOBILE = is_mobile()
except Exception:
    MOBILE = False

try:
    st.set_page_config(
        page_title=BRAND_NAME,
        page_icon=page_icon_arg(),
        layout="centered" if MOBILE else "wide",
        initial_sidebar_state="collapsed" if MOBILE else "expanded",
    )
except Exception:
    try:
        st.set_page_config(page_title=BRAND_NAME, page_icon="🃏")
    except Exception:
        pass
try:
    inject_pwa_head()
except Exception:
    pass
try:
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
except Exception:
    pass
try:
    init_db_gs()  # cached once per server process — no longer hits Sheets every rerun
except Exception:
    # Don't take down the whole app if Sheets/secrets are briefly unavailable
    pass


# ─── Auth ────────────────────────────────────────────────────────────────────
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False

# Always scrub DF session payloads first (even on login page) — Cloud OOM guard
try:
    _scrub_dataframe_session_keys()
except Exception:
    pass

if not st.session_state["logged_in"]:
    if MOBILE:
        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
        st.markdown(
            f"""
            <div class="login-panel">
              <div class="tt-kicker" style="color:#C5A028 !important;">{BRAND_APP}</div>
              <h1 style="margin:0 0 6px 0;">活動量管理系統</h1>
            </div>
            """,
            unsafe_allow_html=True,
        )
        u = st.text_input("Username", placeholder="e.g. Tim")
        p = st.text_input("Password", type="password", placeholder="••••••")
        if st.button("登入", use_container_width=True):
            d = login(u, p)
            if d:
                st.session_state.update(
                    {
                        "logged_in": True,
                        "user": d[0][0],
                        "role": d[0][2],
                        "avatar": d[0][5],
                    }
                )
                st.session_state.pop("_notif_checked_this_login", None)
                st.session_state.pop("_notif_pending_payload", None)
                st.toast(f"Welcome back, {d[0][0]}!", icon="🦁")
                st.rerun()
            else:
                st.toast("登入失敗，請檢查帳密", icon="❌")
        st.markdown(
            """
            <div class="tt-install-card">
              <strong>想變主畫面 App？</strong><br>
              Safari 打開 → 分享 →「加到主畫面」
            </div>
            """,
            unsafe_allow_html=True,
        )
        render_install_guide(compact=True)
        st.caption("每年目標：M + 2")
        st.caption("若見到 Oh no：撳右下角紅色 Manage app → ⋮ → Reboot app，等 Running 後再開。")
    else:
        c1, c2, c3 = st.columns([1, 1.4, 1])
        with c2:
            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown(
                f"""
                <div class="login-panel">
                  <div class="tt-kicker" style="color:#C5A028 !important;">{BRAND_SYSTEM}</div>
                  <h1 style="margin:0 0 6px 0;">活動量管理系統</h1>
                  <p style="color:#6B7280; margin:0 0 18px 0;">打卡更快 · 戰報更清晰 · Iris 業績自動同步</p>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.markdown("<br>", unsafe_allow_html=True)
            u = st.text_input("Username", placeholder="e.g. Tim")
            p = st.text_input("Password", type="password", placeholder="••••••")
            if st.button("登入系統", use_container_width=True):
                d = login(u, p)
                if d:
                    st.session_state.update(
                        {
                            "logged_in": True,
                            "user": d[0][0],
                            "role": d[0][2],
                            "avatar": d[0][5],
                        }
                    )
                    st.session_state.pop("_notif_checked_this_login", None)
                    st.session_state.pop("_notif_pending_payload", None)
                    st.toast(f"Welcome back, {d[0][0]}!", icon="🦁")
                    st.rerun()
                else:
                    st.toast("登入失敗，請檢查帳密", icon="❌")
            render_install_guide(compact=True)
            st.caption("2026 MDRT 目標：$512,800  ·  M + 2 = 百萬年薪之路")
    st.stop()


# ─── Logged-in shell ─────────────────────────────────────────────────────────
# Recover broken session (e.g. after a mid-upload crash) instead of Oh-no screen
if not st.session_state.get("user"):
    st.session_state["logged_in"] = False
    st.session_state.pop("_menu_choice", None)
    st.warning("登入狀態已失效，請重新登入。")
    st.rerun()

# Drop legacy DataFrame session payloads before any page work (Cloud crash risk)
try:
    _scrub_dataframe_session_keys()
except Exception:
    st.session_state.pop("_notif_pending_payload", None)
    st.session_state.pop("_iris_last_preview", None)

# One-time escape hatch after previous crash / bad menu
if st.session_state.get("_force_home_once"):
    st.session_state["_menu_choice"] = "🏠 我的主頁"
    st.session_state.pop("_force_home_once", None)

# Warm disk cache once per browser session so pages read locally (fast + offline-safe)
try:
    if not st.session_state.get("_warmed_at"):
        try:
            with st.spinner("正在載入團隊數據（首次會稍慢，之後會用快取）…"):
                warm_cache(force=False)
        except Exception:
            st.session_state["_warmed_at"] = True

    try:
        check_notifications(st.session_state.get("user"))
    except Exception:
        pass
    is_leader = st.session_state.get("role") == "Leader"
    try:
        conn = connection_banner_state()
    except Exception:
        conn = {"level": "unknown", "label": "數據狀態未知", "age": None, "raw": {}}
except Exception as e:
    st.session_state.clear()
    st.error(f"啟動失敗，已重置登入：{e}")
    st.info("請重新登入。若仍然 Oh no：右下角紅色 Manage app → ⋮ → Reboot app。")
    st.stop()

menu_items = [
    "🏠 我的主頁",
    "📝 打卡 Check-in",
    "📊 團隊 Dashboard",
    "📅 每月業績",
    "🏆 年度挑戰",
    "⚖️ 每週挑戰",
    "🤝 招募龍虎榜",
    "🎁 季度優惠 & 獎賞",
    "📁 常用表格",
    "🩺 常見疾病核保",
    "💹 收入／支出 T-Account",
]
if is_leader:
    menu_items.insert(4, "🔄 業績報告同步")
menu_items.append("👤 設定")

with st.sidebar:
    st.markdown("<br>", unsafe_allow_html=True)
    c_avt, c_txt = st.columns([1, 2])
    with c_avt:
        if st.session_state.get("avatar"):
            st.image(st.session_state["avatar"], width=64 if MOBILE else 72)
    with c_txt:
        st.markdown(
            f"<h3 style='margin:0'>{st.session_state['user']}</h3>",
            unsafe_allow_html=True,
        )
        st.caption(f"{st.session_state['role']} · {BRAND_NAME}")

    if conn["level"] == "ok":
        st.success(conn["label"], icon="⚡")
    elif conn["level"] == "degraded":
        st.warning(conn["label"], icon="📡")
    else:
        st.info(conn["label"])

    if st.button("重新整理數據", use_container_width=True, help="強制向 Google Sheets 拉最新數據"):
        with st.spinner("同步雲端…"):
            warm_cache(force=True)
        st.toast("數據已更新", icon="✅")
        st.rerun()

    sync = last_iris_sync()
    if sync:
        st.caption(f"Iris 上次同步：{str(sync.get('synced_at', ''))[:16]}")
    else:
        st.caption("Iris 尚未同步業績")

    st.divider()
    # Desktop: full radio menu in sidebar. Mobile: short list + top selectbox.
    if MOBILE:
        st.caption("手機可用上方選單切換功能；側欄放設定同登出。")
        render_install_guide(compact=True)
    else:
        menu_sidebar = st.radio("MAIN MENU", menu_items, label_visibility="collapsed")
        st.session_state["_menu_choice"] = menu_sidebar

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("登出", use_container_width=True, type="secondary"):
        st.session_state["logged_in"] = False
        st.rerun()

if MOBILE:
    st.markdown('<div class="tt-mobile-nav">', unsafe_allow_html=True)
    menu = mobile_top_nav(menu_items, st.session_state.get("_menu_choice"))
    st.session_state["_menu_choice"] = menu
    st.markdown("</div>", unsafe_allow_html=True)
else:
    menu = st.session_state.get("_menu_choice", menu_items[0])

if conn["level"] == "degraded":
    st.warning(
        "雲端 Sheets 暫時慢／斷線，而家顯示離線快取數據。"
        "你可以繼續打卡（會先存本機）；連線恢復後按側欄「重新整理數據」。",
        icon="📡",
    )

if is_leader:
    try:
        if get_daily_folder_id() or get_mdrt_folder_id():
            new_iris = has_new_inbox_file()
            if new_iris:
                kind = new_iris.get("report_kind") or "daily"
                kind_label = "MDRT Progress" if kind == "mdrt" else "Daily Production"
                st.info(
                    f"Drive {kind_label} 有新檔：**{new_iris.get('name')}** — "
                    "去側欄「業績報告同步」撳對應「同步最新檔」。",
                    icon="📥",
                )
    except Exception:
        pass


# ─── Pages ───────────────────────────────────────────────────────────────────
def page_home():
    user = st.session_state["user"]
    snap = get_member_snapshot(user) if st.session_state["role"] == "Member" else None
    team = get_data("Yearly")

    st.markdown(
        f"""
        <div class="tt-hero">
          <div class="tt-kicker">{BRAND_APP if MOBILE else BRAND_SYSTEM}</div>
          <h1 style="margin:0;">你好，{user}</h1>
          <p class="tt-sub">{"一撳打卡 · 即睇進度" if MOBILE else "今日目標：完成活動打卡 · 睇清楚自己同團隊進度"}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if snap:
        # Same MDRT_2027 source as Leaderboard (do not use YTD FYC here)
        mdrt = mdrt_card_metrics(user)
        mdrt_hint = (
            f"MDRT {mdrt['mdrt_pct']:.1f}% · 已達標"
            if mdrt["mdrt_met"]
            else f"MDRT {mdrt['mdrt_pct']:.1f}% · 尚欠 ${mdrt['mdrt_remaining']:,.0f}"
        )
        row1 = st.columns(2) if MOBILE else st.columns(4)
        cards = [
            (
                "本週活動",
                f"{snap['wk_count']} / {WEEKLY_MIN_ACTS}",
                f"分數 {snap['wk_score']} · {snap['wk_start']} 起",
                None,
            ),
            (
                "我的 MDRT 進度",
                f"${mdrt['mdrt_progress']:,.0f}",
                mdrt_hint,
                mdrt["mdrt_pct"],
            ),
            ("活動分數", f"{snap['score']}", "全年累積", None),
            ("招募", f"{snap['recruit']}", f"Team SC ${get_team_sc(snap['team_fyc']):,.0f}", None),
        ]
        if MOBILE:
            for col, card in zip(row1, cards[:2]):
                label, value, hint, pct = card
                bar = (
                    f'<div class="tt-progress-wrap"><div class="tt-progress-bar" style="width:{pct}%"></div></div>'
                    if pct is not None
                    else ""
                )
                col.markdown(
                    f'<div class="tt-card"><div class="tt-label">{label}</div>'
                    f'<div class="tt-value">{value}</div>'
                    f'<div class="tt-hint">{hint}</div>{bar}</div>',
                    unsafe_allow_html=True,
                )
            row2 = st.columns(2)
            for col, card in zip(row2, cards[2:]):
                label, value, hint, pct = card
                col.markdown(
                    f'<div class="tt-card"><div class="tt-label">{label}</div>'
                    f'<div class="tt-value">{value}</div>'
                    f'<div class="tt-hint">{hint}</div></div>',
                    unsafe_allow_html=True,
                )
        else:
            for col, card in zip(row1, cards):
                label, value, hint, pct = card
                bar = (
                    f'<div class="tt-progress-wrap"><div class="tt-progress-bar" style="width:{pct}%"></div></div>'
                    if pct is not None
                    else ""
                )
                col.markdown(
                    f'<div class="tt-card"><div class="tt-label">{label}</div>'
                    f'<div class="tt-value">{value}</div>'
                    f'<div class="tt-hint">{hint}</div>{bar}</div>',
                    unsafe_allow_html=True,
                )
    else:
        # Admin / Leader home: 2 metrics on phone, 3 on desktop
        calc = float(team["fyc"].sum()) if not team.empty else 0.0
        team_sc_home = get_team_sc(calc)
        if MOBILE:
            c1, c2 = st.columns(2)
            c1.metric("Team SC", f"${team_sc_home:,.0f}")
            c2.metric("Recruits", int(team["recruit"].sum()) if not team.empty else 0)
            st.metric(
                "Activities",
                int(team["Total_Score"].sum()) if not team.empty else 0,
            )
        else:
            c1, c2, c3 = st.columns(3)
            c1.metric("Team SC", f"${team_sc_home:,.0f}")
            c2.metric("Recruits", int(team["recruit"].sum()) if not team.empty else 0)
            c3.metric("Activities", int(team["Total_Score"].sum()) if not team.empty else 0)

    st.markdown("### 快速打卡")

    @st.fragment
    def _quick_checkin():
        with st.form("quick_checkin", clear_on_submit=True):
            if MOBILE:
                d = st.date_input("日期", value=datetime.date.today())
                t = st.selectbox("活動種類", ACTIVITY_TYPES)
                n = st.text_area(
                    "重點備註",
                    height=100,
                    placeholder="客戶名 / 下一步 / 結果…",
                )
            else:
                c1, c2 = st.columns([1, 2])
                with c1:
                    d = st.date_input("日期", value=datetime.date.today())
                    t = st.selectbox("活動種類", ACTIVITY_TYPES)
                with c2:
                    n = st.text_area(
                        "重點備註（可簡短）",
                        height=120,
                        placeholder="客戶名 / 下一步 / 結果…",
                    )
            if st.form_submit_button("提交打卡", type="primary", use_container_width=True):
                if n.strip():
                    add_act(user, d, t, n.strip())
                    st.toast("打卡成功！", icon="✅")
                    st.rerun(scope="app")
                else:
                    st.error("請寫至少一句備註")

    _quick_checkin()

    st.markdown("### 團隊最新動態")
    acts = get_all_act().head(5)
    users_df = get_clean_users()
    if acts.empty:
        st.info("暫時未有動態 — 去「打卡」寫第一筆啦。")
    else:
        acts = pd.merge(acts, users_df[["username", "avatar"]], on="username", how="left")
        for _, row in acts.iterrows():
            act_date = pd.to_datetime(row["date"]).strftime("%Y-%m-%d")
            avatar_url = (
                row["avatar"]
                if isinstance(row.get("avatar"), str) and str(row["avatar"]).startswith("http")
                else f"https://ui-avatars.com/api/?background=d4af37&color=fff&name={row['username']}"
            )
            card_class, badge_class = get_activity_style(row["type"])
            note_html = str(row["note"]).replace("\n", "<br>")
            st.markdown(
                f"""
                <div class="activity-card {card_class}">
                  <div class="act-header">
                    <div style="display:flex;align-items:center;">
                      <img src="{avatar_url}" class="act-avatar">
                      <div><div class="act-name">{row['username']}</div>
                      <div class="act-time">{act_date}</div></div>
                    </div>
                    <div class="act-badge {badge_class}">{row['type']}</div>
                  </div>
                  <div class="act-content">{note_html}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def page_checkin():
    st.markdown("## 打卡中心")
    st.caption("用範本記面談重點，提交後即時出現喺團隊動態。")
    tab_new, tab_hist = st.tabs(["立即打卡", "團隊動態"])

    with tab_new:
        t = st.selectbox("活動種類", ACTIVITY_TYPES, key="ci_type")
        default_note = get_note_template(t)
        with st.form("checkin_form", clear_on_submit=True):
            d = st.date_input("日期", value=datetime.date.today())
            n = st.text_area("內容詳情", value=default_note, height=200)
            if st.form_submit_button("提交打卡", type="primary", use_container_width=True):
                add_act(st.session_state["user"], d, t, n)
                st.toast("提交成功！", icon="✅")

    with tab_hist:
        users_df = get_clean_users()
        filter_user = st.multiselect(
            "篩選同事", options=users_df["username"].unique().tolist() if not users_df.empty else []
        )
        all_acts = get_all_act()
        if all_acts.empty:
            st.info("暫無動態")
            return
        all_acts = pd.merge(all_acts, users_df[["username", "avatar"]], on="username", how="left")
        display_df = all_acts[all_acts["username"].isin(filter_user)] if filter_user else all_acts
        for _, row in display_df.iterrows():
            act_date = pd.to_datetime(row["date"]).strftime("%Y-%m-%d")
            act_time = (
                pd.to_datetime(row["timestamp"]).strftime("%H:%M") if row.get("timestamp") else ""
            )
            avatar_url = (
                row["avatar"]
                if isinstance(row.get("avatar"), str) and str(row["avatar"]).startswith("http")
                else f"https://ui-avatars.com/api/?background=random&color=fff&name={row['username']}"
            )
            card_class, badge_class = get_activity_style(row["type"])
            st.markdown(
                f"""
                <div class="activity-card {card_class}">
                  <div class="act-header">
                    <div style="display:flex;align-items:center;">
                      <img src="{avatar_url}" class="act-avatar">
                      <div><div class="act-name">{row['username']}</div>
                      <div class="act-time">{act_date} {act_time}</div></div>
                    </div>
                    <div class="act-badge {badge_class}">{row['type']}</div>
                  </div>
                  <div class="act-content">{str(row['note']).replace(chr(10), '<br>')}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def _esc(s) -> str:
    return (
        str(s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _avatar_url(row) -> str:
    av = row.get("avatar", "")
    name = str(row.get("username", "U"))
    if isinstance(av, str) and (av.startswith("http") or av.startswith("data:image")):
        return av
    return f"https://ui-avatars.com/api/?name={urllib.parse.quote(name)}&background=d4af37&color=fff&size=128"


def render_dashboard_kpis(team_sc: float, team_rec: int, team_act: int) -> None:
    """KPI tiles via components.html (Streamlit markdown drops custom CSS)."""
    html = f"""
<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  html, body {{ margin:0; padding:0; overflow:visible; background:transparent;
    font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; }}
  .wrap {{ display:grid; grid-template-columns:1fr; gap:10px; padding-bottom:4px; }}
  @media(min-width:720px) {{ .wrap {{ grid-template-columns:repeat(3,1fr); }} }}
  .kpi {{ background:#fff; border:1px solid #E6E8EC; border-radius:14px;
          padding:14px 14px 16px; box-shadow:0 6px 18px rgba(28,36,48,.05); }}
  .k {{ font-size:11px; letter-spacing:.08em; text-transform:uppercase; color:#6B7280; margin-bottom:6px; }}
  .v {{ font-family:Georgia,'Times New Roman',serif; font-size:30px; color:#1C2430;
        line-height:1.25; padding-bottom:2px; word-break:break-word; }}
</style></head><body>
<div class="wrap">
  <div class="kpi"><div class="k">Team SC</div><div class="v">${team_sc:,.0f}</div></div>
  <div class="kpi"><div class="k">Recruits</div><div class="v">{team_rec}</div></div>
  <div class="kpi"><div class="k">Activities</div><div class="v">{team_act}</div></div>
</div>
</body></html>
"""
    # Mobile stacks 3 cards — give enough height so Activities digits are not clipped
    components.html(html, height=280 if MOBILE else 120, scrolling=False)


def render_rank_cards(
    df: pd.DataFrame,
    *,
    mode: str = "mdrt",
    month_label: str = "",
) -> None:
    """
    Card-style leaderboard.
    mode='mdrt'   → 2027 MDRT temporary progress vs MDRT_TARGET
    mode='monthly'→ progress vs that month's team max (min scale 20k)
    """
    ranked = df.sort_values(by="fyc", ascending=False).reset_index(drop=True)
    month_scale = float(ranked["fyc"].max()) if not ranked.empty else 0.0
    if mode == "monthly":
        bar_target = max(month_scale, 20000.0)
        target_label_fn = lambda _fyc: f"{month_label} 本月排名" if month_label else "本月排名"
    else:
        bar_target = float(MDRT_TARGET)
        target_label_fn = lambda _fyc: f"2027 MDRT 目標 ${MDRT_TARGET:,.0f}"

    parts = []
    for i, row in ranked.iterrows():
        rank = i + 1
        fyc = float(row["fyc"])
        pct = min(max(fyc / bar_target * 100, 0), 100) if bar_target else 0
        rank_bg = (
            "linear-gradient(135deg,#F0D078,#C5A028)"
            if rank == 1
            else "linear-gradient(135deg,#EEF1F4,#B8C0C8)"
            if rank == 2
            else "linear-gradient(135deg,#F0D3B8,#C4895A)"
            if rank == 3
            else "#F3F1EB"
        )
        border = "#E2C56A" if rank == 1 else "#E6E8EC"
        bg = "linear-gradient(145deg,#FFFDF5 0%,#FFFFFF 55%)" if rank == 1 else "#FFFFFF"
        medal = str(rank)
        name = _esc(row["username"])
        av = _esc(_avatar_url(row))
        recruit = int(row.get("recruit", 0) or 0)
        score = int(row.get("Total_Score", 0) or 0)
        chip = ""
        if mode == "mdrt" and pct >= 100:
            chip = (
                '<span style="display:inline-block;margin-left:6px;background:#F7F1DE;color:#7A6420;'
                'border-radius:999px;padding:2px 8px;font-size:11px;font-weight:600;">MDRT</span>'
            )
        elif mode == "monthly" and rank == 1 and fyc > 0:
            chip = (
                '<span style="display:inline-block;margin-left:6px;background:#F7F1DE;color:#7A6420;'
                'border-radius:999px;padding:2px 8px;font-size:11px;font-weight:600;">月冠</span>'
            )
        top_bar = (
            '<div style="position:absolute;left:0;top:0;right:0;height:4px;'
            'background:linear-gradient(90deg,#D4AF37,#F0D078,#D4AF37);"></div>'
            if rank == 1
            else ""
        )
        sub = target_label_fn(fyc)
        pct_text = f"{pct:.0f}%" if mode == "mdrt" else (f"#{rank}" if fyc > 0 else "—")
        parts.append(
            "<div style='position:relative;background:"
            + bg
            + ";border:1px solid "
            + border
            + ";border-radius:16px;padding:14px 14px 12px;margin:0 0 12px 0;"
            + "box-shadow:0 8px 22px rgba(28,36,48,.06);overflow:hidden;'>"
            + top_bar
            + "<div style='display:flex;align-items:center;gap:12px;'>"
            + "<div style='width:34px;height:34px;border-radius:50%;display:flex;align-items:center;"
            + "justify-content:center;font-weight:800;font-size:14px;background:"
            + rank_bg
            + ";color:#1C2430;flex-shrink:0;'>"
            + medal
            + "</div>"
            + f"<img src='{av}' alt='{name}' style='width:48px;height:48px;border-radius:50%;"
            + "object-fit:cover;border:2px solid #F0E6C4;flex-shrink:0;background:#eee;'>"
            + "<div style='flex:1;min-width:0;'>"
            + f"<div style='font-weight:700;font-size:16px;color:#1C2430;'>{name}{chip}</div>"
            + f"<div style=\"font-family:Georgia,serif;font-size:22px;color:#1C2430;"
            + f"line-height:1.2;margin-top:2px;\">${fyc:,.0f}</div>"
            + f"<div style='color:#6B7280;font-size:12px;margin-top:2px;'>{sub}</div>"
            + "</div>"
            + f"<div style='flex-shrink:0;text-align:right;font-weight:800;font-size:17px;"
            + f"color:#9A7B1A;min-width:52px;'>{pct_text}</div>"
            + "</div>"
            + "<div style='margin-top:10px;height:9px;border-radius:999px;background:#ECE7DC;overflow:hidden;'>"
            + f"<div style='height:100%;width:{pct:.1f}%;border-radius:999px;"
            + "background:linear-gradient(90deg,#D4AF37,#F0D078);'></div></div>"
            + "<div style='display:flex;gap:14px;margin-top:10px;color:#6B7280;font-size:13px;'>"
            + f"<span>招募 <strong style='color:#1C2430;'>{recruit}</strong></span>"
            + f"<span>活動分 <strong style='color:#1C2430;'>{score}</strong></span>"
            + "</div></div>"
        )

    n = max(len(parts), 1)
    height = 28 + n * 152
    html = (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<style>html,body{margin:0;padding:2px 0 8px;overflow:visible;"
        "font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;"
        "background:transparent;}</style></head><body>"
        + "".join(parts)
        + "</body></html>"
    )
    components.html(html, height=height, scrolling=False)


def render_leaderboard(df: pd.DataFrame) -> None:
    render_rank_cards(df, mode="mdrt")


def page_dashboard():
    st.markdown(f"## Dashboard · {st.session_state['user']}")
    if is_leader:
        with st.expander("每週戰報生成器（Leader）", expanded=False):
            if st.button("生成上週結算戰報"):
                wk_df, start, end = get_last_week_data()
                max_score = wk_df["wk_score"].max() if not wk_df.empty else 0
                winners = (
                    wk_df[wk_df["wk_score"] == max_score]
                    if not wk_df.empty and max_score > 0
                    else pd.DataFrame()
                )
                losers = wk_df[wk_df["wk_count"] < WEEKLY_MIN_ACTS] if not wk_df.empty else pd.DataFrame()
                penalty_total = len(losers) * WEEKLY_PENALTY
                prize = (
                    penalty_total / len(winners)
                    if penalty_total > 0 and not winners.empty
                    else (WEEKLY_PENALTY / len(winners) if not winners.empty else 0)
                )
                report = f"📅 *【TIM TEAM 上週戰報 ({start} ~ {end})】*\n\n"
                if max_score > 0 and not winners.empty:
                    report += f"🏆 *上週 MVP (獨得獎金 ${int(prize)}):*\n"
                    for _, w in winners.iterrows():
                        report += f"👑 *{w['username']}* ({int(w['wk_score'])}分)\n"
                    report += (
                        f"_多謝 {len(losers)} 位同事贊助獎金池！_\n\n"
                        if penalty_total > 0
                        else "_全員達標！Tim 自掏 $100 請飲茶！_\n\n"
                    )
                else:
                    report += "⚠️ *上週全軍覆沒？* 無人開工？\n\n"
                if not losers.empty:
                    report += f"💸 *【罰款名單 - 每人 ${WEEKLY_PENALTY}】*\n"
                    for _, l in losers.iterrows():
                        report += f"❌ {l['username']} (得 {int(l['wk_count'])} 次)\n"
                else:
                    report += "✅ *上週無人罰款！Excellent！*\n"
                report += "\n📊 *詳細戰況：*\n"
                if not wk_df.empty:
                    for _, row in wk_df.sort_values(by="wk_score", ascending=False).iterrows():
                        report += f"{row['username']}: {int(row['wk_score'])}分 ({int(row['wk_count'])}次)\n"
                report += "\n🚀 *新一週由零開始，大家加油！*"
                st.code(report)
                st.link_button("Send to WhatsApp", f"https://wa.me/?text={urllib.parse.quote(report)}")

    df = get_data("Yearly")
    calc_ytd = float(df["fyc"].sum()) if not df.empty else 0.0
    team_sc = get_team_sc(calc_ytd)
    team_rec = int(df["recruit"].sum()) if not df.empty else 0
    team_act = int(df["Total_Score"].sum()) if not df.empty else 0
    render_dashboard_kpis(team_sc, team_rec, team_act)

    if is_leader:
        with st.expander("編輯 Team SC（Year to date）", expanded=False):
            st.caption(
                f"Dashboard 顯示嘅 Team SC 以呢度輸入為準。"
                f"系統計算出嚟嘅成員 YTD 加總（參考）：${calc_ytd:,.0f}"
            )
            sc_in = st.number_input(
                "Team SC（YTD）",
                min_value=0.0,
                value=float(team_sc),
                step=1000.0,
                format="%.0f",
                key="team_sc_input",
            )
            if st.button("儲存 Team SC", type="primary", use_container_width=True):
                if set_team_sc(float(sc_in)):
                    st.toast(f"Team SC 已更新為 ${float(sc_in):,.0f}", icon="✅")
                    st.rerun()
                else:
                    st.error("儲存失敗，請稍後再試")

    st.markdown("### Leaderboard")
    st.caption(f"2027 MDRT 目標 ${MDRT_TARGET:,.0f} 暫時進度")
    user_list = df["username"].tolist() if not df.empty else []
    progress_map = get_mdrt_progress_map()
    if df.empty:
        st.info("暫無成員數據")
    else:
        lb = df.copy()
        lb["fyc"] = lb["username"].map(lambda u: lookup_mdrt_progress(u, progress_map))
        render_leaderboard(lb)

    if is_leader:
        with st.expander("編輯各人 2027 MDRT 暫時進度", expanded=False):
            st.caption(
                "呢度輸入每位同事嘅計劃 bonus & other credit 總數"
                f"（計入 2027 MDRT 目標 ${MDRT_TARGET:,.0f}）。"
            )
            if not user_list:
                st.info("暫無成員可編輯")
            else:
                for uname in user_list:
                    st.number_input(
                        f"{uname}",
                        min_value=0.0,
                        value=float(lookup_mdrt_progress(uname, progress_map)),
                        step=1000.0,
                        format="%.0f",
                        key=f"mdrt_progress_{uname}",
                    )
                if st.button("儲存全部暫時進度", type="primary", use_container_width=True):
                    for uname in user_list:
                        set_mdrt_progress(
                            uname, float(st.session_state.get(f"mdrt_progress_{uname}", 0))
                        )
                    st.toast("MDRT 暫時進度已更新", icon="✅")
                    st.rerun()

        with st.expander("手動調整個人業績 / 招募（備用）"):
            st.caption("日常請用「業績報告同步」上傳 Daily / MDRT report。呢度只係後備人手修正。")
            c_a, c_b, c_c = st.columns(3)
            tgt = c_a.selectbox("User", user_list)
            mth = c_b.selectbox("Month", [f"2026-{i:02d}" for i in range(1, 13)])
            amt = c_c.number_input("Amount", step=1000)
            if st.button("Save FYC"):
                upd_fyc(tgt, mth, amt, source="manual")
                st.toast("Saved!", icon="✅")
                st.rerun()
            st.divider()
            c_d, c_e = st.columns(2)
            tgt_r = c_d.selectbox("User", user_list, key="r1")
            rec = c_e.number_input("Recruits", step=1)
            if st.button("Save Recruit"):
                upd_rec(tgt_r, rec)
                st.toast("Saved!", icon="✅")
                st.rerun()


def _render_drive_report_box(
    *,
    title: str,
    report_kind: str,
    folder_id: str,
    month_fallback: str,
    amount_label: str,
    key_prefix: str,
) -> None:
    """Preview / sync newest file from one Drive inbox."""
    st.markdown(f"##### {title}")
    if not folder_id:
        st.info("請先儲存呢個資料夾 ID。")
        return

    files = list_inbox_files(folder_id=folder_id, limit=6)
    err = st.session_state.get("_iris_drive_error")
    if err:
        st.error(
            f"讀取 Drive 失敗：{err}\n\n"
            "常見原因：未將資料夾共用俾 service account，或 Folder ID 錯。"
        )
    if not files:
        st.warning(
            "資料夾未見 Excel/CSV/PDF。請將對應 report 放進去再試。"
            + ("（MDRT Progress 支援 PDF）" if report_kind == "mdrt" else "")
        )
        return

    st.dataframe(
        [
            {
                "檔名": f.get("name"),
                "更新時間": str(f.get("modifiedTime", ""))[:19].replace("T", " "),
            }
            for f in files
        ],
        use_container_width=True,
        hide_index=True,
    )
    latest = files[0]
    c1, c2 = st.columns(2)
    do_preview = c1.button("預覽最新檔", use_container_width=True, key=f"{key_prefix}_preview")
    do_sync = c2.button(
        "同步最新檔到系統",
        type="primary",
        use_container_width=True,
        key=f"{key_prefix}_sync",
    )
    if not (do_preview or do_sync):
        return

    try:
        raw = download_file(latest["id"])
        raw_df = _iris_call('load_iris_bytes', raw, latest.get("name", "report.xlsx"))
        preview, detected = _iris_call('auto_build_preview', 
            raw_df,
            month_fallback,
            filename=latest.get("name", ""),
            report_kind=report_kind,
        )
        _store_iris_preview(preview)
        st.caption(
            f"報告類型={detected.get('report_kind') or report_kind} · "
            f"姓名={detected.get('agent') or '—'} · "
            f"編號={detected.get('code') or '—'} · "
            f"金額欄={detected.get('mdrt_credit') or detected.get('fyc') or '—'} · "
            f"月份={detected.get('month') or month_fallback}"
        )
        summary = _iris_call('preview_summary', preview)
        st.write(
            f"團隊可同步：**{summary['matched_rows']}** 列 "
            f"（{summary['matched_users']} 人）· "
            f"其他同事將忽略：**{summary['unmapped_agents']}** 個編號"
        )
        show_all = st.checkbox(
            "顯示全部（含非團隊）", value=False, key=f"{key_prefix}_show_all"
        )
        matched_view = preview[preview["matched"]]
        view = preview if show_all else matched_view
        if matched_view.empty:
            st.info("而家未對應到任何團隊成員。請去「② 顧問對應」只加你團隊。")
        st.dataframe(
            view if not view.empty else preview.head(20),
            use_container_width=True,
            hide_index=True,
            column_config={
                "amount": st.column_config.NumberColumn(amount_label, format="$%.0f"),
                "matched": "團隊成員",
            },
        )
        if do_sync:
            if summary["matched_rows"] == 0:
                st.error("未有團隊成員可同步。請先完成顧問對應。")
            else:
                result = _iris_call('apply_report_sync', 
                    preview,
                    st.session_state["user"],
                    latest.get("name", "drive.xlsx"),
                    report_kind=report_kind,
                )
                if report_kind == "mdrt":
                    mark_mdrt_file_synced(latest["id"])
                    st.success(
                        f"已同步 MDRT Progress「{latest.get('name')}」： "
                        f"暫時進度 {result.get('mdrt_updated', result['updated'])} 筆 · "
                        f"{result['matched_users']} 位團隊成員"
                    )
                else:
                    mark_daily_file_synced(latest["id"])
                    st.success(
                        f"已同步 Daily Production「{latest.get('name')}」： "
                        f"MTD_Comp_FYC {result['updated']} 筆 · "
                        f"{result['matched_users']} 位團隊成員 · "
                        f"月份 {', '.join(result.get('months') or []) or '—'}"
                    )
                st.balloons()
    except Exception as e:
        st.error(f"處理失敗：{e}")


def page_iris_sync():
    st.markdown("## 業績報告同步")
    st.markdown(
        """
        <div class="iris-banner">
          <strong>兩份報告 → 兩個數字</strong><br>
          <b>Daily production report</b> → 讀 <b>MTD_Comp_FYC</b>（唔用 MTD_Sub_FYC）→ 每月業績 FYC<br>
          <b>MDRT Progress Report</b> → 讀 <b>Total Credit eligible for MDRT</b> → Leaderboard 暫時進度<br>
          <b>Team SC</b> 仍然喺 Dashboard 人手輸入<br>
          只需對應 TIM TEAM 成員；其他同事會自動忽略。
        </div>
        """,
        unsafe_allow_html=True,
    )

    tab_drive, tab_map, tab_sync, tab_log = st.tabs(
        ["① Drive 自動同步（推薦）", "② 顧問對應", "③ 手動上傳", "④ 同步紀錄"]
    )

    with tab_drive:
        sa = service_account_email()
        st.markdown("#### 一次性設定（兩個 Drive 資料夾）")
        st.markdown(
            f"""
1. Google Drive 開 **兩個** 資料夾，例如  
   **`TIM TEAM Daily Production`** 同 **`TIM TEAM MDRT Progress`**
2. 兩個資料夾都共用俾呢個電郵（編輯者）：  
   `{sa or "（讀唔到 service account，請檢查 Streamlit secrets）"}`
3. 分別複製 Folder ID（或完整 folders/ 連結）貼下面儲存
4. 之後：Daily report（Excel/CSV）放第一個資料夾；MDRT Progress Report（**PDF 或 Excel**）放第二個
            """
        )
        d1, d2 = st.columns(2)
        with d1:
            daily_in = st.text_input(
                "Daily Production 資料夾",
                value=get_daily_folder_id(),
                placeholder="Folder ID 或完整 URL",
                key="daily_folder_input",
            )
            if st.button("儲存 Daily 資料夾", type="primary", use_container_width=True):
                fid = _normalize_folder_id(daily_in)
                if not fid:
                    st.error("請貼上有效嘅 Folder ID 或 Drive 連結")
                elif save_daily_folder_id(fid):
                    st.toast(f"已儲存 Daily 資料夾：{fid[:12]}…", icon="✅")
                    st.rerun()
                else:
                    st.error("儲存失敗。可再試一次，或按側欄「重新整理數據」後再儲存。")
        with d2:
            mdrt_in = st.text_input(
                "MDRT Progress 資料夾",
                value=get_mdrt_folder_id(),
                placeholder="Folder ID 或完整 URL",
                key="mdrt_folder_input",
            )
            if st.button("儲存 MDRT 資料夾", type="primary", use_container_width=True):
                fid = _normalize_folder_id(mdrt_in)
                if not fid:
                    st.error("請貼上有效嘅 Folder ID 或 Drive 連結")
                elif save_mdrt_folder_id(fid):
                    st.toast(f"已儲存 MDRT 資料夾：{fid[:12]}…", icon="✅")
                    st.rerun()
                else:
                    st.error("儲存失敗。可再試一次，或按側欄「重新整理數據」後再儲存。")

        st.divider()
        month_drive = st.selectbox(
            "Daily report 若無月份欄，使用此月份",
            [f"2026-{i:02d}" for i in range(1, 13)],
            index=max(0, datetime.date.today().month - 1),
            key="iris_drive_month",
        )

        _render_drive_report_box(
            title="A. Daily production → 每月 FYC（MTD_Comp_FYC）",
            report_kind="daily",
            folder_id=get_daily_folder_id(),
            month_fallback=month_drive,
            amount_label="MTD_Comp_FYC",
            key_prefix="drv_daily",
        )
        st.divider()
        _render_drive_report_box(
            title="B. MDRT Progress → Leaderboard 暫時進度",
            report_kind="mdrt",
            folder_id=get_mdrt_folder_id(),
            month_fallback=month_drive,
            amount_label="Total Credit eligible for MDRT",
            key_prefix="drv_mdrt",
        )

    users = get_clean_users()
    member_names = (
        users[users["role"] == "Member"]["username"].tolist() if not users.empty else []
    )

    with tab_map:
        st.markdown("#### 只對應你團隊（其他 Iris 同事可忽略）")
        st.caption(
            "你張報表入面嘅數字（如 30947）多數係 Iris 顧問編號。"
            "只需為 TIM TEAM 成員建立對應；其餘編號唔使理。"
        )

        last_preview = _load_iris_preview()
        pending = _iris_call('unmapped_agents', last_preview) if last_preview is not None else pd.DataFrame()
        if not pending.empty:
            st.markdown("##### 從最新預覽快速對應")
            st.dataframe(
                pending.head(30),
                use_container_width=True,
                hide_index=True,
                column_config={"amount": st.column_config.NumberColumn("金額", format="$%.0f")},
            )
            with st.form("quick_map_form", clear_on_submit=True):
                options = []
                for _, r in pending.iterrows():
                    code = str(r.get("iris_code") or "").strip()
                    name = str(r.get("iris_name") or "").strip()
                    label = code or name
                    if label:
                        options.append(label)
                pick = st.selectbox("揀一個 Iris 編號／姓名", options)
                user_q = st.selectbox("對應到系統 Username", member_names, key="quick_map_user")
                if st.form_submit_button("儲存呢個對應", type="primary"):
                    if pick and user_q:
                        if re.fullmatch(r"\d{4,}", str(pick)):
                            _iris_call('save_agent_mapping', "", str(pick), user_q, "quick-map")
                        else:
                            _iris_call('save_agent_mapping', str(pick), "", user_q, "quick-map")
                        st.toast(f"已對應 {pick} → {user_q}", icon="✅")
                        st.rerun()

        st.markdown("##### 手動新增對應")
        with st.form("map_form", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            iris_name = c1.text_input("Iris 姓名（可留空）", placeholder="報表有姓名先填")
            iris_code = c2.text_input("Iris 編號", placeholder="例如 30947")
            username = c3.selectbox("系統 Username", member_names)
            notes = st.text_input("備註（可選）")
            if st.form_submit_button("儲存對應", type="primary"):
                if iris_name or iris_code:
                    _iris_call('save_agent_mapping', iris_name, iris_code, username, notes)
                    st.toast("對應已儲存", icon="✅")
                    st.rerun()
                else:
                    st.error("請至少填 Iris 姓名或編號")

        amap = _iris_call('get_agent_map', )
        if amap.empty:
            st.info("未有對應。建議先「預覽最新檔」，再用上面快速對應你團隊。")
        else:
            st.markdown("##### 已儲存對應")
            st.dataframe(amap, use_container_width=True, hide_index=True)

    with tab_sync:
        report_kind_manual = st.radio(
            "報告類型",
            ["daily", "mdrt"],
            format_func=lambda k: (
                "Daily production（MTD_Comp_FYC → 每月 FYC）"
                if k == "daily"
                else "MDRT Progress（Total Credit eligible for MDRT → 暫時進度）"
            ),
            horizontal=False,
            key="manual_report_kind",
        )
        c_dl1, c_dl2 = st.columns(2)
        with c_dl1:
            st.download_button(
                "下載 Daily 範本 CSV",
                data=sample_daily_template_csv(),
                file_name="daily_production_template.csv",
                mime="text/csv",
            )
        with c_dl2:
            st.download_button(
                "下載 MDRT 範本 CSV",
                data=sample_mdrt_template_csv(),
                file_name="mdrt_progress_template.csv",
                mime="text/csv",
            )
        st.caption("檔案上限 8MB。太大請改用上面 Drive 資料夾同步，避免 Cloud Oh no。")
        if "manual_iris_upload_nonce" not in st.session_state:
            st.session_state["manual_iris_upload_nonce"] = 0
        up_nonce = int(st.session_state.get("manual_iris_upload_nonce") or 0)
        uploaded = st.file_uploader(
            "上傳報告檔（≤8MB）",
            type=["xlsx", "xls", "csv", "pdf"],
            help="Daily：Excel/CSV（MTD_Comp_FYC）；MDRT：Excel/CSV/PDF。太大請用 Drive 同步。",
            key=f"manual_iris_upload_{up_nonce}",
        )
        c_clear, _ = st.columns([1, 2])
        with c_clear:
            if st.button("清除／換另一份檔", key=f"manual_iris_clear_{up_nonce}"):
                st.session_state["manual_iris_upload_nonce"] = up_nonce + 1
                st.session_state.pop("_iris_last_preview", None)
                st.session_state["_iris_last_preview_rows"] = []
                st.rerun()
        default_month = datetime.date.today().strftime("%Y-%m")
        month_choice = st.selectbox(
            "Daily report 若無月份欄，使用此月份",
            [f"2026-{i:02d}" for i in range(1, 13)],
            index=max(0, datetime.date.today().month - 1),
            key="manual_month_choice",
        )

        if not uploaded:
            return

        try:
            raw, up_name = _bytes_from_upload(
                uploaded, max_bytes=_IRIS_UPLOAD_MAX_BYTES
            )
            raw_df = _iris_call("load_iris_bytes", raw, up_name)
            del raw
        except Exception as e:
            st.error(f"無法讀取檔案：{e}")
            return

        try:
            st.markdown("#### 原始預覽")
            st.dataframe(raw_df.head(20), use_container_width=True)

            detected = _iris_call("detect_columns", raw_df)
            auto_kind = _iris_call("detect_report_kind", raw_df, up_name)
            if auto_kind in {"daily", "mdrt"} and auto_kind != report_kind_manual:
                st.warning(
                    f"檔案欄位較似 **{auto_kind}** report；你揀咗 **{report_kind_manual}**。"
                    "如果預覽金額唔對，請改上面報告類型。"
                )
            cols = [str(c) for c in raw_df.columns]
            c1, c2 = st.columns(2)
            c3, c4 = st.columns(2)
            col_agent = c1.selectbox(
                "姓名欄",
                ["（無）"] + cols,
                index=(cols.index(detected["agent"]) + 1)
                if detected["agent"] in cols
                else 0,
            )
            col_code = c2.selectbox(
                "編號欄",
                ["（無）"] + cols,
                index=(cols.index(detected["code"]) + 1)
                if detected["code"] in cols
                else 0,
            )

            if report_kind_manual == "mdrt":
                credit_default = (
                    cols.index(detected["mdrt_credit"])
                    if detected.get("mdrt_credit") in cols
                    else 0
                )
                col_amount = c3.selectbox(
                    "暫時進度欄（Total Credit eligible for MDRT）",
                    cols,
                    index=credit_default,
                )
                st.caption("會寫入 Leaderboard 2027 MDRT 暫時進度。Team SC 仍要人手入。")
                preview = _iris_call(
                    "build_mdrt_preview",
                    raw_df,
                    None if col_agent == "（無）" else col_agent,
                    None if col_code == "（無）" else col_code,
                    col_amount,
                )
                amount_label = "Total Credit eligible for MDRT"
            else:
                fyc_default = (
                    cols.index(detected["fyc"]) if detected["fyc"] in cols else 0
                )
                col_amount = c3.selectbox(
                    "當月 FYC 欄（MTD_Comp_FYC）",
                    cols,
                    index=fyc_default,
                    help="唔好揀 Monthly Submission",
                )
                col_month = c4.selectbox(
                    "月份欄",
                    ["（用上方選擇）"] + cols,
                    index=(cols.index(detected["month"]) + 1)
                    if detected["month"] in cols
                    else 0,
                )
                st.caption("會寫入每月業績 FYC。唔會改 Leaderboard 暫時進度／Team SC。")
                preview = _iris_call(
                    "build_sync_preview",
                    raw_df,
                    None if col_agent == "（無）" else col_agent,
                    None if col_code == "（無）" else col_code,
                    col_amount,
                    None if col_month == "（用上方選擇）" else col_month,
                    month_choice or default_month,
                    col_ytd=None,
                )
                amount_label = "MTD_Comp_FYC"

            _store_iris_preview(preview)
            st.markdown("#### 對應結果")
            summary = _iris_call("preview_summary", preview)
            st.write(
                f"團隊可同步：**{summary['matched_rows']}** 列 · "
                f"其他同事將忽略：**{summary['unmapped_agents']}** 個編號"
            )
            st.dataframe(
                preview,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "amount": st.column_config.NumberColumn(
                        amount_label, format="$%.0f"
                    ),
                    "matched": "團隊成員",
                },
            )
            if summary["unmapped_agents"] > 0:
                st.caption(
                    "未對應 = 非團隊／未設定，同步時會自動略過。只需對應 TIM TEAM 成員。"
                )
                with st.expander("查看將被忽略嘅編號"):
                    st.dataframe(
                        _iris_call("unmapped_agents", preview),
                        use_container_width=True,
                        hide_index=True,
                    )

            if st.button(
                "確認同步到系統",
                type="primary",
                disabled=summary["matched_rows"] == 0,
            ):
                result = _iris_call(
                    "apply_report_sync",
                    preview,
                    st.session_state["user"],
                    up_name,
                    report_kind=report_kind_manual,
                )
                if report_kind_manual == "mdrt":
                    st.success(
                        f"MDRT 暫時進度已更新："
                        f"{result.get('mdrt_updated', result['updated'])} 筆 · "
                        f"{result['matched_users']} 位團隊成員"
                    )
                else:
                    st.success(
                        f"每月 FYC 已更新：{result['updated']} 筆 · "
                        f"{result['matched_users']} 位團隊成員 · "
                        f"月份 {', '.join(result['months']) or '—'}"
                    )
                st.balloons()
                # Reset uploader so the next file can be chosen immediately
                st.session_state["manual_iris_upload_nonce"] = (
                    int(st.session_state.get("manual_iris_upload_nonce") or 0) + 1
                )
                st.session_state.pop("_iris_last_preview", None)
                st.session_state["_iris_last_preview_rows"] = []
                st.rerun()
        except Exception as e:
            st.session_state.pop("_iris_last_preview", None)
            st.session_state["_iris_last_preview_rows"] = []
            st.error(f"處理上傳失敗（已清除暫存）：{e}")
            return

    with tab_log:
        log = read_data("iris_sync_log")
        if log.empty:
            st.info("未有同步紀錄")
        else:
            st.dataframe(
                log.sort_values(by="id", ascending=False),
                use_container_width=True,
                hide_index=True,
            )


def page_monthly():
    st.markdown("## 每月業績")
    m = st.selectbox(
        "月份",
        [f"2026-{i:02d}" for i in range(1, 13)],
        index=datetime.date.today().month - 1,
    )
    df = get_data(month=m)
    if df.empty:
        st.info("本月暫無數據 — Leader 可用「業績報告同步」匯入 Daily production。")
        return

    month_total = float(df["fyc"].sum())
    leaders = df.sort_values(by="fyc", ascending=False)
    top_name = str(leaders.iloc[0]["username"]) if not leaders.empty else "—"
    top_fyc = float(leaders.iloc[0]["fyc"]) if not leaders.empty else 0.0

    # Monthly summary strip
    summary_html = f"""
<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
  body{{margin:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:transparent;}}
  .box{{background:linear-gradient(145deg,#1C2430,#2C3A4E);color:#F8F4EA;border-radius:16px;padding:16px 16px 14px;}}
  .k{{font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:#D4AF37;margin-bottom:6px;}}
  .v{{font-family:Georgia,serif;font-size:30px;line-height:1.2;}}
  .s{{margin-top:8px;color:rgba(248,244,234,.78);font-size:13px;}}
</style></head><body>
<div class="box">
  <div class="k">{m} 團隊 MTD_Comp_FYC</div>
  <div class="v">${month_total:,.0f}</div>
  <div class="s">月冠：{ _esc(top_name) } · ${top_fyc:,.0f}</div>
</div>
</body></html>
"""
    components.html(summary_html, height=120, scrolling=False)

    st.markdown("### 本月排行")
    st.caption(
        "按該月 **MTD_Comp_FYC**（Completion）排名 · 唔用 MTD_Sub_FYC · "
        "進度條對比本月最高（至少 $20,000 尺度）。"
        "若數字唔啱，請去「業績報告同步」重新同步最新 Daily production。"
    )
    render_rank_cards(df, mode="monthly", month_label=m)


def page_year_goal():
    st.markdown("## 2026 年度挑戰")
    q1_df = get_q1_data()
    st.markdown(
        f"""
        <div class="challenge-header-box">
          <strong>Q1 {Q1_TARGET:,} Challenge（1/1 – 31/3）</strong><br>
          第一季累積 FYC 達 HK$ {Q1_TARGET:,} — MDRT 入場券。
        </div>
        """,
        unsafe_allow_html=True,
    )
    if not q1_df.empty:
        for _, r in q1_df.sort_values(by="q1_total", ascending=False).iterrows():
            progress = min(r["q1_total"] / Q1_TARGET, 1.0) if Q1_TARGET else 0
            st.markdown(
                f"""
                <div class="tt-card" style="margin-bottom:10px;display:flex;gap:14px;align-items:center;">
                  <img src="{r['avatar']}" style="width:52px;height:52px;border-radius:50%;object-fit:cover;">
                  <div style="flex:1;">
                    <div style="font-weight:700;">{r['username']}</div>
                    <div>${r['q1_total']:,.0f}</div>
                    <div class="tt-progress-wrap"><div class="tt-progress-bar" style="width:{progress*100}%;"></div></div>
                    <div class="tt-hint">Target: ${Q1_TARGET:,} ({progress*100:.1f}%)</div>
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
    else:
        st.info("暫無 Q1 業績數據")

    st.markdown("### 年度獎賞")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(
            '<div class="reward-card-premium"><span class="reward-icon">🚀</span>'
            '<p class="reward-title-p">1st MDRT</p><p class="reward-prize-p">$20,000 Cash</p>'
            '<p class="reward-desc-p">首位完成 $512,800 FYC 者獨得</p></div>',
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            '<div class="reward-card-premium"><span class="reward-icon">👑</span>'
            '<p class="reward-title-p">Top FYC 冠軍</p><p class="reward-prize-p">$10,000 Cash</p>'
            '<p class="reward-desc-p">全年業績最高者 (需 Min. 180,000 FYC)</p></div>',
            unsafe_allow_html=True,
        )
    c3, c4 = st.columns(2)
    with c3:
        st.markdown(
            '<div class="reward-card-premium"><span class="reward-icon">✈️</span>'
            '<p class="reward-title-p">招募冠軍</p><p class="reward-prize-p">雙人來回機票</p>'
            '<p class="reward-desc-p">全年招募人數最多者 (需 Min. 2人)</p></div>',
            unsafe_allow_html=True,
        )
    with c4:
        st.markdown(
            '<div class="reward-card-premium"><span class="reward-icon">🍽️</span>'
            '<p class="reward-title-p">Monthly Star</p><p class="reward-prize-p">Tim 請食飯</p>'
            '<p class="reward-desc-p">單月 FYC 最高者 (需 Min. $20k)</p></div>',
            unsafe_allow_html=True,
        )


def page_challenge():
    df, start, end = get_weekly_data()
    st.markdown(f"## 每週挑戰 · {start} ~ {end}")
    st.markdown(
        f"""
        <div class="challenge-header-box">
          <strong>遊戲規則</strong>
          <ul>
            <li>結算：逢星期日晚 23:59</li>
            <li>每週活動少於 <strong>{WEEKLY_MIN_ACTS} 次</strong> → 罰款 ${WEEKLY_PENALTY}</li>
            <li>罰款注入獎金池，由最高分者獨得</li>
          </ul>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if df.empty:
        st.info("本週暫無數據")
        return
    max_score = df["wk_score"].max()
    winners = df[df["wk_score"] == max_score] if max_score > 0 else pd.DataFrame()
    pool = len(df[df["wk_count"] < WEEKLY_MIN_ACTS]) * WEEKLY_PENALTY
    st.markdown(
        f"### Prize Pool: <span style='color:#C5A028'>${pool if pool > 0 else WEEKLY_PENALTY}</span>",
        unsafe_allow_html=True,
    )
    if not winners.empty:
        cols = st.columns(len(winners))
        for idx, row in winners.reset_index().iterrows():
            cols[idx].image(row["avatar"], width=60)
            cols[idx].caption(f"👑 {row['username']}")
    st.dataframe(
        df[["avatar", "username", "wk_score", "wk_count"]].sort_values(
            by="wk_score", ascending=False
        ),
        column_config={
            "avatar": st.column_config.ImageColumn("", width="small"),
            "wk_score": st.column_config.ProgressColumn(
                "Score", format="%d", max_value=max(10, int(max_score) if max_score else 10)
            ),
        },
        use_container_width=True,
        hide_index=True,
    )


def page_recruit():
    st.markdown("## 招募龍虎榜")
    df = get_data("Yearly")
    if df.empty:
        st.info("暫無招募數據")
        return
    st.dataframe(
        df[["avatar", "username", "recruit"]].sort_values(by="recruit", ascending=False),
        column_config={
            "avatar": st.column_config.ImageColumn("Avatar", width="small"),
            "username": "Agent",
            "recruit": st.column_config.ProgressColumn(
                "Recruits", format="%d", min_value=0, max_value=10
            ),
        },
        use_container_width=True,
        hide_index=True,
    )


def _offer_cell_html(val: str) -> str:
    text = _esc(val).replace("\n", "<br>")
    return text if text else "—"


def _offer_col_class(col_name: str, index: int) -> str:
    """Widen 詳情/說明; keep 備註／項目 label columns narrow."""
    name = str(col_name or "").strip()
    if name == "備註":
        return "offer-note-col"
    if name == "項目":
        # 領獎須知等兩欄表：項目窄、說明闊
        return "offer-label-col"
    if index == 0 or name == "產品":
        return "offer-product"
    if name in {"詳情", "說明", "優惠重點", "優惠", "獎賞", "特別獎金"}:
        return "offer-detail-col"
    if name in {"條件", "繳費", "繳費／條件", "合資格要求", "累積首年保費"}:
        return "offer-mid-col"
    return "offer-detail-col"


def _render_offer_catalog(catalog: dict, *, empty_hint: str, accent: str = "#D4AF37") -> None:
    """Render tables in the main Streamlit DOM (not iframe) so mobile always shows content."""
    sections = list((catalog or {}).get("sections") or [])
    if not sections:
        st.warning(empty_hint)
        return

    banner = str((catalog or {}).get("banner", "") or "").strip()
    footnote = str((catalog or {}).get("footnote", "") or "").strip()
    n_rows = sum(len(s.get("rows") or []) for s in sections)
    st.caption(f"{len(sections)} 個分類 · {n_rows} 項")

    if banner:
        st.markdown(
            f'<div class="offer-banner">{_esc(banner)}</div>',
            unsafe_allow_html=True,
        )

    for section in sections:
        title = _esc(section.get("title", ""))
        cols = list(section.get("columns") or [])
        rows = list(section.get("rows") or [])
        if not cols or not rows:
            continue
        col_classes = [_offer_col_class(c, i) for i, c in enumerate(cols)]
        colgroup = "".join(
            f'<col class="{cls}">' for cls in col_classes
        )
        thead = "".join(
            f'<th class="{col_classes[i]}">{_esc(c)}</th>' for i, c in enumerate(cols)
        )
        body_rows = []
        for row in rows:
            cells = list(row) + [""] * max(0, len(cols) - len(row))
            tds = "".join(
                f'<td class="{col_classes[j]}">'
                f"{_offer_cell_html(str(cells[j] if j < len(cells) else ''))}</td>"
                for j in range(len(cols))
            )
            body_rows.append(f"<tr>{tds}</tr>")
        st.markdown(
            f"""
            <div class="offer-section">
              <div class="offer-section-title">
                <span class="offer-section-bar" style="background:{accent}"></span>{title}
              </div>
              <div class="offer-table-wrap">
                <table class="offer-table offer-table-fixed offer-cols-{len(cols)}">
                  <colgroup>{colgroup}</colgroup>
                  <thead><tr>{thead}</tr></thead>
                  <tbody>{''.join(body_rows)}</tbody>
                </table>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    if footnote:
        st.caption(footnote)


def page_quarterly_offers():
    st.markdown("## 季度優惠 & 獎賞")
    st.caption(
        "表格一覽 · Q4 來自 FWD Flash Report（客戶優惠 PDM76/2026、"
        "理財顧問獎賞 TA261048）。僅供內部參考，條款以官方文件為準。"
    )

    quarters = _quarters_map()
    q_keys = list(quarters.keys())
    cur = _current_quarter_key()
    default_idx = q_keys.index(cur) if cur in q_keys else 0
    labels = [f"{k} {quarters[k]['label']}（{quarters[k]['period']}）" for k in q_keys]
    choice = st.radio(
        "季度",
        options=q_keys,
        index=default_idx,
        format_func=lambda k: labels[q_keys.index(k)],
        horizontal=not MOBILE,
        label_visibility="collapsed",
    )
    meta = quarters[choice]
    st.markdown(
        f"""
        <div class="challenge-header-box">
          <strong>{choice} {meta['label']}</strong> · {meta['period']}<br>
          <span style="color:#6B7280;font-size:0.92rem;">而家系統季度：{cur}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    kind = st.radio(
        "類型",
        options=["customer", "agent"],
        format_func=lambda k: "客戶優惠" if k == "customer" else "營業員獎賞",
        horizontal=True,
        key=f"offer_kind_{choice}",
    )
    catalog = get_quarterly_catalog(choice, kind)
    _render_offer_catalog(
        catalog,
        empty_hint=(
            "呢季暫時未有資料。請確認已選 Q4，或 Reboot 後再試。"
            if choice != "Q4"
            else "未能載入 Q4 表格。請去 Streamlit Manage app → Reboot 後再入。"
        ),
        accent="#D4AF37" if kind == "customer" else "#C4895A",
    )

    if is_leader:
        with st.expander("Leader：新增 / 刪除優惠項目", expanded=False):
            st.caption("寫入 Google Sheet `quarterly_offers`。有 Sheet 資料時會覆蓋該季預設內容。")
            with st.form("quarterly_offer_form", clear_on_submit=True):
                kind = st.selectbox(
                    "類型",
                    ["customer", "agent"],
                    format_func=lambda k: "客戶優惠" if k == "customer" else "營業員獎賞",
                )
                title = st.text_input("標題", placeholder="e.g. 首年保費折扣 / FYC Bonus")
                detail = st.text_area("詳情", height=100)
                note = st.text_input("備註（可留空）", placeholder="限期、條款提示…")
                sort = st.number_input("排序", min_value=0, value=0, step=1)
                if st.form_submit_button("新增項目", type="primary"):
                    if title.strip() and detail.strip():
                        if add_quarterly_offer(choice, kind, title, detail, note, int(sort)):
                            st.toast("已新增", icon="✅")
                            st.rerun()
                        else:
                            st.error("儲存失敗，請稍後再試")
                    else:
                        st.error("標題同詳情必填")

            st.divider()
            st.caption(f"刪除 {choice} 已存項目（只刪 Sheet 入面嘅）")
            try:
                df_all = read_data("quarterly_offers")
            except Exception:
                df_all = pd.DataFrame()
            if df_all is None or df_all.empty or "quarter" not in df_all.columns:
                st.info("Sheet 未有項目")
            else:
                work = df_all.copy()
                work["quarter"] = work["quarter"].astype(str).str.strip().str.upper()
                work = work[work["quarter"] == choice]
                if work.empty:
                    st.info("呢季 Sheet 未有項目")
                else:
                    for _, row in work.iterrows():
                        kind_label = (
                            "客戶優惠"
                            if str(row.get("kind", "")).lower() == "customer"
                            else "營業員獎賞"
                        )
                        c1, c2 = st.columns([4, 1])
                        c1.markdown(f"**[{kind_label}]** {row.get('title', '')}")
                        if c2.button("刪除", key=f"del_offer_{row.get('id')}"):
                            if delete_quarterly_offer(row.get("id")):
                                st.toast("已刪除", icon="🗑️")
                                st.rerun()


_COMMON_FORMS_CATEGORIES = [
    "簽單表格",
    "行政文件",
    "培訓工具",
    "招募工具",
    "產品資料",
    "Sales Kit",
    "其他",
]
_COMMON_FORMS_FOLDER_KEY = "common_forms_folder_id"
_COMMON_FORMS_ALLOWED_EXT = {
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".csv",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".txt",
    ".zip",
}


def _common_forms():
    """Lazy-load 常用表格 helpers. Reload only when Cloud cached a stale module."""
    import importlib
    import sys

    try:
        import tt_core.common_forms as m
    except Exception:
        return None
    # Only reload if critical helpers are missing (stale Cloud bytecode)
    needed = ("sync_folder_into_catalog", "list_forms", "ensure_view_link", "get_folder_id")
    if all(callable(getattr(m, name, None)) for name in needed[:2]):
        return m
    try:
        return importlib.reload(sys.modules["tt_core.common_forms"])
    except Exception:
        return m


def _common_forms_folder_id() -> str:
    cf = _common_forms()
    try:
        if cf is not None:
            fn = getattr(cf, "get_folder_id", None)
            if callable(fn):
                return str(fn() or "").strip()
    except Exception:
        pass
    return _get_setting(_COMMON_FORMS_FOLDER_KEY, "")


def _save_common_forms_folder(raw: str) -> bool:
    cf = _common_forms()
    try:
        if cf is not None:
            fn = getattr(cf, "save_folder_id", None)
            if callable(fn):
                return bool(fn(raw))
    except Exception:
        pass
    return bool(_set_setting(_COMMON_FORMS_FOLDER_KEY, _normalize_folder_id(raw)))


def _common_forms_setup_hint() -> str:
    cf = _common_forms()
    try:
        if cf is not None:
            fn = getattr(cf, "setup_hint", None)
            if callable(fn):
                return str(fn())
    except Exception:
        pass
    sa = ""
    try:
        sa = str(service_account_email() or "")
    except Exception:
        sa = ""
    email = sa or "（service account email）"
    return (
        "一次性設定：\n"
        "1. 用你自己嘅 Google 帳號開資料夾，例如「TIM TEAM 常用表格」\n"
        f"2. 將資料夾分享俾 **{email}**（**編輯者** — 先可以自動開放下載連結）\n"
        "3. 複製資料夾連結或 Folder ID，貼喺下面儲存\n"
        "4. 放入文件 →「同步 Drive 資料夾」→「開放全部連結」\n"
        "5. 之後同事開啟唔使再等 approve"
    )


def _list_common_forms_drive_files(folder_id: str, limit: int = 100) -> list:
    """Inline Drive list — works even if Cloud cached an old common_forms.py."""
    cf = _common_forms()
    try:
        if cf is not None:
            fn = getattr(cf, "list_drive_folder_files", None)
            if callable(fn):
                return list(fn(folder_id, limit=limit) or [])
    except Exception:
        pass

    try:
        service = _drive().get_drive_service()
    except Exception:
        service = None
    folder_id = str(folder_id or "").strip()
    if not service or not folder_id:
        return []
    q = (
        f"'{folder_id}' in parents and trashed=false and "
        "mimeType != 'application/vnd.google-apps.folder'"
    )
    try:
        files: list[dict] = []
        page_token = None
        while True:
            resp = (
                service.files()
                .list(
                    q=q,
                    spaces="drive",
                    fields="nextPageToken,files(id,name,mimeType,modifiedTime,size)",
                    orderBy="modifiedTime desc",
                    pageSize=min(100, max(1, limit - len(files))),
                    pageToken=page_token,
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True,
                )
                .execute()
            )
            files.extend(resp.get("files", []) or [])
            page_token = resp.get("nextPageToken")
            if not page_token or len(files) >= limit:
                break
        out = []
        for f in files:
            name = str(f.get("name") or "")
            ext = Path(name).suffix.lower()
            if ext and ext not in _COMMON_FORMS_ALLOWED_EXT:
                continue
            out.append(f)
        return out
    except Exception as e:
        st.session_state["_common_forms_drive_warn"] = str(e)[:240]
        return []


def _sync_common_forms_folder(
    *,
    category: str = "其他",
    uploaded_by: str = "",
    note: str = "",
) -> dict:
    """Sync Drive folder → Sheets. Inline fallback for stale Cloud modules."""
    cf = _common_forms()
    try:
        if cf is not None:
            fn = getattr(cf, "sync_folder_into_catalog", None)
            if callable(fn):
                return dict(
                    fn(
                        category=category,
                        uploaded_by=uploaded_by,
                        note=note,
                    )
                    or {}
                )
    except Exception:
        pass

    folder_id = _common_forms_folder_id()
    if not folder_id:
        return {"ok": False, "error": "未設定常用表格 Drive 資料夾", "added": 0, "skipped": 0}

    files = _list_common_forms_drive_files(folder_id)
    if not files:
        err = st.session_state.pop("_common_forms_drive_warn", "")
        if err:
            return {"ok": False, "error": f"讀取資料夾失敗：{err}", "added": 0, "skipped": 0}
        return {
            "ok": True,
            "added": 0,
            "skipped": 0,
            "message": "資料夾暫時未有可同步檔案（請先用自己帳號放入 PDF／Word／Excel）",
        }

    try:
        from tt_core.db import soft_invalidate

        soft_invalidate("common_forms")
    except Exception:
        pass
    try:
        existing = read_data("common_forms", force=True)
    except Exception:
        existing = pd.DataFrame()
    known_ids = set()
    if existing is not None and not existing.empty and "drive_file_id" in existing.columns:
        known_ids = {
            str(x).strip() for x in existing["drive_file_id"].tolist() if str(x).strip()
        }

    category = str(category or "其他").strip() or "其他"
    note = str(note or "").strip()
    added = 0
    skipped = 0
    failed = 0
    failed_names: list[str] = []
    now = str(datetime.datetime.now())

    for f in files:
        drive_id = str(f.get("id") or "").strip()
        name = str(f.get("name") or "").strip()
        if not drive_id or not name:
            continue
        if drive_id in known_ids:
            skipped += 1
            continue
        title = Path(name).stem or name
        mime = str(f.get("mimeType") or "application/octet-stream")
        row = {
            "title": title,
            "category": category,
            "filename": name,
            "mime": mime,
            "drive_file_id": drive_id,
            "size_bytes": int(f.get("size") or 0),
            "uploaded_by": str(uploaded_by or "").strip(),
            "uploaded_at": str(f.get("modifiedTime") or now)[:19].replace("T", " "),
            "note": note,
        }
        try:
            ok = bool(run_query_gs("INSERT", "common_forms", row))
        except Exception:
            ok = False
        if ok:
            added += 1
            known_ids.add(drive_id)
            try:
                service = _drive().get_drive_service()
                if service:
                    service.permissions().create(
                        fileId=drive_id,
                        body={"type": "anyone", "role": "reader"},
                        supportsAllDrives=True,
                        fields="id",
                    ).execute()
            except Exception:
                pass
        else:
            failed += 1
            if len(failed_names) < 5:
                failed_names.append(name)

    if added == 0 and failed == 0 and skipped > 0:
        msg = (
            f"冇新檔：Drive 入面 {skipped} 份都已經喺清單。"
            "請放入新檔案到資料夾，再撳同步一次。"
        )
    elif failed and added == 0:
        return {
            "ok": False,
            "error": "寫入清單失敗：" + "、".join(failed_names),
            "added": 0,
            "skipped": skipped,
            "failed": failed,
        }
    else:
        msg = f"同步完成：新增 {added} 份，略過已有 {skipped} 份"
        if failed:
            msg += f"，失敗 {failed} 份"

    return {
        "ok": failed == 0 or added > 0,
        "added": added,
        "skipped": skipped,
        "failed": failed,
        "message": msg,
    }


def page_common_forms():
    st.markdown("## 常用表格")
    st.caption(
        "簽單／行政常用文件。撳「開啟檔案」用 Google Drive 開；"
        "睇完關掉新頁／返回即可，唔會困喺下載預覽。"
    )

    cf = _common_forms()
    categories = list(getattr(cf, "CATEGORIES", None) or _COMMON_FORMS_CATEGORIES)
    folder_id = _common_forms_folder_id()

    if is_leader:
        with st.expander("Leader：Drive 資料夾設定", expanded=not bool(folder_id)):
            st.markdown(_common_forms_setup_hint())
            raw = st.text_input(
                "常用表格 Folder ID / Drive 連結",
                value=folder_id,
                placeholder="https://drive.google.com/drive/folders/…",
                key="common_forms_folder_input",
            )
            if st.button("儲存資料夾", type="primary", key="common_forms_save_folder"):
                if _save_common_forms_folder(raw):
                    st.toast("已儲存常用表格資料夾", icon="✅")
                    st.rerun()
                else:
                    st.error("請貼上有效嘅 Folder ID 或 Drive 連結")
            if folder_id:
                st.caption(f"而家 Folder ID：`{folder_id}`")

        with st.expander("Leader：同步 Drive 資料夾（推薦）", expanded=bool(folder_id)):
            st.info(
                "請用你自己 Google 帳號將文件放入資料夾，再撳同步。"
                "可以重複撳同步——已入清單嘅會略過，只加新檔。"
            )
            if not folder_id:
                st.warning("請先完成上面嘅 Drive 資料夾設定。")
            else:
                sync_cat = st.selectbox(
                    "新檔預設分類",
                    categories,
                    key="common_forms_sync_cat",
                )
                sync_note = st.text_input(
                    "新檔備註（可留空）",
                    key="common_forms_sync_note",
                    placeholder="例如：2026 版簽單表格",
                )
                if st.button("同步 Drive 資料夾", type="primary", key="common_forms_sync_btn"):
                    with st.spinner("掃描資料夾…"):
                        result = _sync_common_forms_folder(
                            category=sync_cat,
                            uploaded_by=st.session_state.get("user", ""),
                            note=sync_note,
                        )
                    if result.get("ok"):
                        added = int(result.get("added") or 0)
                        if added:
                            st.toast(result.get("message") or "同步完成", icon="✅")
                        else:
                            st.info(result.get("message") or "冇新檔")
                        # Reset category filter so new files are visible
                        st.session_state["common_forms_cat_filter"] = "全部"
                        st.rerun()
                    else:
                        st.error(result.get("error") or result.get("message") or "同步失敗")
                if st.button(
                    "開放全部連結（免審批）",
                    key="common_forms_share_all",
                    use_container_width=True,
                    help="將清單內每份檔案設為「知道連結即可檢視」，同事唔使再等你 approve",
                ):
                    with st.spinner("開放連結中…"):
                        share_fn = getattr(cf, "share_all_catalog_files", None) if cf else None
                        if callable(share_fn):
                            result = share_fn()
                        else:
                            result = _share_all_common_forms()
                    if result.get("ok"):
                        st.toast(result.get("message") or "已開放", icon="✅")
                    else:
                        st.warning(result.get("message") or "部分檔案未能開放")
                        err = st.session_state.pop("_common_forms_share_warn", "")
                        if err:
                            st.caption(f"詳情：{err}")

        with st.expander("Leader：點樣加新文件？", expanded=False):
            st.info(
                "為免 Streamlit Cloud 上載爆記憶體（Oh no），"
                "**已關閉 app 內上傳**。\n\n"
                "請用自己 Google 帳號把檔案放入 Drive 資料夾，"
                "然後撳上面 **「同步 Drive 資料夾」**。"
            )
            st.caption("共用雲端硬碟／我的雲端硬碟都可以用同步方式。")

    filter_opts = ["全部"] + categories
    cat_filter = st.radio(
        "分類",
        options=filter_opts,
        horizontal=not MOBILE,
        key="common_forms_cat_filter",
    )

    try:
        list_fn = getattr(cf, "list_forms", None) if cf else None
        if callable(list_fn):
            df = list_fn(category=None if cat_filter == "全部" else cat_filter)
        else:
            df = read_data("common_forms")
            if df is not None and not df.empty and cat_filter != "全部":
                df = df[df["category"].astype(str).str.strip() == cat_filter]
    except Exception as e:
        st.error(f"讀取清單失敗：{e}")
        return

    if df is None or df.empty:
        st.info(
            "暫時未有文件。"
            + (
                " Leader：用自己帳號放入 Drive 資料夾後，撳「同步 Drive 資料夾」。"
                if is_leader
                else " 請聯絡 Leader 放入常用表格。"
            )
        )
        return

    st.caption(f"共 {len(df)} 份文件")
    for _, row in df.iterrows():
        rid = row.get("id", "")
        title = str(row.get("title", "") or row.get("filename", "") or "未命名")
        cat = str(row.get("category", "") or "其他")
        fname = str(row.get("filename", "") or "")
        note = str(row.get("note", "") or "").strip()
        by = str(row.get("uploaded_by", "") or "")
        at = str(row.get("uploaded_at", "") or "")[:16]
        fmt = getattr(cf, "format_size", None) if cf else None
        if callable(fmt):
            size_label = fmt(row.get("size_bytes", 0))
        else:
            try:
                n = int(float(row.get("size_bytes", 0) or 0))
                size_label = (
                    f"{n} B"
                    if n < 1024
                    else f"{n/1024:.1f} KB"
                    if n < 1024 * 1024
                    else f"{n/(1024*1024):.1f} MB"
                )
            except Exception:
                size_label = "—"
        drive_id = str(row.get("drive_file_id", "") or "").strip()

        st.markdown(
            f"""
            <div class="challenge-header-box" style="margin-bottom:0.55rem;">
              <strong>{title}</strong>
              <span style="color:#6B7280;font-size:0.9rem;"> · {cat}</span><br>
              <span style="color:#6B7280;font-size:0.88rem;">{fname} · {size_label}</span>
              {"<br><span style='color:#6B7280;font-size:0.88rem;'>" + note + "</span>" if note else ""}
              <br><span style="color:#9CA3AF;font-size:0.8rem;">上傳：{by or "—"} · {at or "—"}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        view_url = _common_forms_view_link(drive_id) if drive_id else ""
        cols = st.columns([2, 1] if is_leader else [1])
        with cols[0]:
            if not drive_id:
                st.warning("缺少 Drive 檔案 ID")
            elif view_url:
                # Shared Drive link — no Request access after Leader opens links
                if hasattr(st, "link_button"):
                    st.link_button(
                        "開啟檔案",
                        view_url,
                        use_container_width=True,
                        type="primary",
                    )
                else:
                    st.markdown(
                        f'<a href="{view_url}" target="_blank" rel="noopener noreferrer">'
                        f"<strong>開啟檔案</strong></a>",
                        unsafe_allow_html=True,
                    )
            else:
                st.warning("未能產生開啟連結")
        if is_leader and len(cols) > 1:
            with cols[1]:
                if st.button("刪除", key=f"del_form_{rid}", use_container_width=True):
                    del_fn = getattr(cf, "delete_form", None) if cf else None
                    if callable(del_fn):
                        result = del_fn(rid, drive_id or None)
                    else:
                        result = {
                            "ok": bool(run_query_gs("DELETE", "common_forms", row_id=rid))
                        }
                    if result.get("ok"):
                        st.toast("已刪除", icon="🗑️")
                        st.rerun()
                    else:
                        st.error(result.get("error") or "刪除失敗")

def _common_forms_view_link(drive_file_id: str) -> str:
    """Build a Drive view URL without calling Drive API (safe during page render)."""
    file_id = str(drive_file_id or "").strip()
    if not file_id:
        return ""
    return f"https://drive.google.com/file/d/{file_id}/view?usp=sharing"


def _share_all_common_forms() -> dict:
    """Inline fallback: anyone-with-link for every catalog file."""
    cf = _common_forms()
    try:
        if cf is not None:
            fn = getattr(cf, "share_all_catalog_files", None)
            if callable(fn):
                return dict(fn() or {})
    except Exception:
        pass
    try:
        existing = read_data("common_forms")
    except Exception:
        existing = pd.DataFrame()
    if existing is None or existing.empty or "drive_file_id" not in existing.columns:
        return {"ok": True, "shared": 0, "failed": 0, "message": "清單未有檔案"}
    shared = 0
    failed = 0
    try:
        service = _drive().get_drive_service()
    except Exception:
        service = None
    if not service:
        return {"ok": False, "shared": 0, "failed": 0, "message": "Drive 未連接"}
    for raw_id in existing["drive_file_id"].tolist():
        drive_id = str(raw_id or "").strip()
        if not drive_id:
            continue
        try:
            service.permissions().create(
                fileId=drive_id,
                body={"type": "anyone", "role": "reader"},
                supportsAllDrives=True,
                fields="id",
            ).execute()
            shared += 1
        except Exception as e:
            msg = str(e).lower()
            if "already" in msg or "duplicate" in msg or "exists" in msg:
                shared += 1
            else:
                failed += 1
                st.session_state["_common_forms_share_warn"] = str(e)[:240]
    return {
        "ok": failed == 0,
        "shared": shared,
        "failed": failed,
        "message": f"已開放連結 {shared} 份" + (f"，失敗 {failed} 份" if failed else ""),
    }


def _medical_uw():
    """Lazy-load medical underwriting helpers (Cloud-safe)."""
    try:
        import tt_core.medical_uw as m

        return m
    except Exception:
        return None


def page_medical_uw():
    """見客用：按 Medical Manual 常見疾病一步步問答，顯示參考核保結果。"""
    st.markdown("## 🩺 常見疾病核保")
    st.caption("見客時按核保指引問症 → 即時睇各計劃參考結果（內部用）")

    mu = _medical_uw()
    if mu is None:
        st.error("核保模組暫時未能載入。請 Reboot app 後再試。")
        return

    disclaimer = mu.disclaimer_text()
    st.warning(disclaimer)

    # Session wizard state
    if "mu_disease_id" not in st.session_state:
        st.session_state["mu_disease_id"] = None
    if "mu_answers" not in st.session_state:
        st.session_state["mu_answers"] = {}
    if "mu_scenario_id" not in st.session_state:
        st.session_state["mu_scenario_id"] = None

    disease_id = st.session_state.get("mu_disease_id")

    # ── Step 1: pick disease ──────────────────────────────────────────────
    if not disease_id:
        q = st.text_input(
            "搜尋疾病（中／英）",
            placeholder="例如：高血壓、脂肪肝、diabetes、asthma…",
            key="mu_search",
        )
        diseases = mu.search_diseases(q)
        if not diseases:
            st.info("搵唔到相關疾病。試下其他關鍵字。")
            return
        st.caption(f"共 {len(diseases)} 項（來源：Medical Manual 常見疾病核保指引 v2.0）")
        # Compact picker
        labels = [f"{d['name_zh']}（{d['name_en']}）" for d in diseases]
        pick = st.selectbox("選擇疾病", labels, key="mu_disease_pick")
        if st.button("開始問症", type="primary", use_container_width=True):
            idx = labels.index(pick)
            st.session_state["mu_disease_id"] = diseases[idx]["id"]
            st.session_state["mu_answers"] = {}
            st.session_state["mu_scenario_id"] = None
            st.rerun()
        with st.expander("全部疾病一覽"):
            for d in mu.list_diseases():
                st.markdown(f"- **{d['name_zh']}** · {d['name_en']}")
        return

    disease = mu.get_disease(disease_id)
    if not disease:
        st.session_state["mu_disease_id"] = None
        st.rerun()
        return

    top_l, top_r = st.columns([3, 1])
    with top_l:
        st.markdown(f"### {disease['name_zh']}")
        st.caption(disease.get("name_en") or "")
    with top_r:
        if st.button("換疾病", use_container_width=True):
            st.session_state["mu_disease_id"] = None
            st.session_state["mu_answers"] = {}
            st.session_state["mu_scenario_id"] = None
            st.rerun()

    if disease.get("description_zh"):
        st.info(disease["description_zh"])

    # ── Step 2: questions ─────────────────────────────────────────────────
    st.markdown("#### ① 問客人（按核保先決要求）")
    answers = dict(st.session_state.get("mu_answers") or {})
    questions = disease.get("questions") or []
    with st.form("mu_questions_form"):
        for i, q in enumerate(questions):
            opts = q.get("options") or []
            opt_labels = [o["label"] for o in opts]
            opt_values = [o["value"] for o in opts]
            current = answers.get(q["id"])
            try:
                idx = opt_values.index(current) if current in opt_values else 0
            except Exception:
                idx = 0
            choice = st.radio(
                f"{i + 1}. {q.get('prompt') or q['id']}",
                options=opt_labels,
                index=idx,
                key=f"mu_q_{disease_id}_{q['id']}",
            )
            answers[q["id"]] = opt_values[opt_labels.index(choice)]
        submitted = st.form_submit_button("計核保參考結果", type="primary", use_container_width=True)

    if submitted:
        st.session_state["mu_answers"] = answers
        auto = mu.match_scenarios(disease, answers, fallback_all=False)
        if auto:
            st.session_state["mu_scenario_id"] = auto[0]["id"]
        else:
            st.session_state["mu_scenario_id"] = None
        st.rerun()

    answers = dict(st.session_state.get("mu_answers") or {})
    if not answers:
        st.caption("請回答上面問題後撳「計核保參考結果」。")
        return

    # ── Step 3: scenario confirm + outcomes ───────────────────────────────
    st.markdown("#### ② 對應核保情況")
    auto = mu.match_scenarios(disease, answers, fallback_all=False)
    matched = auto if auto else list(disease.get("scenarios") or [])
    scenario_ids = [s["id"] for s in matched]
    scenario_labels = [s["label_zh"] for s in matched]
    if not matched:
        st.warning("呢個疾病暫時未有對應情況，請聯絡核保或查閱原文指引。")
        return

    if auto:
        st.success(f"根據答案，最接近：**{auto[0]['label_zh']}**")
        default_id = st.session_state.get("mu_scenario_id") or auto[0]["id"]
    else:
        st.info("未能自動鎖定單一情況，請揀最接近客人狀況嘅一項：")
        default_id = st.session_state.get("mu_scenario_id") or scenario_ids[0]

    try:
        default_idx = scenario_ids.index(default_id) if default_id in scenario_ids else 0
    except Exception:
        default_idx = 0
    pick_label = st.selectbox(
        "核保情況",
        scenario_labels,
        index=default_idx,
        key=f"mu_scenario_pick_{disease_id}",
    )
    scenario = matched[scenario_labels.index(pick_label)]
    st.session_state["mu_scenario_id"] = scenario["id"]

    st.markdown("#### ③ 各計劃參考結果")
    outcomes = scenario.get("outcomes") or {}
    tone_colors = {
        "good": "#059669",
        "caution": "#D97706",
        "warn": "#DC2626",
        "bad": "#991B1B",
        "neutral": "#4B5563",
    }
    cols = st.columns(5)
    for col, key in zip(cols, ["life", "ci", "medical", "accident", "cancer"]):
        label = mu.PRODUCT_LABELS.get(key, key)
        val = outcomes.get(key, "—")
        tone = mu.outcome_tone(val)
        color = tone_colors.get(tone, "#4B5563")
        with col:
            st.markdown(
                f"""
                <div style="border:1px solid #E5E7EB;border-radius:10px;padding:10px 8px;text-align:center;min-height:96px;">
                  <div style="font-size:12px;color:#6B7280;margin-bottom:6px;">{label}</div>
                  <div style="font-size:14px;font-weight:700;color:{color};line-height:1.35;">{val}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    if scenario.get("note"):
        st.caption(scenario["note"])

    extra = disease.get("extra_reqs") or []
    if extra:
        st.markdown("#### 可能附加要求")
        for line in extra:
            st.markdown(f"- {line}")

    with st.expander("今次問答摘要"):
        for qlab, alab in mu.summarize_answers(disease, answers):
            st.markdown(f"- **{qlab}**：{alab}")
        st.markdown(f"- **對應情況**：{scenario.get('label_zh')}")

    st.caption("結果只供內部參考，最終以 FWD 核保為準。")


def page_cashflow_taccount():
    """見客用：收入／支出 T-Account → 計 Cashflow → 儲蓄保險 budget。"""
    st.markdown("## 💹 收入／支出 T-Account")
    st.caption("同客戶一齊填每月收入同支出，計出現金流，作為儲蓄保險保費 budget。")

    try:
        from tt_core import cashflow as cf
    except Exception:
        st.error("Cashflow 模組未能載入，請 Reboot 後再試。")
        return

    client = st.text_input(
        "客戶名稱（可留空）",
        key="cf_client_name",
        placeholder="例如：陳生／陳太",
    )

    # Seed session defaults once
    for it in cf.INCOME_ITEMS + cf.EXPENSE_ITEMS:
        k = f"cf_{it['id']}"
        if k not in st.session_state:
            st.session_state[k] = 0.0

    st.markdown(
        """
        <style>
        .cf-head {
          background: linear-gradient(90deg, #1a1a2e 0%, #2d2d44 100%);
          color: #F5D76E;
          font-weight: 700;
          text-align: center;
          padding: 10px 8px;
          border-radius: 8px 8px 0 0;
          margin-bottom: 0;
          letter-spacing: 0.02em;
        }
        .cf-total-row {
          background: #1a1a2e;
          color: #F5D76E;
          font-weight: 700;
          padding: 10px 12px;
          border-radius: 0 0 8px 8px;
          display: flex;
          justify-content: space-between;
          margin-top: 4px;
        }
        .cf-result {
          border: 1px solid #E5E7EB;
          border-radius: 12px;
          padding: 16px;
          margin-top: 12px;
          background: linear-gradient(180deg, #FFFDF5 0%, #FFFFFF 100%);
        }
        .cf-result .big {
          font-size: 1.6rem;
          font-weight: 800;
          margin: 4px 0 8px 0;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    left, right = st.columns(2, gap="medium")

    with left:
        st.markdown('<div class="cf-head">每月收入</div>', unsafe_allow_html=True)
        income_vals: dict = {}
        for it in cf.INCOME_ITEMS:
            income_vals[it["id"]] = st.number_input(
                it["label"],
                min_value=0.0,
                step=100.0,
                format="%.0f",
                key=f"cf_{it['id']}",
            )
        income_total = cf.sum_items(income_vals, cf.INCOME_ITEMS)
        st.markdown(
            f'<div class="cf-total-row"><span>總收入</span><span>{cf.format_hkd(income_total)}</span></div>',
            unsafe_allow_html=True,
        )

    with right:
        st.markdown('<div class="cf-head">每月支出</div>', unsafe_allow_html=True)
        expense_vals: dict = {}
        for it in cf.EXPENSE_ITEMS:
            expense_vals[it["id"]] = st.number_input(
                it["label"],
                min_value=0.0,
                step=100.0,
                format="%.0f",
                key=f"cf_{it['id']}",
            )
        expense_total = cf.sum_items(expense_vals, cf.EXPENSE_ITEMS)
        st.markdown(
            f'<div class="cf-total-row"><span>總支出</span><span>{cf.format_hkd(expense_total)}</span></div>',
            unsafe_allow_html=True,
        )

    values = {**income_vals, **expense_vals}
    result = cf.calc_cashflow(values)
    cashflow = result["cashflow"]
    tone = "#059669" if cashflow > 0 else ("#DC2626" if cashflow < 0 else "#6B7280")

    name_bit = f" — {client.strip()}" if str(client or "").strip() else ""
    st.markdown(
        f"""
        <div class="cf-result">
          <div style="color:#6B7280;font-size:0.9rem;">每月 Cashflow{name_bit}</div>
          <div class="big" style="color:{tone};">{cf.format_hkd(cashflow)}</div>
          <div style="color:#4B5563;font-size:0.92rem;">
            總收入 {cf.format_hkd(result['income'])} − 總支出 {cf.format_hkd(result['expense'])}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.info(cf.budget_suggestion(cashflow))
    st.caption(cf.PRODUCT_HINTS)

    c1, c2 = st.columns(2)
    with c1:
        if st.button("清空重計", use_container_width=True, key="cf_reset"):
            for it in cf.INCOME_ITEMS + cf.EXPENSE_ITEMS:
                st.session_state[f"cf_{it['id']}"] = 0.0
            st.session_state["cf_client_name"] = ""
            st.rerun()
    with c2:
        st.caption("金額以港元／每月計。數字只留在此裝置 session，唔會自動上傳。")


def page_profile():
    st.markdown("## 個人設定")
    if MOBILE:
        if st.session_state.get("avatar"):
            st.image(st.session_state["avatar"], width=96)
        st.markdown(f"### {st.session_state['user']}")
        st.caption(st.session_state["role"])
        render_install_guide(compact=False)
        with st.expander("更改密碼"):
            new_pw = st.text_input("新密碼", type="password")
            if st.button("更新密碼", use_container_width=True):
                update_pw(st.session_state["user"], new_pw)
                st.toast("Password Updated!", icon="✅")
        with st.expander("更改頭像"):
            uploaded_file = st.file_uploader("Upload Image", type=["jpg", "png", "jpeg"])
            if uploaded_file is not None and st.button("Upload", use_container_width=True):
                img_str = proc_img(uploaded_file)
                if img_str:
                    update_avt(st.session_state["user"], img_str)
                    st.session_state["avatar"] = img_str
                    st.toast("Avatar Updated!", icon="✅")
                    st.rerun()
    else:
        col1, col2 = st.columns([1, 2])
        with col1:
            if st.session_state.get("avatar"):
                st.image(st.session_state["avatar"], width=150)
        with col2:
            st.markdown(f"### {st.session_state['user']}")
            st.markdown(f"**Role:** {st.session_state['role']}")
            render_install_guide(compact=True)
            with st.expander("更改密碼"):
                new_pw = st.text_input("新密碼", type="password")
                if st.button("更新密碼"):
                    update_pw(st.session_state["user"], new_pw)
                    st.toast("Password Updated!", icon="✅")
            with st.expander("更改頭像"):
                uploaded_file = st.file_uploader("Upload Image", type=["jpg", "png", "jpeg"])
                if uploaded_file is not None and st.button("Upload"):
                    img_str = proc_img(uploaded_file)
                    if img_str:
                        update_avt(st.session_state["user"], img_str)
                        st.session_state["avatar"] = img_str
                        st.toast("Avatar Updated!", icon="✅")
                        st.rerun()


# ─── Router ──────────────────────────────────────────────────────────────────
def _safe_page(label: str, fn):
    try:
        fn()
    except Exception as e:
        st.session_state["_force_home_once"] = True
        st.session_state["_menu_choice"] = "🏠 我的主頁"
        st.error(f"{label} 暫時無法開啟：{e}")
        st.caption("可以撳側欄其他功能，或登出再入。若持續出現請 Reboot app。")
        if st.button("返回主頁", type="primary", key=f"safe_home_{label}"):
            st.rerun()

if "我的主頁" in menu:
    _safe_page("我的主頁", page_home)
elif "打卡" in menu:
    _safe_page("打卡", page_checkin)
elif "Dashboard" in menu:
    _safe_page("Dashboard", page_dashboard)
elif "業績報告" in menu or "Iris" in menu:
    if is_leader:
        _safe_page("業績報告同步", page_iris_sync)
    else:
        st.warning("只有 Leader 可以同步業績報告")
elif "每月" in menu:
    _safe_page("每月業績", page_monthly)
elif "年度" in menu:
    _safe_page("年度挑戰", page_year_goal)
elif "每週" in menu:
    _safe_page("每週挑戰", page_challenge)
elif "招募" in menu:
    _safe_page("招募龍虎榜", page_recruit)
elif "季度優惠" in menu:
    _safe_page("季度優惠", page_quarterly_offers)
elif "常用表格" in menu:
    _safe_page("常用表格", page_common_forms)
elif "常見疾病核保" in menu or "核保" in menu:
    _safe_page("常見疾病核保", page_medical_uw)
elif "T-Account" in menu or "收入／支出" in menu or "Cashflow" in menu:
    _safe_page("收入／支出 T-Account", page_cashflow_taccount)
elif "設定" in menu:
    _safe_page("設定", page_profile)

# cloud_redeploy_stamp: 2026-10-15T13:20Z
