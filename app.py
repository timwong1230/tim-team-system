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
    # Users 表 (移除了 fyc 欄位，改為動態計算)
    run_query("""CREATE TABLE IF NOT EXISTS users
                 (username TEXT PRIMARY KEY, password TEXT, role TEXT, team TEXT, recruit INTEGER, avatar TEXT)""")
    
    # 新增: Monthly FYC 表 (專門記每個月既數)
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
            url = f"https://ui-avatars.com/api/?name={u[0]}&background=random"
            run_query("INSERT INTO users VALUES (?,?,?,?,?,?)", (u[0], u[1], u[2], u[3], 0, url))

init_db()

# --- 2. 核心功能 ---
def login_user(username, password):
    return run_query('SELECT * FROM users WHERE username =? AND password = ?', (username, password), fetch=True)

def update_avatar(username, image_data):
    run_query("UPDATE users SET avatar = ? WHERE username = ?", (image_data, username))

def add_activity(username, date, act_type, note):
    pts = 1
    if "Insurance" in act_type: pts = 2
    elif "Closing" in act_type: pts = 5
    run_query("INSERT INTO activities (username, date, type, points, note) VALUES (?, ?, ?, ?, ?)", (username, date, act_type, pts, note))

# --- Admin 入數功能 (分月份) ---
def update_monthly_fyc(username, month, amount):
    # 檢查該月是否已有紀錄
    exist = run_query("SELECT id FROM monthly_fyc WHERE username=? AND month=?", (username, month), fetch=True)
    if exist:
        run_query("UPDATE monthly_fyc SET amount=? WHERE id=?", (amount, exist[0][0]))
    else:
        run_query("INSERT INTO monthly_fyc (username, month, amount) VALUES (?,?,?)", (username, month, amount))

def update_recruit(username, amount):
    run_query("UPDATE users SET recruit=? WHERE username=?", (amount, username))

# --- 獲取數據 ---
def get_leaderboard_data(selected_month=None):
    with sqlite3.connect(DB_FILE) as conn:
        # 1. 獲取用戶基本資料
        df_users = pd.read_sql_query("SELECT username, team, recruit, avatar FROM users WHERE role='Member'", conn)
        
        # 2. 計算 FYC
        if selected_month == "全年總計":
            # 全年: 加總所有月份
            df_fyc = pd.read_sql_query("SELECT username, SUM(amount) as fyc FROM monthly_fyc GROUP BY username", conn)
        else:
            # 單月: 只取該月
            df_fyc = pd.read_sql_query(f"SELECT username, amount as fyc FROM monthly_fyc WHERE month='{selected_month}'", conn)
            
        # 3. 計算活動分
        df_act = pd.read_sql_query("SELECT username, SUM(points) as Total_Score FROM activities GROUP BY username", conn)

    # 合併數據
    df = pd.merge(df_users, df_fyc, on='username', how='left').fillna(0)
    df = pd.merge(df, df_act, on='username', how='left').fillna(0)
    return df

def get_user_activities(username):
    with sqlite3.connect(DB_FILE) as conn:
        return pd.read_sql_query(f"SELECT date, type, points, note FROM activities WHERE username='{username}' ORDER BY date DESC", conn)

def process_image_upload(file):
    if file:
        try:
            return f"data:image/png;base64,{base64.b64encode(file.getvalue()).decode()}"
        except: return None
    return None

