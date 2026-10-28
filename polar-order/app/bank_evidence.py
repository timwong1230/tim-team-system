"""Bank transaction screenshot / PDF evidence uploads.

Saves files under BANK_EVIDENCE_DIR (persistent disk on Render) and optionally
mirrors them to a Google Drive folder. Metadata is appended to Bank_Evidence.
"""

from __future__ import annotations

import json
import mimetypes
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .paths import BANK_EVIDENCE_DIR
from .sheets_sync import (
    SheetsNotConfigured,
    append_bank_evidence,
    evidence_folder_id,
    sheets_configured,
)

HK = ZoneInfo("Asia/Hong_Kong")

ALLOWED_MIME = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
    "image/heic",
    "image/heif",
    "application/pdf",
}
MAX_BYTES = 12 * 1024 * 1024  # 12 MB per file
MAX_FILES = 20

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._\-]+")


def _safe_filename(name: str) -> str:
    base = Path(name or "evidence").name.strip() or "evidence"
    cleaned = _SAFE_NAME.sub("_", base).strip("._") or "evidence"
    return cleaned[:120]


def _guess_mime(filename: str, content_type: str | None) -> str:
    ct = (content_type or "").split(";")[0].strip().lower()
    if ct in ALLOWED_MIME or ct == "image/jpg":
        return "image/jpeg" if ct == "image/jpg" else ct
    guessed, _ = mimetypes.guess_type(filename)
    if guessed and guessed in ALLOWED_MIME:
        return guessed
    return ct or "application/octet-stream"


def _ensure_dir() -> Path:
    BANK_EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    return BANK_EVIDENCE_DIR


def _drive_session():
    """Authorized session for Drive REST (multipart upload)."""
    from google.auth.transport.requests import AuthorizedSession
    from google.oauth2.service_account import Credentials

    from .sheets_sync import _credentials_dict, _SCOPES

    key = _credentials_dict()
    if not key:
        raise SheetsNotConfigured("POLAR_GSPREAD_KEY missing")
    creds = Credentials.from_service_account_info(key, scopes=list(_SCOPES))
    return AuthorizedSession(creds)


def _upload_to_drive(
    *,
    data: bytes,
    filename: str,
    mime: str,
    folder_id: str,
) -> dict[str, str]:
    session = _drive_session()
    boundary = f"polar_{uuid.uuid4().hex}"
    meta = json.dumps(
        {"name": filename, "parents": [folder_id]},
        ensure_ascii=False,
    )
    body = (
        f"--{boundary}\r\n"
        "Content-Type: application/json; charset=UTF-8\r\n\r\n"
        f"{meta}\r\n"
        f"--{boundary}\r\n"
        f"Content-Type: {mime}\r\n\r\n"
    ).encode("utf-8") + data + f"\r\n--{boundary}--\r\n".encode("utf-8")

    url = (
        "https://www.googleapis.com/upload/drive/v3/files"
        "?uploadType=multipart&supportsAllDrives=true"
        "&fields=id,name,webViewLink,webContentLink"
    )
    resp = session.post(
        url,
        headers={"Content-Type": f'multipart/related; boundary="{boundary}"'},
        data=body,
        timeout=120,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"Drive upload failed ({resp.status_code}): {resp.text[:400]}")
    payload = resp.json()
    file_id = str(payload.get("id") or "")
    link = str(payload.get("webViewLink") or "")
    if file_id and not link:
        link = f"https://drive.google.com/file/d/{file_id}/view"
    # Anyone-with-link skipped — share folder with Tim / SA instead.
    return {
        "file_id": file_id,
        "drive_url": link,
        "name": str(payload.get("name") or filename),
    }


