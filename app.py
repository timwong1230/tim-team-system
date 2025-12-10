import streamlit as st
import pandas as pd
import sqlite3
import datetime
import base64

# Page Config
st.set_page_config(page_title="TIM TEAM 2026", page_icon="🦁", layout="wide")
DB_FILE = 'tim_team.db'

# --- DB Functions ---
def run_query(query, params=(), fetch=False):
    try:
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            c.execute(query, params)
            if fetch: return c.fetchall()
            conn.commit()
    except: return []

def init_db():
    run_query("""CREATE TABLE IF NOT EXISTS users 
                 (username TEXT PRIMARY KEY, password TEXT, role TEXT, team TEXT, recruit INTEGER, avatar TEXT)""")
    run_query("""CREATE TABLE IF NOT EXISTS monthly_fyc 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, month TEXT, amount INTEGER)""")
    run_query("""CREATE TABLE IF NOT EXISTS activities 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, date TEXT, type TEXT, points INTEGER, note TEXT)""")
    
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

# --- Actions ---
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

# --- New Admin Functions ---
def get_all_activities():
    with sqlite3.connect(DB_FILE) as conn:
        return pd.read_sql_query("SELECT id, username, date, type, points, note FROM activities ORDER BY date DESC", conn)

def delete_activity(act_id):
    run_query("DELETE FROM activities WHERE id=?", (act_id,))

def update_activity(act_id, date, act_type, note):
    pts = 1
    if "Insurance" in act_type: pts = 2
    elif "Closing" in act_type: pts = 5
    run_query("UPDATE activities SET date=?, type=?, points=?, note=? WHERE id=?", (date, act_type, pts, note, act_id))

def get_activity_by_id(act_id):
    return run_query("SELECT * FROM activities WHERE id=?", (act_id,), fetch=True)

# --- Data Fetching ---
def get_leaderboard_data(selected_month=None):
    with sqlite3.connect(DB_FILE) as conn:
        df_users = pd.read_sql_query("SELECT username, team, recruit, avatar FROM users WHERE role='Member'", conn)
        if selected_month == "全年總計":
            sql_fyc = "SELECT username, SUM(amount) as fyc FROM monthly_fyc GROUP BY username"
        else:
            sql_fyc = f"SELECT username, amount as fyc FROM monthly_fyc WHERE month='{selected_month}'"
        df_fyc = pd.read_sql_query(sql_fyc, conn)
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

# --- UI State ---
if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False

# --- Login View ---
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

