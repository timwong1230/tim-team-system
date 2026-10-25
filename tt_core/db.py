"""Resilient Google Sheets layer with disk cache + stale-while-revalidate."""

from __future__ import annotations

import json
import os
import random
import time
from typing import Any

import gspread
import pandas as pd
import streamlit as st
from google.oauth2.service_account import Credentials
from gspread.exceptions import APIError, WorksheetNotFound

from tt_core import cache_store
from tt_core.constants import SHEET_SCHEMAS

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# Serve cache instantly; refresh in background TTL window
CACHE_TTL_SEC = int(os.environ.get("TIM_TEAM_CACHE_TTL", "180"))  # 3 min
STALE_MAX_SEC = int(os.environ.get("TIM_TEAM_STALE_MAX", "86400"))  # 24h still usable
MAX_RETRIES = 4
SPREADSHEET_NAME = "tim_team_db"

CORE_SHEETS = [
    "users",
    "monthly_fyc",
    "activities",
    "followups",
    "story_ammo",
    "quarterly_offers",
    "iris_agent_map",
    "iris_sync_log",
    "system_settings",
    "common_forms",
    "prospects",
]


def _backoff_sleep(attempt: int) -> None:
    time.sleep(min(8.0, (0.4 * (2**attempt)) + random.uniform(0, 0.3)))


def _credentials_dict() -> dict | None:
    try:
        if "service_account" in st.secrets:
            return json.loads(st.secrets["service_account"]["key_content"])
        if "GSPREAD_KEY" in os.environ:
            return json.loads(os.environ["GSPREAD_KEY"])
    except Exception:
        return None
    return None


# Connect / read timeouts (seconds). Without these, a hung Google API call
# freezes Streamlit on a white spinner forever after reboot.
_GS_CONNECT_TIMEOUT = float(os.environ.get("TIM_TEAM_GS_CONNECT_TIMEOUT", "8"))
_GS_READ_TIMEOUT = float(os.environ.get("TIM_TEAM_GS_READ_TIMEOUT", "25"))


@st.cache_resource(show_spinner=False)
def get_gs_client():
    key_dict = _credentials_dict()
    if not key_dict:
        return None
    try:
        creds = Credentials.from_service_account_info(key_dict, scopes=SCOPES)
        client = gspread.authorize(creds)
        try:
            client.http_client.set_timeout((_GS_CONNECT_TIMEOUT, _GS_READ_TIMEOUT))
        except Exception:
            pass
        return client
    except Exception:
        return None


@st.cache_resource(show_spinner=False)
def get_spreadsheet():
    """Open the workbook once per server process."""
    client = get_gs_client()
    if not client:
        return None
    for attempt in range(MAX_RETRIES):
        try:
            return client.open(SPREADSHEET_NAME)
        except Exception:
            _backoff_sleep(attempt)
    return None


def get_sheet(sheet_name: str):
    sh = get_spreadsheet()
    if not sh:
        return None
    for attempt in range(MAX_RETRIES):
        try:
            try:
                return sh.worksheet(sheet_name)
            except WorksheetNotFound:
                cols = max(len(SHEET_SCHEMAS.get(sheet_name, [])), 11)
                return sh.add_worksheet(title=sheet_name, rows=2000, cols=cols)
        except Exception:
            _backoff_sleep(attempt)
    return None


def _normalize_df(df: pd.DataFrame, sheet_name: str) -> pd.DataFrame:
    expected_cols = SHEET_SCHEMAS.get(sheet_name, [])
    for col in expected_cols:
        if col not in df.columns:
            df[col] = ""
    if expected_cols:
        ordered = expected_cols + [c for c in df.columns if c not in expected_cols]
        df = df[ordered]
    if "id" in df.columns and not df.empty:
        df = df.copy()
        df["id"] = df["id"].map(cache_store.normalize_id)
    return df


def _values_to_df(values: list[list], sheet_name: str) -> pd.DataFrame:
    if not values:
        return _normalize_df(pd.DataFrame(), sheet_name)
    headers = [str(h).strip() if h is not None else "" for h in values[0]]
    # Deduplicate empty / duplicate headers
    seen = {}
    clean_headers = []
    for h in headers:
        name = h or "col"
        if name in seen:
            seen[name] += 1
            name = f"{name}_{seen[name]}"
        else:
            seen[name] = 0
        clean_headers.append(name)
    rows = values[1:]
    records = []
    for row in rows:
        if not any(str(c).strip() for c in row):
            continue
        padded = list(row) + [""] * (len(clean_headers) - len(row))
        records.append(dict(zip(clean_headers, padded[: len(clean_headers)])))
    return _normalize_df(pd.DataFrame(records), sheet_name)


