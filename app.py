import streamlit as st
import pandas as pd
import sqlite3
import datetime
import base64

st.set_page_config(page_title="TIM TEAM 2026", page_icon="🦁", layout="wide")
DB_FILE = 'tim_team.db'

# --- 1. 數據庫核心 ---
def run_query(query, params=(), fetch=False):
    try:
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            c.execute(query, params)
            if fetch: return c.fetchall()
            conn.commit()
    except: return []

def init_db():
    # Users 表
    run_query("""CREATE TABLE IF NOT EXISTS users
                 (username TEXT PRIMARY KEY, password TEXT, role TEXT, team TEXT, recruit INTEGER, avatar TEXT)""")
    # Monthly FYC 表
    run_query("""CREATE TABLE IF NOT EXISTS monthly_fyc
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, month TEXT, amount INTEGER)""")
    # 活動表
    run_query("""CREATE TABLE IF NOT EXISTS activities
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, date TEXT, type TEXT, points INTEGER, note TEXT)""")
    
    if not run_query("SELECT * FROM users", fetch=True):
        users = [('Admin', 'admin123', 'Leader', 'Boss'), ('Tim', '1234', 'Member', 'Tim Team'),
                 ('Oscar', '1234', 'Member', 'Tim Team'), ('Catherine', '1234', 'Member', 'Tim Team'),
                 ('Maggie', '1234', 'Member', 'Tim Team'), ('Wilson', '1234', 'Member', 'Tim Team')]
        for u in users:
            url = f"https://ui-avatars.com/api/?name={u[0]}&background=random