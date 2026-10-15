"""常用表格：簽單 / 行政文件上傳到 Google Drive，清單存在 Sheets。"""

from __future__ import annotations

import datetime
import io
import mimetypes
from typing import Any

import pandas as pd
import streamlit as st
from googleapiclient.http import MediaIoBaseUpload

from tt_core.db import read_data, run_query_gs
from tt_core.iris_drive import (
    download_file,
    get_drive_service,
    get_setting,
    service_account_email,
    set_setting,
)

SHEET = "common_forms"
FOLDER_KEY = "common_forms_folder_id"

CATEGORIES = [
    "簽單表格",
    "行政文件",
    "培訓資料",
    "客戶文件",
    "其他",
]

ALLOWED_EXT = {
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


def get_folder_id() -> str:
    return get_setting(FOLDER_KEY, "").strip()


def _normalize_folder_id(folder_id: str) -> str:
    folder_id = (folder_id or "").strip()
    if "/folders/" in folder_id:
        folder_id = folder_id.split("/folders/")[1].split("?")[0].split("/")[0]
    return folder_id


def save_folder_id(folder_id: str) -> bool:
    return set_setting(FOLDER_KEY, _normalize_folder_id(folder_id))


def list_forms(*, category: str | None = None) -> pd.DataFrame:
    df = read_data(SHEET)
    if df is None or df.empty:
        return pd.DataFrame(
            columns=[
                "id",
                "title",
                "category",
                "filename",
                "mime",
                "drive_file_id",
                "size_bytes",
                "uploaded_by",
                "uploaded_at",
                "note",
            ]
        )
    out = df.copy()
    if category and category != "全部":
        out = out[out["category"].astype(str).str.strip() == category]
    if "uploaded_at" in out.columns:
        out = out.sort_values(by="uploaded_at", ascending=False, kind="mergesort")
    return out.reset_index(drop=True)


def _guess_mime(filename: str) -> str:
    mime, _ = mimetypes.guess_type(filename)
    return mime or "application/octet-stream"


def upload_form(
    *,
    title: str,
    category: str,
    filename: str,
    data: bytes,
    uploaded_by: str,
    note: str = "",
    mime: str | None = None,
) -> dict[str, Any]:
    """Upload bytes to Drive and INSERT metadata row. Returns {ok, error?, id?}."""
    title = str(title or "").strip()
    filename = str(filename or "").strip()
    category = str(category or "其他").strip() or "其他"
    note = str(note or "").strip()
    if not title or not filename or not data:
        return {"ok": False, "error": "標題同檔案必填"}

    from pathlib import Path

    ext = Path(filename).suffix.lower()
    if ext and ext not in ALLOWED_EXT:
        return {"ok": False, "error": f"唔支援 {ext} 檔案類型"}

    folder_id = get_folder_id()
    if not folder_id:
        return {"ok": False, "error": "未設定常用表格 Drive 資料夾（Leader 請先貼 Folder ID）"}

    service = get_drive_service()
    if not service:
        return {"ok": False, "error": "Drive 未連接（檢查 service account）"}

    mime = mime or _guess_mime(filename)
    meta = {"name": filename, "parents": [folder_id]}
    media = MediaIoBaseUpload(io.BytesIO(data), mimetype=mime, resumable=True)
    try:
        created = (
            service.files()
            .create(
                body=meta,
                media_body=media,
                fields="id,name,size,mimeType",
                supportsAllDrives=True,
            )
            .execute()
        )
    except Exception as e:
        return {"ok": False, "error": f"Drive 上傳失敗：{e}"}

    drive_id = str(created.get("id") or "")
    if not drive_id:
        return {"ok": False, "error": "Drive 上傳成功但無 file id"}

    now = str(datetime.datetime.now())
    size_bytes = int(created.get("size") or len(data) or 0)
    row = {
        "title": title,
        "category": category,
        "filename": filename,
        "mime": str(created.get("mimeType") or mime),
        "drive_file_id": drive_id,
        "size_bytes": size_bytes,
        "uploaded_by": str(uploaded_by or "").strip(),
        "uploaded_at": now,
        "note": note,
    }
    ok = bool(run_query_gs("INSERT", SHEET, row))
    if not ok:
        # Best-effort cleanup of orphan Drive file
        try:
            service.files().delete(fileId=drive_id, supportsAllDrives=True).execute()
        except Exception:
            pass
        return {"ok": False, "error": "已上傳 Drive，但寫入清單失敗"}
    return {"ok": True, "drive_file_id": drive_id, "row": row}


def download_form_bytes(drive_file_id: str) -> bytes:
    return download_file(drive_file_id)


def delete_form(row_id, drive_file_id: str | None = None) -> dict[str, Any]:
    if row_id is None or str(row_id).strip() == "":
        return {"ok": False, "error": "缺少項目 id"}

    if drive_file_id:
        service = get_drive_service()
        if service:
            try:
                service.files().update(
                    fileId=str(drive_file_id),
                    body={"trashed": True},
                    supportsAllDrives=True,
                ).execute()
            except Exception as e:
                # Still remove from list if Drive trash fails (e.g. already gone)
                st.session_state["_common_forms_drive_warn"] = str(e)[:200]

    ok = bool(run_query_gs("DELETE", SHEET, row_id=row_id))
    if not ok:
        return {"ok": False, "error": "刪除清單失敗"}
    return {"ok": True}


def format_size(n) -> str:
    try:
        n = int(float(n or 0))
    except Exception:
        return "—"
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / (1024 * 1024):.1f} MB"


def setup_hint() -> str:
    email = service_account_email() or "（service account email）"
    return (
        "一次性設定：\n"
        "1. Google Drive 開一個資料夾，例如「TIM TEAM 常用表格」\n"
        f"2. 將資料夾分享俾 **{email}**（編輯者）\n"
        "3. 複製資料夾連結或 Folder ID，貼喺下面儲存"
    )