def _fetch_sheet_from_gs(sheet_name: str) -> pd.DataFrame | None:
    ws = get_sheet(sheet_name)
    if not ws:
        return None
    last_err = None
    for attempt in range(MAX_RETRIES):
        try:
            # get_all_values is usually more reliable than get_all_records
            values = ws.get_all_values()
            return _values_to_df(values, sheet_name)
        except APIError as e:
            last_err = e
            # Rate limit / backend error → backoff
            _backoff_sleep(attempt)
        except Exception as e:
            last_err = e
            _backoff_sleep(attempt)
    if last_err:
        cache_store.touch_status(False, str(last_err)[:200])
    return None


def _cache_age(meta: dict) -> float | None:
    saved = meta.get("saved_at")
    if not saved:
        return None
    return time.time() - float(saved)


def _set_read_meta(sheet_name: str, *, from_cache: bool, stale: bool = False):
    st.session_state["_data_status"] = {
        "sheet": sheet_name,
        "from_cache": from_cache,
        "stale": stale,
        "at": time.time(),
    }


def read_data(sheet_name: str, *, force: bool = False) -> pd.DataFrame:
    """
    Read with stale-while-revalidate:
    1) fresh disk/memory cache → instant return
    2) else try Google Sheets (retries)
    3) on failure → return stale cache up to 24h rather than empty
    """
    expected_cols = SHEET_SCHEMAS.get(sheet_name, [])
    cached_df, meta = cache_store.load_sheet(sheet_name)
    age = _cache_age(meta)

    if (
        not force
        and cached_df is not None
        and age is not None
        and age < CACHE_TTL_SEC
    ):
        _set_read_meta(sheet_name, from_cache=True, stale=False)
        return _normalize_df(cached_df, sheet_name)

    fresh = _fetch_sheet_from_gs(sheet_name)
    if fresh is not None:
        cache_store.save_sheet(sheet_name, fresh, source="sheets")
        cache_store.touch_status(True, "ok")
        # Never put DataFrames in session_state — Cloud OOM / sticky Oh-no
        st.session_state.pop(f"backup_{sheet_name}", None)
        _set_read_meta(sheet_name, from_cache=False, stale=False)
        return fresh

    # Sheets failed — prefer stale disk/memory cache (not session_state)
    if cached_df is not None and (age is None or age < STALE_MAX_SEC):
        _set_read_meta(sheet_name, from_cache=True, stale=True)
        st.session_state.pop(f"backup_{sheet_name}", None)
        return _normalize_df(cached_df, sheet_name)

    _set_read_meta(sheet_name, from_cache=False, stale=True)
    return pd.DataFrame(columns=expected_cols)


def warm_cache(force: bool = False) -> dict:
    """Prefetch core sheets into disk cache. Called once per session / on refresh."""
    results = {}
    started = time.time()
    budget = float(os.environ.get("TIM_TEAM_WARM_BUDGET_SEC", "45"))
    for name in CORE_SHEETS:
        if time.time() - started > budget:
            results[name] = {"ok": False, "error": "warm_budget_exceeded"}
            continue
        try:
            df = read_data(name, force=force)
            results[name] = {"ok": True, "rows": len(df)}
        except Exception as e:
            results[name] = {"ok": False, "error": str(e)[:120]}
    st.session_state["_warmed_at"] = time.time()
    return results


def clear_cache():
    """Invalidate Streamlit + memory cache (disk kept as safety net)."""
    cache_store.invalidate_memory()
    try:
        st.cache_data.clear()
    except Exception:
        pass
    # Force spreadsheet handle refresh on next hard failure path
    try:
        get_spreadsheet.clear()
        get_gs_client.clear()
    except Exception:
        pass


def soft_invalidate(sheet_name: str | None = None):
    """Drop memory TTL so next read refreshes, keep disk fallback."""
    cache_store.invalidate_memory(sheet_name)


