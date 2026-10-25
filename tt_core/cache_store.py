"""Disk + memory cache so the app stays usable when Google Sheets is slow/down."""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

import pandas as pd

CACHE_DIR = Path(os.environ.get("TIM_TEAM_CACHE_DIR", "/tmp/tim_team_cache"))
META_PATH = CACHE_DIR / "_meta.json"
_LOCK = threading.Lock()

# In-process mirror (fast path within same worker)
_MEMORY: dict[str, dict[str, Any]] = {}


def _ensure_dir() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _sheet_path(sheet_name: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in sheet_name)
    return CACHE_DIR / f"{safe}.parquet"


def _read_meta() -> dict:
    _ensure_dir()
    if not META_PATH.exists():
        return {}
    try:
        return json.loads(META_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_meta(meta: dict) -> None:
    _ensure_dir()
    META_PATH.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def save_sheet(sheet_name: str, df: pd.DataFrame, *, source: str = "sheets") -> None:
    """Persist a sheet snapshot to memory + disk."""
    _ensure_dir()
    # Normalize for parquet (all object-friendly)
    out = df.copy()
    for col in out.columns:
        out[col] = out[col].astype(str)
    payload = {
        "df": out,
        "saved_at": time.time(),
        "source": source,
        "rows": int(len(out)),
    }
    with _LOCK:
        _MEMORY[sheet_name] = payload
        try:
            out.to_parquet(_sheet_path(sheet_name), index=False)
        except Exception:
            # Fallback if parquet engine missing
            out.to_pickle(_sheet_path(sheet_name).with_suffix(".pkl"))
        meta = _read_meta()
        meta[sheet_name] = {
            "saved_at": payload["saved_at"],
            "source": source,
            "rows": payload["rows"],
        }
        meta["_last_ok"] = payload["saved_at"]
        _write_meta(meta)


def load_sheet(sheet_name: str) -> tuple[pd.DataFrame | None, dict]:
    """Return (df, meta). df is None if no cache."""
    with _LOCK:
        mem = _MEMORY.get(sheet_name)
        if mem is not None:
            return mem["df"].copy(), {
                "saved_at": mem["saved_at"],
                "source": mem["source"],
                "rows": mem["rows"],
                "layer": "memory",
            }

    path = _sheet_path(sheet_name)
    pkl = path.with_suffix(".pkl")
    try:
        if path.exists():
            df = pd.read_parquet(path)
        elif pkl.exists():
            df = pd.read_pickle(pkl)
        else:
            return None, {}
        meta = _read_meta().get(sheet_name, {})
        meta = {**meta, "layer": "disk"}
        with _LOCK:
            _MEMORY[sheet_name] = {
                "df": df,
                "saved_at": meta.get("saved_at", time.time()),
                "source": meta.get("source", "disk"),
                "rows": len(df),
            }
        return df.copy(), meta
    except Exception:
        return None, {}


def touch_status(ok: bool, detail: str = "") -> None:
    with _LOCK:
        meta = _read_meta()
        meta["_status"] = {
            "ok": ok,
            "detail": detail,
            "at": time.time(),
        }
        if ok:
            meta["_last_ok"] = time.time()
        else:
            meta["_last_error"] = {"at": time.time(), "detail": detail}
        _write_meta(meta)


def get_status() -> dict:
    meta = _read_meta()
    status = meta.get("_status", {})
    last_ok = meta.get("_last_ok")
    age = (time.time() - last_ok) if last_ok else None
    return {
        "ok": bool(status.get("ok", last_ok is not None)),
        "detail": status.get("detail", ""),
        "last_ok": last_ok,
        "age_sec": age,
        "sheets": {k: v for k, v in meta.items() if not k.startswith("_")},
    }


def invalidate_memory(sheet_name: str | None = None) -> None:
    with _LOCK:
        if sheet_name is None:
            _MEMORY.clear()
        else:
            _MEMORY.pop(sheet_name, None)


def normalize_id(value: Any) -> str:
    """Canonical row id: ``1``, ``1.0``, ``\"1.0\"`` → ``\"1\"`` so cache/Sheets match."""
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "nat"}:
        return ""
    try:
        num = float(text)
        if num.is_integer():
            return str(int(num))
    except (TypeError, ValueError):
        pass
    return text


def _id_mask(series: pd.Series, row_id: Any) -> pd.Series:
    target = normalize_id(row_id)
    if not target:
        return pd.Series([False] * len(series), index=series.index)
    return series.map(normalize_id) == target


def upsert_row_cache(sheet_name: str, row: dict, id_field: str = "id") -> pd.DataFrame:
    """Optimistically merge a row into cached sheet (by id if present)."""
    df, _ = load_sheet(sheet_name)
    if df is None:
        df = pd.DataFrame([row])
    else:
        row = {k: str(v) if v is not None else "" for k, v in row.items()}
        if id_field in row:
            row[id_field] = normalize_id(row[id_field]) or row[id_field]
        for col in row:
            if col not in df.columns:
                df[col] = ""
        if id_field in row and id_field in df.columns and normalize_id(row[id_field]):
            mask = _id_mask(df[id_field], row[id_field])
            if mask.any():
                for k, v in row.items():
                    df.loc[mask, k] = v
            else:
                df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
        else:
            df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    save_sheet(sheet_name, df, source="optimistic")
    return df


def delete_row_cache(sheet_name: str, row_id: Any, id_field: str = "id") -> None:
    df, _ = load_sheet(sheet_name)
    if df is None or id_field not in df.columns:
        return
    df = df[~_id_mask(df[id_field], row_id)].copy()
    save_sheet(sheet_name, df, source="optimistic")


def next_id(sheet_name: str) -> int:
    df, _ = load_sheet(sheet_name)
    if df is None or df.empty or "id" not in df.columns:
        return 1
    ids = pd.to_numeric(df["id"].map(normalize_id), errors="coerce").dropna()
    return int(ids.max()) + 1 if not ids.empty else 1
