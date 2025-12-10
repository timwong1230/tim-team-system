import streamlit as st
import pandas as pd
import sqlite3
import datetime
import base64

st.set_page_config(page_title="TIM TEAM 2026", page_icon="🦁", layout="wide")
DB_FILE = 'tim_team.db'

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
            url = f"{base}{u[0]}&background=random"
            run_query("INSERT INTO users VALUES (?,?,?,?,?,?)", (u[0], u[1], u[2], u[3], 0, url))

init_db()

def login_user(username, password):
    return run_query('SELECT * FROM users WHERE username =? AND password = ?', (username, password), fetch=True)

def update_avatar(username, img):
    run_query("UPDATE users SET avatar = ? WHERE username = ?", (img, username))

def add_activity(username, date, act_type, note):
    pts = 1
    if "Insurance" in act_type: pts = 2
    elif "Closing" in act_type: pts = 5
    run_query("INSERT INTO activities (username, date, type, points, note) VALUES (?, ?, ?, ?, ?)", (username, date, act_type, pts, note))

def update_monthly_fyc(username, month, amount):
    exist = run_query("SELECT id FROM monthly_fyc WHERE username=? AND month=?", (username, month), fetch=True)
    if exist: run_query("UPDATE monthly_fyc SET amount=? WHERE id=?", (amount, exist[0][0]))
    else: run_query("INSERT INTO monthly_fyc (username, month, amount) VALUES (?,?,?)", (username, month, amount))

def update_recruit(username, amount):
    run_query("UPDATE users SET recruit=? WHERE username=?", (amount, username))

def get_leaderboard_data(selected_month=None):
    with sqlite3.connect(DB_FILE) as conn:
        df_users = pd.read_sql_query("SELECT username, team, recruit, avatar FROM users WHERE role='Member'", conn)
        if selected_month == "全年總計":
            df_fyc = pd.read_sql_query("SELECT username, SUM(amount) as fyc FROM monthly_fyc GROUP BY username", conn)
        else:
            df_fyc = pd.read_sql_query(f"SELECT username, amount as fyc FROM monthly_fyc WHERE month='{selected_month}'", conn)
        df_act = pd.read_sql_query("SELECT username, SUM(points) as Total_Score FROM activities GROUP BY username", conn)
    
    df = pd.merge(df_users, df_fyc, on='username', how='left').fillna(0)
    df = pd.merge(df, df_act, on='username', how='left').fillna(0)
    return df

def get_user_activities(username):
    with sqlite3.connect(DB_FILE) as conn:
        return pd.read_sql_query(f"SELECT date, type, points, note FROM activities WHERE username='{username}' ORDER BY date DESC", conn)

def process_image_upload(file):
    if file:
        try: return f"data:image/png;base64,{base64.b64encode(file.getvalue()).decode()}"
        except: return None
    return None

if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False

if not st.session_state['logged_in']:
    st.sidebar.title("🦁 TIM TEAM")
    u = st.sidebar.text_input("用戶名")
    p = st.sidebar.text_input("密碼", type="password")
    if st.sidebar.button("Login"):
        data = login_user(u, p)
        if data:
            st.session_state['logged_in'] = True
            st.session_state['user'] = data[0][0]
            st.session_state['role'] = data[0][2]
            st.session_state['avatar'] = data[0][5]
            st.rerun()
        else: st.sidebar.error("Error")
else:
    st.sidebar.image(st.session_state.get('avatar', ''), width=100)
    st.sidebar.title(st.session_state['user'])
    st.sidebar.divider()
    menu = st.sidebar.radio("Menu", ["📊 全年 Dashboard", "📅 每月龍虎榜", "🤝 招募龍虎榜", "📝 活動打卡", "👤 設定"])
    st.sidebar.divider()
    if st.sidebar.button("