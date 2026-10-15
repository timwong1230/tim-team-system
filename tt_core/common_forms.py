"""常用表格：簽單 / 行政文件。

Service account 冇 My Drive 儲存配額，唔可以「代你」將檔案寫入普通個人資料夾。
可靠做法：
1. Leader 自己用 Google Drive 將檔案放入已分享資料夾，再喺 app「同步資料夾」
2. 或者用 Google Workspace「共用雲端硬碟」(Shared Drive)，先可以喺 app 內直接上傳
"""

from __future__ import annotations

import datetime
import io
import mimetypes
from pathlib import Path
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

_QUOTA_HINT = (
    "Google Service Account 冇個人 Drive 儲存空間，"
    "唔可以上傳去普通「我的雲端硬碟」資料夾。\n\n"
    "**建議做法（最穩）：**\n"
    "1. 用你自己嘅 Google 帳號，將 PDF／文件放入呢個資料夾\n"
    "2. 返嚟 app 撳「同步 Drive 資料夾」\n\n"
    "**進階：** 若公司有 Google Workspace，開「共用雲端硬碟」"
    "並將 service account 加為內容管理員，就可以喺 app 內直接上傳。"
)


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


def _is_allowed_name(filename: str) -> bool:
    ext = Path(filename or "").suffix.lower()
    return (not ext) or ext in ALLOWED_EXT


def _quota_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return (
        "storagequotaexceeded" in msg
        or "do not have storage quota" in msg
        or "service accounts do not have storage" in msg
    )


def list_drive_folder_files(folder_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    """List files already in the shared folder (SA can read; no upload quota needed)."""
    service = get_drive_service()
    folder_id = (folder_id or get_folder_id()).strip()
    if not service or not folder_id:
        return []

    q = f"'{folder_id}' in parents and trashed=false and mimeType != 'application/vnd.google-apps.folder'"
    try:
        resp = (
            service.files()
            .list(
                q=q,
                spaces="drive",
                fields="files(id,name,mimeType,modifiedTime,size,owners)",
                orderBy="modifiedTime desc",
                pageSize=limit,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            )
            .execute()
        )
        files = resp.get("files", []) or []
        return [f for f in files if _is_allowed_name(str(f.get("name") or ""))]
    except Exception as e:
        st.session_state["_common_forms_drive_warn"] = str(e)[:240]
        return []


def sync_folder_into_catalog(
    *,
    category: str = "其他",
    uploaded_by: str = "",
    note: str = "",
) -> dict[str, Any]:
    """
    Index files that Leaders already put into the Drive folder.
    Works with ordinary My Drive folders shared with the service account.
    """
    folder_id = get_folder_id()
    if not folder_id:
        return {"ok": False, "error": "未設定常用表格 Drive 資料夾", "added": 0, "skipped": 0}

    files = list_drive_folder_files(folder_id)
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

    existing = list_forms()
    known_ids = set()
    if not existing.empty and "drive_file_id" in existing.columns:
        known_ids = {str(x).strip() for x in existing["drive_file_id"].tolist() if str(x).strip()}

    category = str(category or "其他").strip() or "其他"
    note = str(note or "").strip()
    added = 0
    skipped = 0
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
        row = {
            "title": title,
            "category": category,
            "filename": name,
            "mime": str(f.get("mimeType") or _guess_mime(name)),
            "drive_file_id": drive_id,
            "size_bytes": int(f.get("size") or 0),
            "uploaded_by": str(uploaded_by or "").strip(),
            "uploaded_at": str(f.get("modifiedTime") or now)[:19].replace("T", " "),
            "note": note,
        }
        if run_query_gs("INSERT", SHEET, row):
            added += 1
            known_ids.add(drive_id)
        else:
            return {
                "ok": False,
                "error": f"寫入清單失敗（已新增 {added} 份）",
                "added": added,
                "skipped": skipped,
            }

    return {
        "ok": True,
        "added": added,
        "skipped": skipped,
        "message": f"同步完成：新增 {added} 份，略過已有 {skipped} 份",
    }


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
    """Upload bytes to Drive (needs Shared Drive). Prefer sync_folder_into_catalog for My Drive."""
    title = str(title or "").strip()
    filename = str(filename or "").strip()
    category = str(category or "其他").strip() or "其他"
    note = str(note or "").strip()
    if not title or not filename or not data:
        return {"ok": False, "error": "標題同檔案必填"}

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
        if _quota_error(e):
            return {"ok": False, "error": _QUOTA_HINT, "quota": True}
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
        try:
            service.files().update(
                fileId=drive_id,
                body={"trashed": True},
                supportsAllDrives=True,
            ).execute()
        except Exception:
            pass
        return {"ok": False, "error": "已上傳 Drive，但寫入清單失敗"}
    return {"ok": True, "drive_file_id": drive_id, "row": row}


def download_form_bytes(drive_file_id: str) -> bytes:
    return download_file(drive_file_id)


def ensure_view_link(drive_file_id: str, *, share_anyone: bool = False) -> str:
    """
    Build a Drive view URL for opening in a new tab (iPhone-safe).

    By default this does NOT call the Drive API during page render.
    Set share_anyone=True only from an explicit Leader action.
    """
    file_id = str(drive_file_id or "").strip()
    if not file_id:
        return ""
    if share_anyone:
        service = get_drive_service()
        if service:
            try:
                service.permissions().create(
                    fileId=file_id,
                    body={"type": "anyone", "role": "reader"},
                    supportsAllDrives=True,
                    fields="id",
                ).execute()
            except Exception:
                pass
    return f"https://drive.google.com/file/d/{file_id}/view?usp=sharing"


def delete_form(row_id, drive_file_id: str | None = None) -> dict[str, Any]:
    """Remove catalog row. Does not trash Drive file by default (Leader may still need the original)."""
    if row_id is None or str(row_id).strip() == "":
        return {"ok": False, "error": "缺少項目 id"}

    # Only remove from app list — keep the Drive original so sync can re-add if needed.
    # Optional trash kept behind session flag for advanced cleanup.
    if drive_file_id and st.session_state.get("_common_forms_trash_drive"):
        service = get_drive_service()
        if service:
            try:
                service.files().update(
                    fileId=str(drive_file_id),
                    body={"trashed": True},
                    supportsAllDrives=True,
                ).execute()
            except Exception as e:
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
        "1. 用你自己嘅 Google 帳號開資料夾，例如「TIM TEAM 常用表格」\n"
        f"2. 將資料夾分享俾 **{email}**（檢視者即可；要 app 內上傳先要編輯者 + 共用雲端硬碟）\n"
        "3. 複製資料夾連結或 Folder ID，貼喺下面儲存\n"
        "4. 之後用自己帳號將文件放入資料夾 → 返 app 撳「同步 Drive 資料夾」"
    )
