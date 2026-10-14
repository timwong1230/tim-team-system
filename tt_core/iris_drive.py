"""Google Drive inboxes for TIM TEAM reports.

Two report folders (recommended):
1. Daily Production → monthly FYC (MTD-COMPLETION)
2. MDRT Progress → Leaderboard temporary progress (Total Credit eligible for MDRT)

Legacy single-folder key `iris_drive_folder_id` is treated as the Daily folder.
"""

from __future__ import annotations

import io
import json
from typing import Any

import streamlit as st
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

from tt_core.db import SCOPES, _credentials_dict, read_data, run_query_gs

SETTINGS_SHEET = "system_settings"

# Daily production report inbox (MTD-COMPLETION → monthly FYC)
DAILY_FOLDER_KEY = "iris_drive_folder_id"
LAST_DAILY_FILE_KEY = "iris_drive_last_file_id"

# MDRT progress report inbox (Total Credit eligible for MDRT)
MDRT_FOLDER_KEY = "mdrt_drive_folder_id"
LAST_MDRT_FILE_KEY = "mdrt_drive_last_file_id"

# Back-compat aliases
IRIS_FOLDER_KEY = DAILY_FOLDER_KEY
LAST_FILE_KEY = LAST_DAILY_FILE_KEY


@st.cache_resource(show_spinner=False)
def get_drive_service():
    key = _credentials_dict()
    if not key:
        return None
    try:
        creds = Credentials.from_service_account_info(key, scopes=SCOPES)
        return build("drive", "v3", credentials=creds, cache_discovery=False)
    except Exception:
        return None


def service_account_email() -> str | None:
    key = _credentials_dict()
    if not key:
        return None
    return key.get("client_email")


def _settings_df():
    df = read_data(SETTINGS_SHEET)
    if df.empty:
        return df
    return df


def get_setting(key: str, default: str = "") -> str:
    try:
        ss = st.session_state.get(f"_setting_{key}")
        if ss is not None and str(ss).strip():
            return str(ss).strip()
    except Exception:
        pass
    try:
        if "iris" in st.secrets and key.replace("iris_", "") in st.secrets["iris"]:
            short = key.replace("iris_", "")
            return str(st.secrets["iris"][short])
        if key in st.secrets:
            return str(st.secrets[key])
    except Exception:
        pass

    df = _settings_df()
    if df.empty or "key" not in df.columns:
        return default
    hit = df[df["key"].astype(str) == key]
    if hit.empty:
        return default
    return str(hit.iloc[0].get("value", default) or default)


def set_setting(key: str, value: str) -> bool:
    import datetime as _dt

    df = _settings_df()
    value = str(value or "").strip()
    if not value:
        return False
    now = str(_dt.datetime.now())
    try:
        st.session_state[f"_setting_{key}"] = value
    except Exception:
        pass

    sheets_ok = False
    try:
        if not df.empty and "key" in df.columns:
            hit = df[df["key"].astype(str) == key]
            if (
                not hit.empty
                and "id" in df.columns
                and str(hit.iloc[0].get("id", "")).strip()
            ):
                sheets_ok = bool(
                    run_query_gs(
                        "UPDATE",
                        SETTINGS_SHEET,
                        {"value": value, "updated_at": now},
                        row_id=hit.iloc[0]["id"],
                    )
                )
            else:
                sheets_ok = bool(
                    run_query_gs(
                        "INSERT",
                        SETTINGS_SHEET,
                        {"key": key, "value": value, "updated_at": now},
                    )
                )
        else:
            sheets_ok = bool(
                run_query_gs(
                    "INSERT",
                    SETTINGS_SHEET,
                    {"key": key, "value": value, "updated_at": now},
                )
            )
    except Exception:
        sheets_ok = False

    # Local cache/session is enough for the app to keep working when Sheets is slow
    if sheets_ok:
        return True
    return get_setting(key, "") == value


def _normalize_folder_id(folder_id: str) -> str:
    folder_id = (folder_id or "").strip()
    if "/folders/" in folder_id:
        folder_id = folder_id.split("/folders/")[1].split("?")[0].split("/")[0]
    return folder_id


def get_daily_folder_id() -> str:
    return get_setting(DAILY_FOLDER_KEY, "").strip()


def get_mdrt_folder_id() -> str:
    return get_setting(MDRT_FOLDER_KEY, "").strip()


def save_daily_folder_id(folder_id: str) -> bool:
    return set_setting(DAILY_FOLDER_KEY, _normalize_folder_id(folder_id))


def save_mdrt_folder_id(folder_id: str) -> bool:
    return set_setting(MDRT_FOLDER_KEY, _normalize_folder_id(folder_id))


# Back-compat
def get_folder_id() -> str:
    return get_daily_folder_id()


def save_folder_id(folder_id: str) -> bool:
    return save_daily_folder_id(folder_id)


def list_inbox_files(folder_id: str | None = None, limit: int = 15) -> list[dict[str, Any]]:
    """List recent Excel/CSV files in a Drive folder."""
    service = get_drive_service()
    folder_id = (folder_id or get_daily_folder_id()).strip()
    if not service or not folder_id:
        return []

    q = (
        f"'{folder_id}' in parents and trashed=false and ("
        "mimeType='text/csv' or "
        "mimeType='application/vnd.ms-excel' or "
        "mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' or "
        "name contains '.csv' or name contains '.xlsx' or name contains '.xls'"
        ")"
    )
    try:
        resp = (
            service.files()
            .list(
                q=q,
                spaces="drive",
                fields="files(id,name,mimeType,modifiedTime,size)",
                orderBy="modifiedTime desc",
                pageSize=limit,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            )
            .execute()
        )
        return resp.get("files", [])
    except Exception as e:
        st.session_state["_iris_drive_error"] = str(e)[:240]
        return []


def download_file(file_id: str) -> bytes:
    service = get_drive_service()
    if not service:
        raise RuntimeError("Drive 未連接（檢查 service account）")
    request = service.files().get_media(fileId=file_id, supportsAllDrives=True)
    buf = io.BytesIO()
    downloader = MediaIoBaseDownload(buf, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return buf.getvalue()


def newest_file(folder_id: str | None = None) -> dict[str, Any] | None:
    files = list_inbox_files(folder_id=folder_id, limit=1)
    return files[0] if files else None


def mark_daily_file_synced(file_id: str) -> None:
    set_setting(LAST_DAILY_FILE_KEY, file_id)


def mark_mdrt_file_synced(file_id: str) -> None:
    set_setting(LAST_MDRT_FILE_KEY, file_id)


def mark_file_synced(file_id: str) -> None:
    """Back-compat: mark daily file synced."""
    mark_daily_file_synced(file_id)


def last_daily_synced_file_id() -> str:
    return get_setting(LAST_DAILY_FILE_KEY, "")


def last_mdrt_synced_file_id() -> str:
    return get_setting(LAST_MDRT_FILE_KEY, "")


def last_synced_file_id() -> str:
    return last_daily_synced_file_id()


def has_new_inbox_file() -> dict[str, Any] | None:
    """Return newest unread file from either inbox (prefers daily)."""
    daily = newest_file(get_daily_folder_id() or None)
    if daily and daily.get("id") and daily["id"] != last_daily_synced_file_id():
        return {**daily, "report_kind": "daily"}
    mdrt_folder = get_mdrt_folder_id()
    if mdrt_folder:
        mdrt = newest_file(mdrt_folder)
        if mdrt and mdrt.get("id") and mdrt["id"] != last_mdrt_synced_file_id():
            return {**mdrt, "report_kind": "mdrt"}
    return None
