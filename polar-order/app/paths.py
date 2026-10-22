"""Filesystem roots — allow cloud hosts to mount a persistent disk."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Menu seed (read-only, baked into image) stays under the app tree.
MENU_PATH = ROOT / "data" / "menu.json"

# Runtime data (SQLite + receipts) — set POLAR_DATA_DIR=/data on cloud.
_DATA = os.getenv("POLAR_DATA_DIR", "").strip()
DATA_DIR = Path(_DATA).expanduser().resolve() if _DATA else (ROOT / "data")
DB_PATH = DATA_DIR / "polar_order.db"
RECEIPT_DIR = DATA_DIR / "receipts"