# --- 3. UI 邏輯 ---
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
    # Sidebar
    st.sidebar.image(st.session_state.get('avatar', ''), width=100)
    st.sidebar.title(st.session_state['user'])
    st.sidebar.divider()
    menu = st.sidebar.radio("Menu", ["📊 全年 Dashboard", "📅 每月龍虎榜", "📝 活動打卡", "👤 設定"])
    st.sidebar.divider()
    if st.sidebar.button("Logout"):
        st.session_state['logged_in'] = False
        st.rerun()

    # --- 頁面 1: 全年總覽 ---
    if menu == "📊 全年 Dashboard":
        st.title("📊 2026 全年總覽 (Yearly)")
        df = get_leaderboard_data("全年總計") # 自動加總所有月份
        
        c1, c2, c3 = st.columns(3)
        c1.metric("💰 全年總 FYC", f"${df['fyc'].sum():,}")
        c2.metric("🎯 總活動分", int(df['Total_Score'].sum()))
        c3.metric("🤝 總 Recruit", int(df['recruit'].sum()))
        
        st.subheader("🏆 全年 MDRT 進度")
        st.dataframe(
            df[['avatar', 'username', 'fyc']].sort_values(by='fyc', ascending=False),
            column_config={
                "avatar": st.column_config.ImageColumn("頭像"),
                "fyc": st.column_config.ProgressColumn("MDRT ($800k)", format="$%d", min_value=0, max_value=800000)
            }, use_container_width=True
        )

        # Admin 入數區
        if st.session_state['role'] == 'Leader':
            st.divider()
            st.subheader("⚙️ Admin 入數 (分月輸入)")
            with st.form("admin_input"):
                c1, c2 = st.columns(2)
                target = c1.selectbox("同事", df['username'].tolist())
                month = c2.selectbox("月份", ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-06", 
                                            "2026-07", "2026-08", "2026-09", "2026-10", "2026-11", "2026-12"])
                
                c3, c4 = st.columns(2)
                amount = c3.number_input(f"該月 FYC ($)", step=1000)
                rec = c4.number_input("總 Recruit 人數", step=1)
                
                if st.form_submit_button("更新數據"):
                    update_monthly_fyc(target, month, amount)
                    update_recruit(target, rec)
                    st.success(f"已更新 {target} 在 {month} 的業績！")
                    st.rerun()

    # --- 頁面 2: 每月龍虎榜 ---
    elif menu == "📅 每月龍虎榜":
        st.title("📅 每月業績之星")
        
        # 選擇月份 Filter
        selected_month = st.selectbox("選擇月份查看", ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-06", 
                                                   "2026-07", "2026-08", "2026-09", "2026-10", "2026-11", "2026-12"])
        
        df = get_leaderboard_data(selected_month)
        
        # Top Sales 展示
        if df['fyc'].sum() > 0:
            top = df.sort_values(by='fyc', ascending=False).iloc[0]
            if top['fyc'] > 0:
                st.balloons()
                st.markdown(f"""
                <div style="background-color:#FFD700; padding:15px; border-radius:10px; text-align:center; color:black; margin-bottom:20px;">
                    <h2>👑 {selected_month} Top Sales: {top['username']}</h2>
                    <h1>${top['fyc']:,}</h1>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.info(f"{selected_month} 暫無數據")
        else:
            st.info(f"{selected_month} 暫無數據，請 Admin 入數。")

        st.dataframe(
            df[['avatar', 'username', 'fyc']].sort_values(by='fyc', ascending=False),
            column_config={
                "avatar": st.column_config.ImageColumn("頭像"),
                "fyc": st.column_config.NumberColumn(f"{selected_month} 業績", format="$%d")
            }, use_container_width=True
        )

    # --- 頁面 3: 活動打卡 ---
    elif menu == "📝 活動打卡":
        st.header("📝 活動打卡")
        c1, c2 = st.columns([1, 2])
        with c1:
            with st.form("act"):
                d = st.date_input("日期")
                t = st.selectbox("種類", ["Meeting (1分)", "Insurance Talk (2分)", "Closing (5分)"])
                n = st.text_area("備註")
                if st.form_submit_button("提交"):
                    add_activity(st.session_state['user'], d, t, n)
                    st.success("Saved!")
        with c2:
            st.dataframe(get_user_activities(st.session_state['user']), use_container_width=True, hide_index=True)

    # --- 頁面 4: 設定 ---
    elif menu == "👤 設定":
        st.title("設定")
        f = st.file_uploader("Upload Image", type=['jpg', 'png'])
        if f and st.button("更換"):
            code = process_image_upload(f)
            if code:
                update_avatar(st.session_state['user'], code)
                st.session_state['avatar'] = code
                st.success("成功!")
                st.rerun()