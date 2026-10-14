"""Google Sheets data access layer."""

from __future__ import annotations

import json
import os
import time
from typing import Any

import gspread
import pandas as pd
import streamlit as st
from google.oauth2.service_account import Credentials
from gspread.exceptions import WorksheetNotFound

from lib.constants import SHEET_SCHEMAS

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


@st.cache_resource
def get_gs_client():
    try:
        if "service_account" in st.secrets:
            json_str = st.secrets["service_account"]["key_content"]
            key_dict = json.loads(json_str)
        elif "GSPREAD_KEY" in os.environ:
            key_dict = json.loads(os.environ["GSPREAD_KEY"])
        else:
            return None
        creds = Credentials.from_service_account_info(key_dict, scopes=SCOPES)
        return gspread.authorize(creds)
    except Exception:
        return None


def get_sheet(sheet_name: str):
    client = get_gs_client()
    if not client:
        return None
    try:
        sh = client.open("tim_team_db")
        try:
            return sh.worksheet(sheet_name)
        except WorksheetNotFound:
            cols = max(len(SHEET_SCHEMAS.get(sheet_name, [])), 11)
            return sh.add_worksheet(title=sheet_name, rows=1000, cols=cols)
    except Exception:
        return None


def clear_cache():
    st.cache_data.clear()


@st.cache_data(ttl=30)
def read_data(sheet_name: str) -> pd.DataFrame:
    ws = get_sheet(sheet_name)
    expected_cols = SHEET_SCHEMAS.get(sheet_name, [])

    for _ in range(3):
        if ws:
            try:
                data = ws.get_all_records()
                df = pd.DataFrame(data)
                for col in expected_cols:
                    if col not in df.columns:
                        df[col] = ""
                if expected_cols:
                    # Keep expected cols first, preserve any extra columns
                    ordered = expected_cols + [c for c in df.columns if c not in expected_cols]
                    df = df[ordered]
                if not df.empty:
                    st.session_state[f"backup_{sheet_name}"] = df
                return df
            except Exception:
                time.sleep(1)

    if f"backup_{sheet_name}" in st.session_state:
        return st.session_state[f"backup_{sheet_name}"]
    return pd.DataFrame(columns=expected_cols)


def ensure_headers(ws, sheet_name: str):
    headers = ws.row_values(1)
    if headers:
        return headers
    schema = SHEET_SCHEMAS.get(sheet_name, [])
    if schema:
        ws.append_row(schema)
    return schema


def run_query_gs(action: str, sheet_name: str, data_dict: dict | None = None, row_id=None):
    ws = get_sheet(sheet_name)
    if not ws:
        return False
    try:
        if action == "INSERT":
            if sheet_name in {
                "activities",
                "monthly_fyc",
                "story_ammo",
                "iris_sync_log",
            }:
                records = ws.get_all_records()
                new_id = 1
                if records:
                    ids = [int(r["id"]) for r in records if str(r.get("id", "")).isdigit()]
                    if ids:
                        new_id = max(ids) + 1
                data_dict = dict(data_dict or {})
                data_dict["id"] = new_id

            headers = ensure_headers(ws, sheet_name)
            row_to_add = [str((data_dict or {}).get(h, "")) for h in headers]
            ws.append_row(row_to_add)

        elif action == "UPDATE":
            cell = ws.find(str(row_id))
            if cell:
                headers = ws.row_values(1)
                for col, val in (data_dict or {}).items():
                    if col in headers:
                        ws.update_cell(cell.row, headers.index(col) + 1, val)

        elif action == "DELETE":
            cell = ws.find(str(row_id))
            if cell:
                ws.delete_rows(cell.row)

        clear_cache()
        return True
    except Exception as e:
        st.error(f"操作失敗: {e}")
        return False


def init_db_gs():
    try:
        ws = get_sheet("users")
        if ws:
            try:
                existing = ws.col_values(1)
            except Exception:
                existing = []
            if not existing:
                ws.append_row(SHEET_SCHEMAS["users"])
                existing = ["username"]
            defaults = [
                ("Admin", "admin123", "Leader"),
                ("Tim", "1234", "Member"),
                ("Oscar", "1234", "Member"),
            ]
            for u in defaults:
                if u[0] not in existing:
                    url = f"https://ui-avatars.com/api/?name={u[0]}&background=d4af37&color=fff&size=128"
                    ws.append_row([u[0], u[1], u[2], "Tim Team", 0, url, ""])
                    clear_cache()

        for sn in [
            "monthly_fyc",
            "activities",
            "story_ammo",
            "iris_agent_map",
            "iris_sync_log",
        ]:
            ws_tmp = get_sheet(sn)
            if ws_tmp:
                try:
                    if not ws_tmp.row_values(1):
                        ws_tmp.append_row(SHEET_SCHEMAS[sn])
                    else:
                        # Soft-migrate monthly_fyc headers if older schema
                        if sn == "monthly_fyc":
                            headers = ws_tmp.row_values(1)
                            for col in ["source", "updated_at"]:
                                if col not in headers:
                                    ws_tmp.update_cell(1, len(headers) + 1, col)
                                    headers.append(col)
                except Exception:
                    pass
    except Exception:
        pass


def update_user_field(username: str, field: str, value: Any) -> bool:
    ws = get_sheet("users")
    if not ws:
        return False
    cell = ws.find(username)
    if not cell:
        return False
    headers = ws.row_values(1)
    if field not in headers:
        return False
    ws.update_cell(cell.row, headers.index(field) + 1, value)
    clear_cache()
    return True