def ensure_headers(ws, sheet_name: str):
    schema = SHEET_SCHEMAS.get(sheet_name, [])
    headers = list(ws.row_values(1) or [])
    if not headers:
        if schema:
            ws.append_row(schema, value_input_option="USER_ENTERED")
        return list(schema)
    # Append any new schema columns missing from an existing sheet
    for col in schema:
        if col not in headers:
            ws.update_cell(1, len(headers) + 1, col)
            headers.append(col)
    return headers


def _with_sheet_retry(fn, retries: int = MAX_RETRIES):
    last = None
    for attempt in range(retries):
        try:
            return fn()
        except Exception as e:
            last = e
            _backoff_sleep(attempt)
    if last:
        raise last


def _find_sheet_row_by_id(ws, row_id) -> int | None:
    """1-based sheet row for ``id`` column only — never match quarter/year/etc."""
    target = cache_store.normalize_id(row_id)
    if not target:
        return None
    headers = list(ws.row_values(1) or [])
    if not headers:
        return None
    try:
        id_col = headers.index("id") + 1
    except ValueError:
        id_col = 1
    values = ws.col_values(id_col) or []
    for idx, raw in enumerate(values):
        if idx == 0:
            continue  # header
        if cache_store.normalize_id(raw) == target:
            return idx + 1  # 1-based
    return None


def _restore_sheet_cache(sheet_name: str) -> None:
    """Undo optimistic cache when Sheets write missed the real row."""
    fresh = _fetch_sheet_from_gs(sheet_name)
    if fresh is not None:
        cache_store.save_sheet(sheet_name, fresh, source="sheets")
    else:
        soft_invalidate(sheet_name)


def run_query_gs(action: str, sheet_name: str, data_dict: dict | None = None, row_id=None):
    """Write to Sheets, with optimistic local cache update first."""
    data_dict = dict(data_dict or {})
    if row_id is not None:
        row_id = cache_store.normalize_id(row_id) or row_id

    # --- Optimistic local update (UI stays fast even if Sheets lags) ---
    if action == "INSERT":
        if sheet_name in {
            "activities",
            "followups",
            "monthly_fyc",
            "story_ammo",
            "quarterly_offers",
            "iris_sync_log",
            "system_settings",
            "common_forms",
            "prospects",
        }:
            if "id" not in data_dict or not data_dict["id"]:
                data_dict["id"] = cache_store.next_id(sheet_name)
            data_dict["id"] = cache_store.normalize_id(data_dict["id"]) or data_dict["id"]
        cache_store.upsert_row_cache(sheet_name, data_dict)
    elif action == "UPDATE" and row_id is not None:
        row = {"id": row_id, **data_dict}
        cache_store.upsert_row_cache(sheet_name, row)
    elif action == "DELETE" and row_id is not None:
        cache_store.delete_row_cache(sheet_name, row_id)

    ws = get_sheet(sheet_name)
    if not ws:
        st.warning("雲端暫時連唔上，已先存在本機快取；稍後按「重新整理」會再同步。")
        return False

    try:
        if action == "INSERT":

            def _insert():
                headers = ensure_headers(ws, sheet_name)
                row_to_add = [str(data_dict.get(h, "")) for h in headers]
                ws.append_row(row_to_add, value_input_option="USER_ENTERED")

            _with_sheet_retry(_insert)

        elif action == "UPDATE":
            sheet_row = _with_sheet_retry(lambda: _find_sheet_row_by_id(ws, row_id))
            if not sheet_row:
                _restore_sheet_cache(sheet_name)
                cache_store.touch_status(False, f"update_missing_id:{row_id}")
                st.error("搵唔到呢筆資料（可能已被刪除）。已還原雲端版本，請重新整理後再試。")
                return False

            def _update():
                headers = ws.row_values(1)
                cells = []
                for col, val in data_dict.items():
                    if col in headers:
                        cells.append(
                            gspread.Cell(sheet_row, headers.index(col) + 1, str(val))
                        )
                if cells:
                    ws.update_cells(cells, value_input_option="USER_ENTERED")

            _with_sheet_retry(_update)

        elif action == "DELETE":
            sheet_row = _with_sheet_retry(lambda: _find_sheet_row_by_id(ws, row_id))
            if not sheet_row:
                _restore_sheet_cache(sheet_name)
                cache_store.touch_status(False, f"delete_missing_id:{row_id}")
                st.error("搵唔到呢筆資料刪除。已還原雲端版本，請重新整理後再試。")
                return False

            def _delete():
                ws.delete_rows(sheet_row)

            _with_sheet_retry(_delete)

        cache_store.touch_status(True, "write_ok")
        soft_invalidate(sheet_name)
        return True
    except Exception as e:
        cache_store.touch_status(False, str(e)[:200])
        st.error(f"雲端寫入失敗（本機已暫存）：{e}")
        return False


