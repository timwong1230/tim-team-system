"""Google Drive inbox for FWD Iris exports.

Most convenient workflow without Iris API:
1. Export report from Iris (Excel/CSV)
2. Save into a Drive folder shared with the app service account
3. Leader taps「同步最新檔」— no manual upload each time
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
IRIS_FOLDER_KEY = "iris_drive_folder_id"
LAST_FILE_KEY = "iris_drive_last_file_id"


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
    # Secrets override (Streamlit Cloud)
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
    now = str(_dt.datetime.now())
    if not df.empty and "key" in df.columns:
        hit = df[df["key"].astype(str) == key]
        if not hit.empty and "id" in df.columns and str(hit.iloc[0].get("id", "")).strip():
            return bool(
                run_query_gs(
                    "UPDATE",
                    SETTINGS_SHEET,
                    {"value": value, "updated_at": now},
                    row_id=hit.iloc[0]["id"],
                )
            )
    return bool(
        run_query_gs(
            "INSERT",
            SETTINGS_SHEET,
            {"key": key, "value": value, "updated_at": now},
        )
    )


def get_folder_id() -> str:
    return get_setting(IRIS_FOLDER_KEY, "").strip()


def save_folder_id(folder_id: str) -> bool:
    # Accept full Drive URL or bare id
    folder_id = folder_id.strip()
    if "/folders/" in folder_id:
        folder_id = folder_id.split("/folders/")[1].split("?")[0].split("/")[0]
    return set_setting(IRIS_FOLDER_KEY, folder_id)


def list_inbox_files(folder_id: str | None = None, limit: int = 15) -> list[dict[str, Any]]:
    """List recent Excel/CSV files in the Iris inbox folder."""
    service = get_drive_service()
    folder_id = (folder_id or get_folder_id()).strip()
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


def mark_file_synced(file_id: str) -> None:
    set_setting(LAST_FILE_KEY, file_id)


def last_synced_file_id() -> str:
    return get_setting(LAST_FILE_KEY, "")


def has_new_inbox_file() -> dict[str, Any] | None:
    """Return newest file if it differs from last synced file id."""
    f = newest_file()
    if not f:
        return None
    if f.get("id") and f["id"] != last_synced_file_id():
        return f
    return None
