import streamlit as st
import pandas as pd
import sqlite3
import datetime
import base64

# --- 1. Page Config (Google Style) ---
st.set_page_config(page_title="TIM TEAM Workspace", page_icon="🦁", layout="wide")
DB_FILE = 'tim_team.db'

# --- 2. CSS 美化 (注入靈魂) ---
st.markdown("""
<style>
    /* 模仿 Google Drive 背景色 */
    .stApp {background-color: #F8F9FA;}
    
    /* 調整 Sidebar 樣式 */
    [data-testid="stSidebar"] {background-color: #FFFFFF; border-right: 1px solid #E0E0E0;}
    
    /* 調整 Metric 卡片樣式 */
    div[data-testid="stMetric"] {
        background-color: #FFFFFF;
        border: 1px solid #E0E0E0;
        padding: 15px;
        border-radius: 12px;
        box-shadow: 0 2px 5px rgba(0,0,0,0.05);
    }
    
    /* 頭像圓形加陰影 */
    [data-testid="stSidebar"] img {
        border-radius: 50%;
        border: 2px solid #fff;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
</style>
""", unsafe_allow_html=True)

# --- 3. DB Functions ---
def run_query(query, params=(), fetch=False):
    try:
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            c.execute(query, params)
            if fetch: return c.fetchall()
            conn.commit()
    except: return []

def init_db():
    run_query("""CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT, role TEXT, team TEXT, recruit INTEGER, avatar TEXT)""")
    run_query("""CREATE TABLE IF NOT EXISTS monthly_fyc (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, month TEXT, amount INTEGER)""")
    run_query("""CREATE TABLE IF NOT EXISTS activities (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, date TEXT, type TEXT, points INTEGER, note TEXT)""")
    
    if not run_query("SELECT * FROM users", fetch=True):
        users = [
            ('Admin', 'admin123', 'Leader', 'Boss'),
            ('Tim', '1234', 'Member', 'Tim Team'),
            ('Oscar', '1234', 'Member', 'Tim Team'),
            ('Catherine', '1234', 'Member', 'Tim Team'),
            ('Maggie', '1234', 'Member', 'Tim Team'),
            ('Wilson', '1234', 'Member', 'Tim Team')
        ]
        for u in users:
            base = "https://ui-avatars.com/api/?name="
            url = f"{base}{u[0]}&background=random&color=fff"
            run_query("INSERT INTO users VALUES (?,?,?,?,?,?)", (u[0], u[1], u[2], u[3], 0, url))

init_db()

# --- 4. Logic Functions ---
def login_user(u, p): return run_query('SELECT * FROM users WHERE username =? AND password = ?', (u, p), fetch=True)
def update_avatar(u, i): run_query("UPDATE users SET avatar = ? WHERE username = ?", (i, u))
def add_activity(u, d, t, n):
    pts = 1
    if "Insurance" in t: pts = 2
    elif "Closing" in t: pts = 5
    run_query("INSERT INTO activities (username, date, type, points, note) VALUES (?, ?,