def save_and_register(
    files: list[dict[str, Any]],
    *,
    note: str = "",
    txn_date: str = "",
    amount_hint: str = "",
) -> dict[str, Any]:
    """Persist uploads locally, mirror to Drive when possible, log to sheet.

    Each item in ``files``: ``{filename, content, content_type}``.
    """
    if not files:
        raise ValueError("No files uploaded")
    if len(files) > MAX_FILES:
        raise ValueError(f"Too many files (max {MAX_FILES})")

    note = (note or "").strip()
    txn_date = (txn_date or "").strip()
    amount_hint = (amount_hint or "").strip()
    uploaded_at = datetime.now(HK).strftime("%Y-%m-%d %H:%M:%S")

    folder = evidence_folder_id()
    drive_ok = bool(folder and sheets_configured())
    drive_errors: list[str] = []

    _ensure_dir()
    rows: list[dict[str, Any]] = []
    saved: list[dict[str, Any]] = []

    for item in files:
        raw = item.get("content") or b""
        if not raw:
            continue
        if len(raw) > MAX_BYTES:
            raise ValueError(f"File too large (max {MAX_BYTES // (1024 * 1024)} MB): {item.get('filename')}")
        filename = _safe_filename(str(item.get("filename") or "evidence"))
        mime = _guess_mime(filename, item.get("content_type"))
        if mime not in ALLOWED_MIME:
            raise ValueError(f"Unsupported file type: {filename} ({mime})")

        evidence_id = uuid.uuid4().hex
        stored_name = f"{evidence_id}_{filename}"
        path = BANK_EVIDENCE_DIR / stored_name
        path.write_bytes(raw)

        drive_url = ""
        drive_file_id = ""
        if drive_ok and folder:
            try:
                drive_name = f"{txn_date + '_' if txn_date else ''}{uploaded_at.replace(':', '').replace(' ', '_')}_{filename}"
                info = _upload_to_drive(
                    data=raw,
                    filename=drive_name,
                    mime=mime,
                    folder_id=folder,
                )
                drive_url = info.get("drive_url") or ""
                drive_file_id = info.get("file_id") or ""
            except Exception as exc:  # noqa: BLE001 — local save still counts
                drive_errors.append(f"{filename}: {exc}")

        row = {
            "uploaded_at": uploaded_at,
            "txn_date": txn_date,
            "amount_hint": amount_hint,
            "note": note,
            "filename": filename,
            "evidence_id": evidence_id,
            "drive_url": drive_url,
            "file_id": drive_file_id,
        }
        rows.append(row)
        saved.append(
            {
                "evidence_id": evidence_id,
                "filename": filename,
                "drive_url": drive_url,
                "bytes": len(raw),
            }
        )

    if not rows:
        raise ValueError("No valid files uploaded")

    sheet_result: dict[str, Any] = {"ok": False, "added": 0}
    if sheets_configured():
        try:
            sheet_result = append_bank_evidence(rows)
        except SheetsNotConfigured:
            sheet_result = {"ok": False, "added": 0, "error": "sheets not configured"}
        except Exception as exc:  # noqa: BLE001
            sheet_result = {"ok": False, "added": 0, "error": str(exc)}

    return {
        "ok": True,
        "uploaded": len(saved),
        "files": saved,
        "sheet": sheet_result,
        "drive_folder_id": folder or "",
        "drive_errors": drive_errors,
        "uploaded_at": uploaded_at,
    }


def resolve_evidence_path(evidence_id: str) -> Path | None:
    eid = (evidence_id or "").strip()
    if not re.fullmatch(r"[0-9a-f]{32}", eid):
        return None
    _ensure_dir()
    matches = list(BANK_EVIDENCE_DIR.glob(f"{eid}_*"))
    if not matches:
        return None
    return matches[0]


def list_recent_evidence(limit: int = 20) -> list[dict[str, Any]]:
    _ensure_dir()
    files = sorted(
        BANK_EVIDENCE_DIR.glob("*"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    out: list[dict[str, Any]] = []
    for path in files:
        if not path.is_file():
            continue
        name = path.name
        eid, _, rest = name.partition("_")
        if len(eid) != 32 or not rest:
            continue
        mime, _ = mimetypes.guess_type(rest)
        out.append(
            {
                "evidence_id": eid,
                "filename": rest,
                "mime": mime or "application/octet-stream",
                "bytes": path.stat().st_size,
                "mtime": datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
                .astimezone(HK)
                .strftime("%Y-%m-%d %H:%M"),
            }
        )
        if len(out) >= limit:
            break
    return out
