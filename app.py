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
    RECRUIT_ACTIVITY_TYPES,
    RECRUIT_STAGES,
    SALES_ACTIVITY_TYPES,
    SALES_STAGES,
    TRACK_RECRUIT,
    TRACK_SALES,
    WEEKLY_MIN_ACTS,
    WEEKLY_PENALTY,
)
from tt_core.data import (
    add_act,
    add_pipeline_checkin,
    check_notifications,
    get_activity_style,
    get_all_act,
    get_clean_users,
    get_coach_member_pack,
    get_data,
    get_due_followups,
    get_last_week_data,
    get_member_snapshot,
    get_note_template,
    get_q1_data,
    get_stuck_cases,
    get_team_coach_overview,
    get_upcoming_followups,
    get_weekly_data,
    last_iris_sync,
    login,
    mark_followup_done,
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
    "🛡️ 保障缺口",
    "🏥 醫療融資計算機",
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
def _render_followup_item(row, *, key_prefix: str) -> None:
    """One follow-up card with mark-done control."""
    nd = row.get("next_date")
    try:
        nd_str = pd.to_datetime(nd).strftime("%Y-%m-%d") if pd.notna(nd) else "—"
    except Exception:
        nd_str = str(nd or "—")
    today = datetime.date.today()
    try:
        overdue = pd.notna(nd) and pd.to_datetime(nd).date() < today
    except Exception:
        overdue = False
    due_today = False
    try:
        due_today = pd.notna(nd) and pd.to_datetime(nd).date() == today
    except Exception:
        pass
    flag = "🔴 已過期" if overdue else ("🟡 今日到期" if due_today else "🟢 即將")
    track = str(row.get("track") or "")
    person = str(row.get("person") or "")
    stage = str(row.get("stage") or "")
    action = str(row.get("next_action") or "")
    st.markdown(
        f"**{flag} · {person}**（{track}｜{stage}）  \n"
        f"Next：{action}  \n"
        f"日期：`{nd_str}`"
    )
    rid = row.get("id")
    c1, c2 = st.columns([1, 1])
    with c1:
        if st.button("✓ 已跟進", key=f"{key_prefix}_done_{rid}", use_container_width=True):
            mark_followup_done(rid)
            st.toast(f"已完成：{person}", icon="✅")
            st.rerun()
    with c2:
        if st.button("去打卡更新", key=f"{key_prefix}_go_{rid}", use_container_width=True):
            st.session_state["_menu_choice"] = "📝 打卡 Check-in"
            st.session_state["ci_prefill_person"] = person
            st.session_state["ci_prefill_track"] = track
            st.rerun()
    st.divider()


def page_home():
    user = st.session_state["user"]
    snap = get_member_snapshot(user) if st.session_state["role"] == "Member" else None
    team = get_data("Yearly")

    st.markdown(
        f"""
        <div class="tt-hero">
          <div class="tt-kicker">{BRAND_APP if MOBILE else BRAND_SYSTEM}</div>
          <h1 style="margin:0;">今日行動清單</h1>
          <p class="tt-sub">你好，{user} · 過期同今日要跟嘅案會出現喺呢度</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    due = get_due_followups(user)
    upcoming = get_upcoming_followups(user, days=7)

    # Compact KPI strip
    if snap:
        mdrt = mdrt_card_metrics(user)
        r1 = st.columns(2)
        r1[0].metric("今日要跟", len(due))
        r1[1].metric("7日內", len(upcoming))
        r2 = st.columns(2)
        r2[0].metric("本週活動", f"{snap['wk_count']}/{WEEKLY_MIN_ACTS}")
        r2[1].metric("MDRT", f"{mdrt['mdrt_pct']:.0f}%")
    else:
        calc = float(team["fyc"].sum()) if not team.empty else 0.0
        r1 = st.columns(2)
        r1[0].metric("今日要跟", len(due))
        r1[1].metric("Team SC", f"${get_team_sc(calc):,.0f}")
        st.metric("Recruits", int(team["recruit"].sum()) if not team.empty else 0)

    st.markdown("### 今日要跟")
    if due.empty:
        st.success("暫時冇逾期／今日到期項目 — 保持！")
    else:
        st.caption(f"共 {len(due)} 項（已過期或今日到期）")
        for _, row in due.iterrows():
            _render_followup_item(row, key_prefix="home_due")

    st.markdown("### 未來 7 日")
    if upcoming.empty:
        st.info("未有未來 7 日跟進。去打卡時記得填 Next action + 日期。")
    else:
        for _, row in upcoming.iterrows():
            _render_followup_item(row, key_prefix="home_up")

    if st.button("＋ 去打卡（做數／招募）", type="primary", use_container_width=True, key="home_go_checkin"):
        st.session_state["_menu_choice"] = "📝 打卡 Check-in"
        st.rerun()

    with st.expander("團隊最新動態", expanded=False):
        acts = get_all_act().head(5)
        users_df = get_clean_users()
        if acts.empty:
            st.info("暫時未有動態。")
        else:
            acts = pd.merge(acts, users_df[["username", "avatar"]], on="username", how="left")
            for _, row in acts.iterrows():
                act_date = pd.to_datetime(row["date"]).strftime("%Y-%m-%d")
                note_preview = str(row.get("note") or "").split("\n")[:3]
                st.markdown(
                    f"**{row['username']}** · {row['type']} · {act_date}  \n"
                    + "  \n".join(note_preview)
                )


def page_checkin():
    st.markdown("## 打卡中心")
    st.caption(
        "做數／招募都填 15 條 Fact find；必須選階段、Next action、跟進日期 — "
        "過期會出現喺主頁「今日要跟」。"
    )
    tab_new, tab_hist = st.tabs(["立即打卡", "團隊動態"])

    with tab_new:
        prefill_track = st.session_state.pop("ci_prefill_track", None)
        prefill_person = st.session_state.pop("ci_prefill_person", None)
        track_options = [TRACK_SALES, TRACK_RECRUIT]
        if prefill_track in track_options:
            st.session_state["ci_track"] = prefill_track
        if "ci_track" not in st.session_state:
            st.session_state["ci_track"] = TRACK_SALES
        track = st.radio(
            "軌道",
            track_options,
            horizontal=True,
            key="ci_track",
        )
        types = SALES_ACTIVITY_TYPES if track == TRACK_SALES else RECRUIT_ACTIVITY_TYPES
        stages = SALES_STAGES if track == TRACK_SALES else RECRUIT_STAGES
        person_label = "客戶名稱" if track == TRACK_SALES else "準增員／新人名稱"
        default_ff = get_note_template("")
        if prefill_person is not None:
            st.session_state["ci_person"] = str(prefill_person)
        if "ci_person" not in st.session_state:
            st.session_state["ci_person"] = ""

        with st.form("checkin_pipeline_v1", clear_on_submit=True):
            d = st.date_input("活動日期", value=datetime.date.today())
            t = st.selectbox("活動種類", types)
            person = st.text_input(
                person_label,
                placeholder="例如：陳生／陳太",
                key="ci_person",
            )
            stage = st.selectbox("邊個階段", stages)
            next_action = st.text_input(
                "Next action（必填）",
                placeholder="例如：WhatsApp 約簽單／帶去見經理",
            )
            next_date = st.date_input(
                "跟進日期（必填）",
                value=datetime.date.today() + datetime.timedelta(days=3),
            )
            factfind = st.text_area(
                "Fact find background（15 條）",
                value=default_ff,
                height=480,
            )
            submitted = st.form_submit_button("提交打卡", type="primary", use_container_width=True)
            if submitted:
                if not str(person or "").strip():
                    st.error(f"請填寫{person_label}")
                elif not str(next_action or "").strip():
                    st.error("請填寫 Next action")
                elif not next_date:
                    st.error("請選擇跟進日期")
                else:
                    try:
                        add_pipeline_checkin(
                            st.session_state["user"],
                            act_date=d,
                            act_type=t,
                            track=track,
                            person=person,
                            stage=stage,
                            next_action=next_action,
                            next_date=next_date,
                            factfind=factfind,
                        )
                        st.toast("打卡成功！已加入跟進清單", icon="✅")
                        st.rerun()
                    except Exception as e:
                        st.error(f"提交失敗：{e}")

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


def _render_whatsapp_share(report: str, *, key: str, caption: str = "") -> None:
    """Show copyable summary + one-tap WhatsApp open (帶得走)."""
    try:
        from tt_core.whatsapp_share import wa_me_url
    except Exception:
        wa_me_url = lambda t: f"https://wa.me/?text={urllib.parse.quote(t or '')}"  # noqa: E731

    st.markdown("##### 📤 一鍵傳 WhatsApp 俾客戶")
    if caption:
        st.caption(caption)
    else:
        st.caption("摘要已預填；撳掣開 WhatsApp 揀對話即可傳送（傳前可改字）。")
    st.code(report, language=None)
    st.link_button(
        "打開 WhatsApp 傳送",
        wa_me_url(report),
        use_container_width=True,
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


def _render_rank_card_list(parts: list[str]) -> None:
    """Shared iframe host for rank cards (mobile-safe, same look as MDRT board)."""
    n = max(len(parts), 1)
    height = 28 + n * 148
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


def _rank_shell(
    *,
    rank: int,
    name: str,
    avatar: str,
    big: str,
    sub: str,
    right: str,
    pct: float,
    meta: str,
    chip: str = "",
) -> str:
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
    top_bar = (
        '<div style="position:absolute;left:0;top:0;right:0;height:4px;'
        'background:linear-gradient(90deg,#D4AF37,#F0D078,#D4AF37);"></div>'
        if rank == 1
        else ""
    )
    return (
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
        + str(rank)
        + "</div>"
        + f"<img src='{avatar}' alt='{name}' style='width:48px;height:48px;border-radius:50%;"
        + "object-fit:cover;border:2px solid #F0E6C4;flex-shrink:0;background:#eee;'>"
        + "<div style='flex:1;min-width:0;'>"
        + f"<div style='font-weight:700;font-size:16px;color:#1C2430;'>{name}{chip}</div>"
        + f"<div style=\"font-family:Georgia,serif;font-size:22px;color:#1C2430;"
        + f"line-height:1.2;margin-top:2px;\">{big}</div>"
        + f"<div style='color:#6B7280;font-size:12px;margin-top:2px;'>{sub}</div>"
        + "</div>"
        + f"<div style='flex-shrink:0;text-align:right;font-weight:800;font-size:17px;"
        + f"color:#9A7B1A;min-width:52px;'>{right}</div>"
        + "</div>"
        + "<div style='margin-top:10px;height:9px;border-radius:999px;background:#ECE7DC;overflow:hidden;'>"
        + f"<div style='height:100%;width:{pct:.1f}%;border-radius:999px;"
        + "background:linear-gradient(90deg,#D4AF37,#F0D078);'></div></div>"
        + f"<div style='display:flex;gap:14px;margin-top:10px;color:#6B7280;font-size:13px;'>{meta}</div>"
        + "</div>"
    )


def render_challenge_cards(df: pd.DataFrame) -> None:
    """Weekly challenge leaderboard — score + activity count cards."""
    if df is None or df.empty:
        st.info("本週暫無數據")
        return
    ranked = df.sort_values(by="wk_score", ascending=False).reset_index(drop=True)
    max_score = float(ranked["wk_score"].max() or 0)
    bar_max = max(max_score, float(WEEKLY_MIN_ACTS), 1.0)
    parts = []
    for i, row in ranked.iterrows():
        rank = i + 1
        score = int(row.get("wk_score", 0) or 0)
        count = int(row.get("wk_count", 0) or 0)
        pct = min(max(score / bar_max * 100, 0), 100)
        name = _esc(row.get("username", ""))
        av = _esc(_avatar_url(row))
        chip = ""
        if rank == 1 and score > 0:
            chip = (
                '<span style="display:inline-block;margin-left:6px;background:#F7F1DE;color:#7A6420;'
                'border-radius:999px;padding:2px 8px;font-size:11px;font-weight:600;">👑 MVP</span>'
            )
        if count < WEEKLY_MIN_ACTS:
            chip += (
                '<span style="display:inline-block;margin-left:6px;background:#FEE2E2;color:#991B1B;'
                f'border-radius:999px;padding:2px 8px;font-size:11px;font-weight:600;">欠 {WEEKLY_MIN_ACTS - count} 次</span>'
            )
        else:
            chip += (
                '<span style="display:inline-block;margin-left:6px;background:#D1FAE5;color:#065F46;'
                'border-radius:999px;padding:2px 8px;font-size:11px;font-weight:600;">達標</span>'
            )
        meta = (
            f"<span>活動次數 <strong style='color:#1C2430;'>{count}</strong></span>"
            f"<span>最低要求 <strong style='color:#1C2430;'>{WEEKLY_MIN_ACTS}</strong></span>"
        )
        parts.append(
            _rank_shell(
                rank=rank,
                name=name,
                avatar=av,
                big=f"{score} 分",
                sub="本週活動分數",
                right=f"#{rank}",
                pct=pct,
                meta=meta,
                chip=chip,
            )
        )
    _render_rank_card_list(parts)


def render_recruit_cards(df: pd.DataFrame) -> None:
    """Recruitment dragon-tiger board — card list by recruit count."""
    if df is None or df.empty:
        st.info("暫無招募數據")
        return
    ranked = df.sort_values(by="recruit", ascending=False).reset_index(drop=True)
    max_rec = float(pd.to_numeric(ranked["recruit"], errors="coerce").fillna(0).max() or 0)
    bar_max = max(max_rec, 5.0)
    parts = []
    for i, row in ranked.iterrows():
        rank = i + 1
        recruit = int(float(row.get("recruit", 0) or 0))
        pct = min(max(recruit / bar_max * 100, 0), 100)
        name = _esc(row.get("username", ""))
        av = _esc(_avatar_url(row))
        score = int(float(row.get("Total_Score", 0) or 0))
        chip = ""
        if rank == 1 and recruit > 0:
            chip = (
                '<span style="display:inline-block;margin-left:6px;background:#F7F1DE;color:#7A6420;'
                'border-radius:999px;padding:2px 8px;font-size:11px;font-weight:600;">🏆 招募王</span>'
            )
        meta = f"<span>全年活動分 <strong style='color:#1C2430;'>{score}</strong></span>"
        parts.append(
            _rank_shell(
                rank=rank,
                name=name,
                avatar=av,
                big=str(recruit),
                sub="招募人數",
                right=f"#{rank}",
                pct=pct,
                meta=meta,
                chip=chip,
            )
        )
    _render_rank_card_list(parts)


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


def _render_stuck_case_rows(stuck: pd.DataFrame, *, key_prefix: str) -> None:
    """Compact 卡案 list with mark-done for coach view."""
    if stuck is None or stuck.empty:
        st.success("呢度暫時冇逾期／今日要跟嘅案。")
        return
    for _, row in stuck.iterrows():
        nd = row.get("next_date")
        try:
            nd_str = pd.to_datetime(nd).strftime("%Y-%m-%d") if pd.notna(nd) else "—"
        except Exception:
            nd_str = str(nd or "—")
        person = str(row.get("person") or "")
        track = str(row.get("track") or "")
        stage = str(row.get("stage") or "")
        action = str(row.get("next_action") or "")
        reason = str(row.get("stuck_reason") or "")
        owner = str(row.get("username") or "")
        overdue = int(row.get("overdue_days") or 0)
        flag = "🔴" if overdue > 0 else "🟡"
        owner_bit = f"**{owner}** · " if owner and key_prefix.startswith("team") else ""
        st.markdown(
            f"{flag} {owner_bit}**{person}**（{track}｜{stage}）  \n"
            f"卡關：{reason}  \n"
            f"Next：{action} · 日期 `{nd_str}`"
        )
        rid = row.get("id")
        b1, b2 = st.columns(2)
        with b1:
            if st.button("✓ 已跟進", key=f"{key_prefix}_done_{rid}", use_container_width=True):
                mark_followup_done(rid)
                st.toast(f"已完成：{person}", icon="✅")
                st.rerun()
        with b2:
            if st.button("去打卡更新", key=f"{key_prefix}_go_{rid}", use_container_width=True):
                st.session_state["_menu_choice"] = "📝 打卡 Check-in"
                st.session_state["ci_prefill_person"] = person
                st.session_state["ci_prefill_track"] = track
                st.rerun()
        st.divider()


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
            <li>經理視圖會對住<strong>卡案清單</strong>（未跟案），唔淨係打卡次數</li>
          </ul>
        </div>
        """,
        unsafe_allow_html=True,
    )

    show_rank = True
    if is_leader:
        tab_rank, tab_coach = st.tabs(["本週排行", "經理視圖"])
    else:
        tab_rank = st.container()
        tab_coach = None

    with tab_rank:
        if df.empty:
            st.info("本週暫無數據")
            show_rank = False
        if show_rank:
            max_score = df["wk_score"].max()
            winners = df[df["wk_score"] == max_score] if max_score > 0 else pd.DataFrame()
            pool = len(df[df["wk_count"] < WEEKLY_MIN_ACTS]) * WEEKLY_PENALTY
            st.markdown(
                f"### Prize Pool: <span style='color:#C5A028'>${pool if pool > 0 else WEEKLY_PENALTY}</span>",
                unsafe_allow_html=True,
            )
            if not winners.empty and max_score > 0:
                names = "、".join(str(u) for u in winners["username"].tolist())
                st.caption(f"本週暫時領先：👑 {names}")
            render_challenge_cards(df)

    if is_leader and tab_coach is not None:
        with tab_coach:
            st.caption(
                "一人一頁睇活動分、本月 FYC、未跟案同卡關原因；"
                "優先跟卡案，而唔淨係追打卡次數。"
            )
            overview = get_team_coach_overview()
            stuck_all = get_stuck_cases()

            c1, c2, c3 = st.columns(3)
            c1.metric("團隊卡案", int(len(stuck_all)))
            c2.metric(
                "欠活動人數",
                int(overview["needs_acts"].sum()) if not overview.empty else 0,
            )
            c3.metric(
                "有卡案同事",
                int((overview["stuck_count"] > 0).sum()) if not overview.empty else 0,
            )

            sub_stuck, sub_one = st.tabs(["卡案清單", "一人一頁"])

            with sub_stuck:
                st.markdown("#### 全隊未跟／逾期案")
                if overview.empty:
                    st.info("未有成員資料。")
                else:
                    # Quick triage chips
                    hot = overview[overview["stuck_count"] > 0]
                    if hot.empty:
                        st.success("全隊暫無逾期卡案 — 好！")
                    else:
                        for _, r in hot.iterrows():
                            st.markdown(
                                f"- **{r['username']}**：{int(r['stuck_count'])} 宗卡案"
                                f"（最長過期 {int(r['max_overdue'])} 日）"
                                f" · 本週 {int(r['wk_count'])}/{WEEKLY_MIN_ACTS} 次"
                                f" · MTD FYC ${float(r['mtd_fyc']):,.0f}"
                            )
                st.markdown("##### 明細")
                _render_stuck_case_rows(stuck_all, key_prefix="team_stuck")

            with sub_one:
                members = (
                    overview["username"].tolist()
                    if not overview.empty
                    else get_clean_users()
                    .query("role == 'Member'")["username"]
                    .astype(str)
                    .tolist()
                )
                if not members:
                    st.info("未有成員。")
                else:
                    # Default to most stuck member
                    default_idx = 0
                    pick = st.selectbox("揀同事", members, index=default_idx, key="coach_member_pick")
                    pack = get_coach_member_pack(pick)
                    st.markdown(f"### {pick}")
                    r1 = st.columns(2)
                    r1[0].metric("本週活動分", pack["wk_score"])
                    r1[1].metric("本週次數", f'{pack["wk_count"]}/{WEEKLY_MIN_ACTS}')
                    r2 = st.columns(2)
                    r2[0].metric("本月 FYC", f'${pack["mtd_fyc"]:,.0f}')
                    r2[1].metric("未跟案", pack["stuck_count"])
                    st.caption(
                        f"YTD FYC ${pack['ytd_fyc']:,.0f} · 全年活動分 {pack['year_score']}"
                        f" · 進行中跟進 {pack['open_followups']} 宗 · {pack['month']}"
                    )
                    if pack["needs_acts"]:
                        st.warning(
                            f"本週活動未達 {WEEKLY_MIN_ACTS} 次 — 有罰款風險；"
                            "同時优先清卡案。"
                        )
                    st.markdown("#### 卡案清單（未跟／逾期）")
                    _render_stuck_case_rows(pack["stuck_cases"], key_prefix=f"one_{pick}")


def page_recruit():
    st.markdown("## 招募龍虎榜")
    st.caption("按招募人數排名；第一名會標成招募王。")
    df = get_data("Yearly")
    if df.empty:
        st.info("暫無招募數據")
        return
    render_recruit_cards(df)


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
    if "mu_client_name" not in st.session_state:
        st.session_state["mu_client_name"] = ""
    st.text_input(
        "客戶名稱（可留空，會寫入 WhatsApp 摘要）",
        key="mu_client_name",
        placeholder="例如：陳生／陳太",
    )

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

    answer_rows = mu.summarize_answers(disease, answers)
    with st.expander("今次問答摘要"):
        for qlab, alab in answer_rows:
            st.markdown(f"- **{qlab}**：{alab}")
        st.markdown(f"- **對應情況**：{scenario.get('label_zh')}")

    try:
        from tt_core.whatsapp_share import medical_uw_summary

        wa_text = medical_uw_summary(
            client=str(st.session_state.get("mu_client_name") or ""),
            disease_zh=disease.get("name_zh") or "",
            disease_en=disease.get("name_en") or "",
            scenario_label=scenario.get("label_zh") or "",
            outcomes=outcomes,
            product_labels=mu.PRODUCT_LABELS,
            answer_rows=answer_rows,
            extra_reqs=list(extra),
        )
        _render_whatsapp_share(
            wa_text,
            key="mu_wa",
            caption="客戶版摘要會註明「只供參考、非最終核保」。",
        )
    except Exception as e:
        st.caption(f"WhatsApp 摘要暫時未能產生：{e}")

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

    # Reset MUST run before widgets that own these keys (Streamlit rule)
    if st.session_state.pop("_cf_pending_reset", False):
        for it in cf.INCOME_ITEMS + cf.EXPENSE_ITEMS:
            st.session_state[f"cf_{it['id']}"] = 0.0
        st.session_state["cf_client_name"] = ""

    # Seed session defaults once (before number_input / text_input)
    if "cf_client_name" not in st.session_state:
        st.session_state["cf_client_name"] = ""
    for it in cf.INCOME_ITEMS + cf.EXPENSE_ITEMS:
        k = f"cf_{it['id']}"
        if k not in st.session_state:
            st.session_state[k] = 0.0

    client = st.text_input(
        "客戶名稱（可留空）",
        key="cf_client_name",
        placeholder="例如：陳生／陳太",
    )

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

    hint = cf.budget_suggestion(cashflow)
    st.info(hint)
    st.caption(cf.PRODUCT_HINTS)

    if result["income"] > 0 or result["expense"] > 0:
        try:
            from tt_core.whatsapp_share import cashflow_summary

            income_lines = [
                (it["label"], float(income_vals.get(it["id"]) or 0))
                for it in cf.INCOME_ITEMS
            ]
            expense_lines = [
                (it["label"], float(expense_vals.get(it["id"]) or 0))
                for it in cf.EXPENSE_ITEMS
            ]
            wa_text = cashflow_summary(
                client=client,
                income=result["income"],
                expense=result["expense"],
                cashflow=cashflow,
                income_lines=income_lines,
                expense_lines=expense_lines,
                format_hkd=cf.format_hkd,
                budget_hint=hint,
            )
            _render_whatsapp_share(wa_text, key="cf_wa")
        except Exception as e:
            st.caption(f"WhatsApp 摘要暫時未能產生：{e}")

    c1, c2 = st.columns(2)
    with c1:
        if st.button("清空重計", use_container_width=True, key="cf_reset"):
            st.session_state["_cf_pending_reset"] = True
            st.rerun()
    with c2:
        st.caption("金額以港元／每月計。數字只留在此裝置 session，唔會自動上傳。")


def page_protection_gap():
    """見客用：輸入現有保障 → pie chart 展示保障缺口。"""
    st.markdown("## 🛡️ 保障缺口")
    st.caption(
        "輸入客戶已有保單（類型／公司／保額／保費），對比建議保額；"
        "四大保障狀態盤用等權重顯示人壽／危疾／醫療／意外——未做都會睇到。"
    )

    try:
        import importlib

        from tt_core import protection_gap as pg

        # Streamlit Cloud can keep a stale module after partial redeploy
        pg = importlib.reload(pg)
        if not hasattr(pg, "pillar_status"):
            raise AttributeError("protection_gap.pillar_status missing after reload")
    except Exception as e:
        st.error(f"保障缺口模組未能載入：{e}。請 Reboot app 後再試。")
        return

    main_types = ["人壽保險", "危疾保險", "醫療保險", "意外保險"]

    def _pg_clear_row_widget_keys(n: int = 40) -> None:
        for i in range(n):
            for suffix in ("type", "company", "cover", "premium"):
                st.session_state.pop(f"pg_r{i}_{suffix}", None)

    # Pending flags MUST apply before widgets that own these keys
    if st.session_state.pop("_pg_pending_reset", False):
        st.session_state["pg_client_name"] = ""
        st.session_state["pg_monthly_income"] = 0.0
        st.session_state["pg_rows"] = pg.empty_portfolio(3)
        _pg_clear_row_widget_keys()
        for t in pg.POLICY_TYPES:
            st.session_state.pop(f"pg_target_{t}", None)

    pending_targets = st.session_state.pop("_pg_pending_targets", None)
    if isinstance(pending_targets, dict):
        for t, val in pending_targets.items():
            st.session_state[f"pg_target_{t}"] = float(val or 0)

    if st.session_state.pop("_pg_add_row", False):
        rows_now = list(st.session_state.get("pg_rows") or [])
        rows_now.append(dict(pg.EMPTY_ROW))
        st.session_state["pg_rows"] = rows_now

    drop_idx = st.session_state.pop("_pg_drop_row", None)
    if isinstance(drop_idx, int):
        rows_now = list(st.session_state.get("pg_rows") or [])
        if 0 <= drop_idx < len(rows_now):
            # Rebuild widget keys from remaining rows after drop
            kept = [r for i, r in enumerate(rows_now) if i != drop_idx]
            _pg_clear_row_widget_keys()
            st.session_state["pg_rows"] = kept or pg.empty_portfolio(1)

    if "pg_client_name" not in st.session_state:
        st.session_state["pg_client_name"] = ""
    if "pg_monthly_income" not in st.session_state:
        st.session_state["pg_monthly_income"] = 0.0
    if "pg_rows" not in st.session_state:
        st.session_state["pg_rows"] = pg.empty_portfolio(3)

    client = st.text_input(
        "客戶名稱（可留空）",
        key="pg_client_name",
        placeholder="例如：陳生／陳太",
    )
    monthly_income = st.number_input(
        "每月收入（用來建議保額，可改）",
        min_value=0.0,
        step=1000.0,
        format="%.0f",
        key="pg_monthly_income",
        help="人壽約 10 倍年薪、危疾約 4 倍、意外約 3 倍；醫療預設 $1,000,000（可手動改）",
    )

    suggested = pg.suggested_targets(monthly_income)
    st.markdown("#### 建議保額（可人手調整）")
    target_cols = st.columns(4)
    targets: dict[str, float] = {}
    for col, t in zip(target_cols, main_types):
        with col:
            key = f"pg_target_{t}"
            if key not in st.session_state:
                st.session_state[key] = float(suggested.get(t) or 0)
            targets[t] = st.number_input(
                t.replace("保險", ""),
                min_value=0.0,
                step=100000.0,
                format="%.0f",
                key=key,
            )
    targets["其他"] = 0.0

    if st.button("按月入重設建議保額", key="pg_resync_targets"):
        st.session_state["_pg_pending_targets"] = {
            t: float(suggested.get(t) or 0) for t in main_types
        }
        st.rerun()

    st.markdown("#### 已有保單")
    st.caption("逐行輸入更穩陣（唔會㩒 Enter 就清數）。保險公司欄較窄，保額／保費較闊。")

    portfolio = list(st.session_state.get("pg_rows") or pg.empty_portfolio(3))
    # Seed row widget keys once from portfolio (never overwrite live widget values)
    for i, row in enumerate(portfolio):
        if f"pg_r{i}_type" not in st.session_state:
            st.session_state[f"pg_r{i}_type"] = str(row.get("保單類型") or "人壽保險")
        if f"pg_r{i}_company" not in st.session_state:
            st.session_state[f"pg_r{i}_company"] = str(row.get("保險公司") or "")
        if f"pg_r{i}_cover" not in st.session_state:
            st.session_state[f"pg_r{i}_cover"] = float(row.get("保額") or 0)
        if f"pg_r{i}_premium" not in st.session_state:
            st.session_state[f"pg_r{i}_premium"] = float(row.get("保費") or 0)

    # Header (desktop)
    if not MOBILE:
        h1, h2, h3, h4, h5 = st.columns([1.15, 0.85, 1.45, 1.25, 0.45])
        h1.caption("保單類型")
        h2.caption("保險公司")
        h3.caption("保額")
        h4.caption("保費（每月）")
        h5.caption("")

    collected: list[dict] = []
    for i in range(len(portfolio)):
        if MOBILE:
            st.markdown(f"**保單 {i + 1}**")
            ptype = st.selectbox(
                "保單類型",
                pg.POLICY_TYPES,
                key=f"pg_r{i}_type",
                label_visibility="collapsed",
            )
            company = st.text_input(
                "保險公司",
                key=f"pg_r{i}_company",
                placeholder="例如 AIA",
                label_visibility="collapsed",
            )
            c_a, c_b = st.columns([1.15, 1.0])
            with c_a:
                cover = st.number_input(
                    "保額",
                    min_value=0.0,
                    step=100000.0,
                    format="%.0f",
                    key=f"pg_r{i}_cover",
                )
            with c_b:
                premium = st.number_input(
                    "保費（每月）",
                    min_value=0.0,
                    step=100.0,
                    format="%.0f",
                    key=f"pg_r{i}_premium",
                )
            if st.button("刪除呢行", key=f"pg_del_{i}", use_container_width=True):
                st.session_state["_pg_drop_row"] = i
                st.rerun()
            st.divider()
        else:
            c1, c2, c3, c4, c5 = st.columns([1.15, 0.85, 1.45, 1.25, 0.45])
            with c1:
                ptype = st.selectbox(
                    "保單類型",
                    pg.POLICY_TYPES,
                    key=f"pg_r{i}_type",
                    label_visibility="collapsed",
                )
            with c2:
                company = st.text_input(
                    "保險公司",
                    key=f"pg_r{i}_company",
                    placeholder="AIA",
                    label_visibility="collapsed",
                )
            with c3:
                cover = st.number_input(
                    "保額",
                    min_value=0.0,
                    step=100000.0,
                    format="%.0f",
                    key=f"pg_r{i}_cover",
                    label_visibility="collapsed",
                )
            with c4:
                premium = st.number_input(
                    "保費",
                    min_value=0.0,
                    step=100.0,
                    format="%.0f",
                    key=f"pg_r{i}_premium",
                    label_visibility="collapsed",
                )
            with c5:
                if st.button("✕", key=f"pg_del_{i}", help="刪除呢行"):
                    st.session_state["_pg_drop_row"] = i
                    st.rerun()

        collected.append(
            {
                "保單類型": ptype,
                "保險公司": company,
                "保額": cover,
                "保費": premium,
            }
        )

    # Persist plain rows for navigation / reset (widgets keep live values via keys)
    st.session_state["pg_rows"] = collected

    b_add, b_hint = st.columns([1, 2])
    with b_add:
        if st.button("＋ 加多一份保單", use_container_width=True, key="pg_add_row"):
            st.session_state["_pg_add_row"] = True
            st.rerun()
    with b_hint:
        st.caption("輸入後數字會保留；唔使驚㩒 Enter。")

    rows = pg.normalize_rows(collected)
    gaps = pg.gap_table(rows, targets)
    total_prem = pg.total_monthly_premium(rows)
    total_gap = sum(float(g["保障缺口"]) for g in gaps if g["保單類型"] != "其他")
    total_have = sum(float(g["已有保額"]) for g in gaps if g["保單類型"] != "其他")

    pillars = pg.pillar_status(gaps)
    summary = pg.completeness_summary(pillars)

    name_bit = f" — {client.strip()}" if str(client or "").strip() else ""
    st.markdown(f"### 分析結果{name_bit}")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("四大保障達標", f'{summary["ready"]}/{summary["total"]}')
    m2.metric("已有保障總額", pg.format_hkd(total_have))
    m3.metric("保障缺口總額", pg.format_hkd(total_gap))
    m4.metric("現有每月保費", pg.format_hkd(total_prem))

    st.markdown("##### 四大保障狀態盤")
    st.caption("人壽／危疾／醫療／意外各佔一格（等權重）——未做嘅會用紅色顯示，唔會消失。")
    st.markdown(pg.svg_pillar_status_pie(pillars), unsafe_allow_html=True)

    st.markdown("##### 各類達標進度")
    st.markdown(pg.html_pillar_gap_bars(pillars), unsafe_allow_html=True)

    if gaps:
        st.markdown("##### 分類缺口明細")
        show = pd.DataFrame(gaps)
        st.dataframe(
            show,
            use_container_width=True,
            hide_index=True,
            column_config={
                "已有保額": st.column_config.NumberColumn(format="$%d"),
                "建議保額": st.column_config.NumberColumn(format="$%d"),
                "保障缺口": st.column_config.NumberColumn(format="$%d"),
                "已保障%": st.column_config.NumberColumn(format="%.1f%%"),
                "現有月保費": st.column_config.NumberColumn(format="$%d"),
            },
        )

    if summary["missing_names"] or summary["short_names"]:
        bits = []
        if summary["missing_names"]:
            bits.append("未做：**" + "／".join(summary["missing_names"]) + "**")
        if summary["short_names"]:
            bits.append("不足：**" + "／".join(summary["short_names"]) + "**")
        st.warning(
            f"四大保障未齊 — {'；'.join(bits)}。"
            f"金額缺口約 **{pg.format_hkd(total_gap)}**。"
        )
    elif rows:
        st.success("四大保障（人壽／危疾／醫療／意外）以而家建議保額計已達標。")
    else:
        st.info("請先輸入至少一份已有保單，或將建議保額同現況對比。")

    if pillars and (rows or total_gap > 0 or total_have > 0):
        try:
            from tt_core.whatsapp_share import protection_gap_summary

            wa_text = protection_gap_summary(
                client=client,
                pillars=pillars,
                summary=summary,
                total_have=total_have,
                total_gap=total_gap,
                total_prem=total_prem,
                format_hkd=pg.format_hkd,
            )
            _render_whatsapp_share(wa_text, key="pg_wa")
        except Exception as e:
            st.caption(f"WhatsApp 摘要暫時未能產生：{e}")

    st.caption(
        "建議保額只供銷售參考，並非核保或財務建議；實際需要視乎家庭責任、負債、Lifestyle。"
        "數字只留在此裝置 session。"
    )

    if st.button("清空重計", use_container_width=True, key="pg_reset"):
        st.session_state["_pg_pending_reset"] = True
        st.rerun()


def page_medical_finance():
    """見客用：5 年儲盈聚 → 第 6 年起提款繳醫家保，計最少年供。"""
    st.markdown("## 🏥 醫療融資計算機")
    st.caption(
        "輸入年齡／性別／通脹，計出用「盈聚‧天下 II（5 年供）」預留醫家保保費，"
        "第 6 年起每年提款＝當年醫保保費（隨年齡＋通脹上升）——最少要儲幾多年供。"
    )

    try:
        from tt_core import medical_finance as mf
    except Exception as e:
        st.error(f"醫療融資模組未能載入：{e}。請 Reboot 後再試。")
        return

    cal = mf.load_calibration()
    fx = float(cal.get("fx_usd_hkd") or 7.85)

    # Stepper-style progress
    st.markdown(
        """
        <div style="display:flex;gap:8px;flex-wrap:wrap;margin:0 0 14px 0;font-size:13px;">
          <span style="background:#1a1a2e;color:#F5D76E;padding:6px 12px;border-radius:999px;">1 關於你</span>
          <span style="background:#F3F4F6;color:#374151;padding:6px 12px;border-radius:999px;">2 醫家保</span>
          <span style="background:#F3F4F6;color:#374151;padding:6px 12px;border-radius:999px;">3 通脹假設</span>
          <span style="background:#F3F4F6;color:#374151;padding:6px 12px;border-radius:999px;">4 融資結果</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("#### 你的基本資料")
    c1, c2 = st.columns(2)
    with c1:
        client = st.text_input("客戶名稱（可留空）", key="mf_client", placeholder="例如：陳生")
        age = st.slider("現時年齡（實際年齡）", min_value=18, max_value=60, value=30, key="mf_age")
    with c2:
        gender = st.radio("性別", ["男", "女"], horizontal=True, key="mf_gender")
        smoke = st.radio("吸煙習慣（儲蓄計劃示範用）", ["非吸煙", "吸煙"], horizontal=True, key="mf_smoke")

    st.markdown("#### 醫保同通脹")
    st.info("第一版固定：**醫家保醫療計劃（獨立保單）** · 年繳保費表")
    inflation_pct = st.slider(
        "未來每年保費加幅 %（疊加喺年齡跳價之上）",
        min_value=0.0,
        max_value=5.0,
        value=2.61,
        step=0.01,
        key="mf_infl",
    )
    quick = st.columns(3)
    if quick[0].button("0%", key="mf_i0"):
        st.session_state["mf_infl"] = 0.0
        st.rerun()
    if quick[1].button("2.61%", key="mf_i261"):
        st.session_state["mf_infl"] = 2.61
        st.rerun()
    if quick[2].button("5%", key="mf_i5"):
        st.session_state["mf_infl"] = 5.0
        st.rerun()

    end_age = st.slider("試算至年齡", min_value=70, max_value=100, value=100, key="mf_end")
    st.caption(
        f"儲蓄產品：{cal.get('product_name')}（美元保單）· 匯率 1 USD = {fx} HKD · "
        f"吸煙選項：{smoke}（醫家保表為標準保費，唔分吸煙）· "
        f"累積倍數已用 25–50 歲男女計劃書校準（年齡唔改倍數，只改醫保保費表）"
    )

    if st.button("計算最少年供", type="primary", use_container_width=True, key="mf_run"):
        st.session_state["mf_result"] = mf.min_annual_savings_usd(
            start_age=int(age),
            gender=gender,
            inflation=float(inflation_pct) / 100.0,
            end_age=int(end_age),
            fx=fx,
        )

    result = st.session_state.get("mf_result")
    if not result:
        st.markdown("##### 資料預覽")
        now_prem = mf.medical_annual_hkd(int(age), gender)
        st.markdown(
            f"**{age} 歲 · {gender} · {smoke}**  \n"
            f"而家醫家保年繳約 **{mf.format_hkd(now_prem)}** · "
            f"第 6 年起（約 {age + 5} 歲）開始由儲蓄提款至 {end_age} 歲。"
        )
        return

    if result.get("error"):
        st.error(result["error"])
        return

    st.markdown("### 融資結果")
    st.markdown(
        f"""
        <div style="border:1px solid #E5E7EB;border-radius:14px;padding:16px 18px;
        background:linear-gradient(180deg,#FFFDF5 0%,#FFFFFF 100%);margin-bottom:12px;">
          <div style="color:#6B7280;font-size:0.9rem;">最少年供（連續儲 5 年）</div>
          <div style="font-family:Georgia,serif;font-size:1.85rem;font-weight:700;color:#1a1a2e;margin:4px 0;">
            {mf.format_usd(result['annual_prem_usd'])}／年
          </div>
          <div style="color:#9A7B1A;font-size:1.1rem;font-weight:700;">
            約 {mf.format_hkd(result['annual_prem_hkd'])}／年
          </div>
          <div style="color:#6B7280;font-size:0.88rem;margin-top:8px;">
            5 年合共 {mf.format_usd(result['total_5yr_usd'])}
            （約 {mf.format_hkd(result['total_5yr_hkd'])}）· 匯率 {fx}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    m1, m2, m3 = st.columns(3)
    m1.metric("開始提款年齡", f"{result['first_withdraw_age']} 歲")
    m2.metric("提款年期", f"{result['n_withdraw_years']} 年")
    m3.metric("最高一年醫保", mf.format_hkd(result["peak_medical_hkd"]))

    st.markdown(
        f"**準備方法：** 前期用收入繳醫保；同時 5 年供盈聚。"
        f"由 **{result['first_withdraw_age']} 歲** 起，每年由儲蓄提款繳當年醫家保"
        f"（已計入年齡跳價 + {inflation_pct:.2f}% 通脹），去到 **{end_age} 歲**。"
    )

    # Simple bar preview: contribution vs withdrawals (sample ages)
    wds = result.get("withdrawals") or []
    if wds:
        st.markdown("##### 提款／保費走勢（揀數年）")
        sample_ages = []
        for a in [
            result["first_withdraw_age"],
            50,
            65,
            80,
            end_age,
        ]:
            if result["first_withdraw_age"] <= a <= end_age and a not in sample_ages:
                sample_ages.append(a)
        by_age = {w["age"]: w for w in wds}
        for a in sample_ages:
            w = by_age.get(a)
            if not w:
                continue
            st.markdown(
                f"- **{a} 歲**：提款／保費 {mf.format_hkd(w['premium_hkd'])}"
                f"（{mf.format_usd(w['withdraw_usd'])}）"
            )
        with st.expander("完整每年提款表（通脹後）"):
            show = pd.DataFrame(wds)[["age", "policy_year", "premium_hkd", "withdraw_usd"]]
            show = show.rename(
                columns={
                    "age": "年齡",
                    "policy_year": "保單年度",
                    "premium_hkd": "醫保年繳 (HKD)",
                    "withdraw_usd": "提款 (USD)",
                }
            )
            st.dataframe(show, use_container_width=True, hide_index=True)

    try:
        wa = mf.whatsapp_summary(result, client=client)
        _render_whatsapp_share(
            wa,
            key="mf_wa",
            caption="客戶版試算摘要（含非保證／非正式報價聲明）。",
        )
    except Exception as e:
        st.caption(f"WhatsApp 摘要暫時未能產生：{e}")

    st.caption(
        "試算以現行醫家保標準保費表 + 盈聚計劃書校準嘅戶口滾存假設（非保證）。"
        "實際紅利／退保價值可能較高或較低，甚至為零；並非正式報價。"
    )


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
elif "保障缺口" in menu:
    _safe_page("保障缺口", page_protection_gap)
elif "醫療融資" in menu:
    _safe_page("醫療融資計算機", page_medical_finance)
elif "設定" in menu:
    _safe_page("設定", page_profile)

# cloud_redeploy_stamp: 2026-10-16T02:10Z