@st.cache_resource(show_spinner=False)
def init_db_gs():
    """Light schema bootstrap once per process — do NOT block boot on full sheet pulls.

    Full cache priming happens in ``warm_cache`` after login (with spinner).
    Pulling every CORE_SHEET here used to freeze Cloud on a white spinner when
    Google API stalled after reboot.
    """
    started = time.time()
    budget = float(os.environ.get("TIM_TEAM_INIT_BUDGET_SEC", "35"))
    try:
        ws = get_sheet("users")
        if ws:
            try:
                existing = ws.col_values(1)
            except Exception:
                existing = []
            if not existing:
                ws.append_row(SHEET_SCHEMAS["users"], value_input_option="USER_ENTERED")
                existing = ["username"]
            try:
                from tt_core.constants import SEED_USERS

                defaults = list(SEED_USERS)
            except Exception:
                defaults = [
                    ("Admin", "admin123", "Leader"),
                    ("Tim", "1234", "Member"),
                    ("Oscar", "1234", "Member"),
                    ("KK", "1234", "Member"),
                    ("guest", "1234", "Guest"),
                ]
            existing_l = {str(x).strip().lower() for x in existing}
            for u in defaults:
                if time.time() - started > budget:
                    break
                if u[0].lower() not in existing_l:
                    url = (
                        f"https://ui-avatars.com/api/?name={u[0]}"
                        f"&background=d4af37&color=fff&size=128"
                    )
                    ws.append_row(
                        [u[0], u[1], u[2], "Tim Team", 0, url, ""],
                        value_input_option="USER_ENTERED",
                    )
                    existing_l.add(u[0].lower())

        for sn in CORE_SHEETS:
            if time.time() - started > budget:
                break
            if sn == "users":
                continue
            ws_tmp = get_sheet(sn)
            if not ws_tmp:
                continue
            try:
                headers = ws_tmp.row_values(1)
                if not headers:
                    ws_tmp.append_row(SHEET_SCHEMAS[sn], value_input_option="USER_ENTERED")
                elif sn == "monthly_fyc":
                    for col in ["source", "updated_at"]:
                        if col not in headers:
                            ws_tmp.update_cell(1, len(headers) + 1, col)
                            headers.append(col)
            except Exception:
                pass

        # Ensure headers only — warm_cache after login fills disk cache
        cache_store.touch_status(True, "init_ok")
        return True
    except Exception as e:
        cache_store.touch_status(False, f"init:{e}"[:200])
        return False


def update_user_field(username: str, field: str, value: Any) -> bool:
    # Optimistic: patch users cache
    df, _ = cache_store.load_sheet("users")
    if df is not None and not df.empty and "username" in df.columns:
        mask = df["username"].astype(str) == str(username)
        if mask.any():
            df.loc[mask, field] = str(value)
            cache_store.save_sheet("users", df, source="optimistic")

    ws = get_sheet("users")
    if not ws:
        st.warning("雲端暫時連唔上，個人設定已暫存本機。")
        return False
    try:

        def _upd():
            cell = ws.find(username)
            if not cell:
                return False
            headers = ws.row_values(1)
            if field not in headers:
                return False
            ws.update_cell(cell.row, headers.index(field) + 1, value)
            return True

        ok = _with_sheet_retry(_upd)
        soft_invalidate("users")
        return bool(ok)
    except Exception as e:
        st.error(f"更新失敗: {e}")
        return False


def connection_banner_state() -> dict:
    """UI helper: overall connection health."""
    status = cache_store.get_status()
    sess = st.session_state.get("_data_status", {})
    age = status.get("age_sec")
    if age is None:
        level = "unknown"
        label = "尚未載入數據"
    elif sess.get("stale") or (status.get("ok") is False):
        level = "degraded"
        label = f"使用離線快取（約 {int(age // 60)} 分鐘前）"
    elif age < CACHE_TTL_SEC:
        level = "ok"
        label = f"數據暢通（快取 {int(age)}s）"
    else:
        level = "ok"
        label = f"數據就緒（{int(age // 60)} 分鐘前更新）"
    return {"level": level, "label": label, "age": age, "raw": status}