# --- Main App ---
else:
    st.sidebar.image(st.session_state.get('avatar', ''), width=100)
    st.sidebar.title(st.session_state['user'])
    st.sidebar.divider()
    opts = ["📊 全年 Dashboard", "📅 每月龍虎榜", "🤝 招募龍虎榜", "📝 活動打卡", "👤 設定"]
    menu = st.sidebar.radio("Menu", opts)
    st.sidebar.divider()
    if st.sidebar.button("Logout"):
        st.session_state['logged_in'] = False
        st.rerun()

    # 1. Dashboard
    if menu == "📊 全年 Dashboard":
        st.title("📊 2026 全年總覽")
        df = get_leaderboard_data("全年總計")
        c1, c2, c3 = st.columns(3)
        c1.metric("💰 全年總 FYC", f"${df['fyc'].sum():,}")
        c2.metric("🎯 總活動分", int(df['Total_Score'].sum()))
        c3.metric("🤝 總 Recruit", int(df['recruit'].sum()))
        
        cfg = {"avatar": st.column_config.ImageColumn("頭像"), "fyc": st.column_config.ProgressColumn("MDRT", format="$%d", max_value=800000)}
        st.dataframe(df[['avatar', 'username', 'fyc']].sort_values(by='fyc', ascending=False), column_config=cfg, use_container_width=True)

        # Admin Panel
        if st.session_state['role'] == 'Leader':
            st.divider()
            st.subheader("⚙️ Admin 管理台")
            
            tab1, tab2, tab3 = st.tabs(["💰 入 FYC", "🤝 入 Recruitment", "📝 管理活動紀錄 (Edit/Delete)"])
            
            with tab1:
                with st.form("admin_fyc"):
                    tgt = st.selectbox("同事", df['username'].tolist(), key="u1")
                    mth = st.selectbox("月份", ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-06", "2026-07", "2026-08", "2026-09", "2026-10", "2026-11", "2026-12"])
                    amt = st.number_input("FYC ($)", step=1000)
                    if st.form_submit_button("更新 FYC"):
                        update_monthly_fyc(tgt, mth, amt)
                        st.success("FYC Updated!")
                        st.rerun()
            
            with tab2:
                with st.form("admin_rec"):
                    tgt_r = st.selectbox("同事", df['username'].tolist(), key="u2")
                    rec = st.number_input("總人數", step=1, min_value=0)
                    if st.form_submit_button("更新 Recruit"):
                        update_recruit(tgt_r, rec)
                        st.success("Recruitment Updated!")
                        st.rerun()

            with tab3:
                st.write("以下係全隊活動紀錄，請記住 **ID** 進行修改或刪除。")
                all_acts = get_all_activities()
                st.dataframe(all_acts, use_container_width=True)
                
                c_edit, c_del = st.columns(2)
                
                with c_edit:
                    st.info("✏️ 修改紀錄")
                    edit_id = st.number_input("輸入要修改的 ID", min_value=0, step=1, key="eid")
                    if edit_id > 0:
                        curr = get_activity_by_id(edit_id)
                        if curr:
                            with st.form("edit_form"):
                                st.caption(f"正在修改: {curr[0][1]} 的紀錄 (原本: {curr[0][3]})")
                                new_d = st.date_input("新日期")
                                new_t = st.selectbox("新種類", ["Meeting (1分)", "Insurance Talk (2分)", "Closing (5分)"])
                                new_n = st.text_area("新備註", value=curr[0][5])
                                if st.form_submit_button("確認修改"):
                                    update_activity(edit_id, new_d, new_t, new_n)
                                    st.success("修改成功！")
                                    st.rerun()
                        else: st.warning("搵唔到此 ID")

                with c_del:
                    st.info("🗑️ 刪除紀錄")
                    del_id = st.number_input("輸入要刪除的 ID", min_value=0, step=1, key="did")
                    if st.button("確認刪除", type="primary"):
                        delete_activity(del_id)
                        st.success(f"ID {del_id} 已刪除！")
                        st.rerun()

    # 2. 每月龍虎榜
    elif menu == "📅 每月龍虎榜":
        st.title("📅 每月業績")
        m_opts = ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-06", "2026-07", "2026-08", "2026-09", "2026-10", "2026-11", "2026-12"]
        month = st.selectbox("月份", m_opts)
        df = get_leaderboard_data(month)
        if df['fyc'].sum() > 0:
            top = df.sort_values(by='fyc', ascending=False).iloc[0]
            if top['fyc'] > 0:
                st.balloons()
                st.success(f"👑 Top Sales: {top['username']} (${top['fyc']:,})")
        cfg = {"avatar": st.column_config.ImageColumn("頭像"), "fyc": st.column_config.NumberColumn("FYC", format="$%d")}
        st.dataframe(df[['avatar', 'username', 'fyc']].sort_values(by='fyc', ascending=False), column_config=cfg, use_container_width=True)

    # 3. 招募榜
    elif menu == "🤝 招募龍虎榜":
        st.title("🤝 招募龍虎榜")
        df = get_leaderboard_data("全年總計")
        cfg = {"avatar": st.column_config.ImageColumn("頭像"), "recruit": st.column_config.NumberColumn("Recruit", format="%d")}
        st.dataframe(df[['avatar', 'username', 'recruit']].sort_values(by='recruit', ascending=False), column_config=cfg, use_container_width=True)

    # 4. 打卡
    elif menu == "📝 活動打卡":
        st.header("📝 打卡")
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
            hist = get_user_activities(st.session_state['user'])
            st.dataframe(hist, use_container_width=True, hide_index=True)

    # 5. 設定
    elif menu == "👤 設定":
        st.title("設定")
        f = st.file_uploader("Upload Image", type=['jpg', 'png'])
        if f and st.button("更換"):
            code = process_image_upload(f)
            if code:
                update_avatar(st.session_state['user'], code)
                st.session_state['avatar'] = code
                st.success("Success!")
                st.rerun()