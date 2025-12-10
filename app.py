import streamlit as st
import pandas as pd
import sqlite3
import datetime
import base64

# --- 1. CONFIG & CSS MAGIC (UI 靈魂) ---
st.set_page_config(page_title="TIM TEAM ELITE", page_icon="💎", layout="wide")
DB_FILE = 'tim_team.db'

# 注入 CSS (令 UI 變靚的魔法)
st.markdown("""
<style>
    /* 全局背景 & 字體 */
    .stApp {background: linear-gradient(to right, #f8f9fa, #e9ecef);}
    h1, h2, h3 {font-family: 'Helvetica Neue', sans-serif; color: #2c3e50;}
    
    /* 側邊欄 Sidebar */
    [data-testid="stSidebar"] {
        background-color: #ffffff;
        border-right: 1px solid #e0e0e0;
        box-shadow: 2px 0 10px rgba(0,0,0,0.05);
    }
    
    /* 頂級 KPI 卡片 (懸浮效果) */
    div[data-testid="stMetric"] {
        background: linear-gradient(135deg, #ffffff 0%, #fdfbfb 100%);
        border: 1px solid #e0e0e0;
        border-radius: 15px;
        padding: 20px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
        transition: transform 0.3s ease, box-shadow 0.3s ease;
    }
    div[data-testid="stMetric"]:hover {
        transform: translateY(-5px);
        box-shadow: 0 10px 20px rgba(0,0,0,0.1);
        border-color: #3498db;
    }
    
    /* 漸變色按鈕 (Pro Button) */
    div.stButton > button {
        background: linear-gradient(90deg, #4b6cb7 0%, #182848 100%);
        color: white;
        border: none;
        border-radius: 8px;
        padding: 10px 24px;
        font-weight: bold;
        transition: all 0.3s ease;
    }
    div.stButton > button:hover {
        transform: scale(1.02);
        box-shadow: 0 5px 15px rgba(75, 108, 183, 0.4);
    }
    
    /* 表格樣式 */
    div[data-testid="stDataFrame"] {
        border-radius: 10px;
        overflow: hidden;
        border: 1px solid #e0e0e0;
        box-shadow: 0 2px 5px rgba(0,0,0,0.05);
    }
    
    /* 頭像樣式 */
    img[src^="data:image"] {
        border-radius: 50%;
        border: 3px solid #ffffff;
        box-shadow: 0 4px 10px rgba(0,0,0,0.15);
    }
</style>
""", unsafe_allow_html=True)

# --- 2. DB CORE ---
def run_query(q, p=(), fetch=False):
    try:
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            c.execute(q, p)
            if fetch: return c.fetchall()
            conn.commit()
    except: return []

def init_db():
    run_query("CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT, role TEXT, team TEXT, recruit INTEGER, avatar TEXT)")
    run_query("CREATE TABLE IF NOT EXISTS monthly_fyc (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, month TEXT, amount INTEGER)")
    run_query("CREATE TABLE IF NOT EXISTS activities (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, date TEXT, type TEXT, points INTEGER, note TEXT)")
    
    if not run_query("SELECT * FROM users", fetch=True):
        users = [('Admin', 'admin123', 'Leader'), ('Tim', '1234', 'Member'), ('Oscar', '1234', 'Member'),
                 ('Catherine', '1234', 'Member'), ('Maggie', '1234', 'Member'), ('Wilson', '1234', 'Member')]
        for u in users:
            url = f"https://ui-avatars.com/api/?name={u[0]}&background=0D8ABC&color=fff&size=128"
            run_query("INSERT INTO users VALUES (?,?,?,?,?,?)", (u[0], u[1], u[2], 'Tim Team', 0, url))

init_db()

# --- 3. LOGIC ---
def login(u, p): return run_query('SELECT * FROM users WHERE username=? AND password=?', (u, p), fetch=True)
def update_avt(u, i): run_query("UPDATE users SET avatar=? WHERE username=?", (i, u))
def add_act(u, d, t, n):
    pts = 5 if "Closing" in t else (2 if "Insurance" in t else 1)
    run_query("INSERT INTO activities (username, date, type, points, note) VALUES (?,?,?,?,?)", (u, d, t, pts, n))
def upd_fyc(u, m, a):
    eid = run_query("SELECT id FROM monthly_fyc WHERE username=? AND month=?", (u, m), fetch=True)
    if eid: run_query("UPDATE monthly_fyc SET amount=? WHERE id=?", (a, eid[0][0]))
    else: run_query("INSERT INTO monthly_fyc (username, month, amount) VALUES (?,?,?)", (u, m, a))
def upd_rec(u, a): run_query("UPDATE users SET recruit=? WHERE username=?", (a, u))
def del_act(id): run_query("DELETE FROM activities WHERE id=?", (id,))
def upd_act(id, d, t, n):
    pts = 5 if "Closing" in t else (2 if "Insurance" in t else 1)
    run_query("UPDATE activities SET date=?, type=?, points=?, note=? WHERE id=?", (d, t, pts, n, id))
def get_act_by_id(id): return run_query("SELECT * FROM activities WHERE id=?", (id,), fetch=True)
def get_all_act():
    with sqlite3.connect(DB_FILE) as c: return pd.read_sql("SELECT id, username, date, type, points, note FROM activities ORDER BY date DESC", c)
def get_data(month=None):
    with sqlite3.connect(DB_FILE) as c:
        users = pd.read_sql("SELECT username, team, recruit, avatar FROM users WHERE role='Member'", c)
        f_sql = "SELECT username, SUM(amount) as fyc FROM monthly_fyc GROUP BY username" if month=="Yearly" else f"SELECT username, amount as fyc FROM monthly_fyc WHERE month='{month}'"
        fyc = pd.read_sql(f_sql, c)
        act = pd.read_sql("SELECT username, SUM(points) as Total_Score FROM activities GROUP BY username", c)
    df = pd.merge(users, fyc, on='username', how='left').fillna(0)
    return pd.merge(df, act, on='username', how='left').fillna(0)
def get_user_act(u):
    with sqlite3.connect(DB_FILE) as c: return pd.read_sql(f"SELECT date, type, points, note FROM activities WHERE username='{u}' ORDER BY date DESC", c)
def proc_img(f):
    try: return f"data:image/png;base64,{base64.b64encode(f.getvalue()).decode()}" if f else None
    except: return None

# --- 4. UI STRUCTURE ---
if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False

if not st.session_state['logged_in']:
    c1, c2, c3 = st.columns([1,1.5,1])
    with c2:
        st.markdown("<br><br>", unsafe_allow_html=True)
        with st.container(border=True):
            st.markdown("<h1 style='text-align: center;'>💎 TIM TEAM</h1>", unsafe_allow_html=True)
            st.caption("Access your elite workspace")
            u = st.text_input("Username")
            p = st.text_input("Password", type="password")
            if st.button("ENTER WORKSPACE", use_container_width=True):
                d = login(u, p)
                if d:
                    st.session_state.update({'logged_in':True, 'user':d[0][0], 'role':d[0][2], 'avatar':d[0][5]})
                    st.rerun()
                else: st.error("Access Denied")
else:
    # Sidebar
    with st.sidebar:
        st.markdown("<br>", unsafe_allow_html=True)
        c_avt, c_txt = st.columns([1, 2])
        with c_avt: st.image(st.session_state.get('avatar',''), width=70)
        with c_txt: 
            st.markdown(f"**{st.session_state['user']}**")
            st.caption(st.session_state['role'])
        
        st.divider()
        menu = st.radio("NAVIGATION", ["📊 Dashboard", "📅 Monthly FYC", "🤝 Recruitment", "📝 Activities", "👤 Profile"])
        st.markdown("<br>"*5, unsafe_allow_html=True)
        if st.button("LOGOUT", use_container_width=True):
            st.session_state['logged_in'] = False
            st.rerun()

    # Dashboard
    if menu == "📊 Dashboard":
        st.markdown("## 📊 Executive Dashboard")
        st.markdown("Your team's performance at a glance.")
        
        df = get_data("Yearly")
        c1, c2, c3 = st.columns(3)
        c1.metric("💰 Total FYC (YTD)", f"${df['fyc'].sum():,}", delta="Yearly Goal")
        c2.metric("🎯 Total Activities", int(df['Total_Score'].sum()), delta="Active")
        c3.metric("👥 Total Recruits", int(df['recruit'].sum()), delta="Growing")
        
        st.markdown("### 🏆 MDRT Road to 2026")
        with st.container(border=True):
            cfg = {
                "avatar": st.column_config.ImageColumn("Agent", width="small"), 
                "fyc": st.column_config.ProgressColumn("MDRT Progress ($800k)", format="$%d", max_value=800000),
                "Total_Score": st.column_config.NumberColumn("Activity Pts"),
                "recruit": st.column_config.NumberColumn("Recruits")
            }
            st.dataframe(
                df[['avatar', 'username', 'fyc', 'Total_Score', 'recruit']].sort_values(by='fyc', ascending=False),
                column_config=cfg, use_container_width=True, hide_index=True
            )
        
        if st.session_state['role'] == 'Leader':
            st.divider()
            st.subheader("⚙️ Admin Control Center")
            t1, t2, t3 = st.tabs(["💰 Update FYC", "🤝 Update Recruit", "📝 Logs Manager"])
            
            with t1:
                c_a, c_b, c_c = st.columns(3)
                tgt = c_a.selectbox("Agent", df['username'].tolist(), key="f1")
                mth = c_b.selectbox("Month", [f"2026-{i:02d}" for i in range(1,13)])
                amt = c_c.number_input("Amount ($)", step=1000)
                if st.button("UPDATE FYC RECORD"):
                    upd_fyc(tgt, mth, amt)
                    st.success(f"FYC Updated for {tgt}!")
                    st.rerun()
            with t2:
                c_a, c_b = st.columns(2)
                tgt_r = c_a.selectbox("Agent", df['username'].tolist(), key="r1")
                rec = c_b.number_input("Total Recruits", step=1)
                if st.button("UPDATE RECRUITMENT"):
                    upd_rec(tgt_r, rec)
                    st.success("Recruitment Updated!")
                    st.rerun()
            with t3:
                st.dataframe(get_all_act(), use_container_width=True, height=200)
                ce, cd = st.columns(2)
                with ce:
                    eid = st.number_input("Edit ID", step=1)
                    if eid > 0 and get_act_by_id(eid):
                        with st.expander(f"Edit Entry #{eid}", expanded=True):
                            nd = st.date_input("Date")
                            nt = st.selectbox("Type", ["Meeting (1分)", "Insurance Talk (2分)", "Closing (5分)"])
                            nn = st.text_area("Note")
                            if st.button("CONFIRM EDIT"):
                                upd_act(eid, nd, nt, nn)
                                st.success("Entry Edited!")
                                st.rerun()
                with cd:
                    did = st.number_input("Delete ID", step=1)
                    if st.button("DELETE ENTRY"):
                        del_act(did)
                        st.success("Entry Deleted!")
                        st.rerun()

    # Monthly
    elif menu == "📅 Monthly FYC":
        st.header("📅 Monthly Performance Review")
        m = st.selectbox("Select Period", [f"2026-{i:02d}" for i in range(1,13)])
        df = get_data(m)
        if df['fyc'].sum() > 0:
            top = df.sort_values(by='fyc', ascending=False).iloc[0]
            if top['fyc'] > 0:
                st.markdown(f"""
                <div style="background: linear-gradient(90deg, #FDB931 0%, #F9D976 100%); padding: 20px; border-radius: 10px; color: #333; text-align: center; box-shadow: 0 4px 15px rgba(0,0,0,0.1);">
                    <h2 style="margin:0;">👑 Star of the Month: {top['username']}</h2>
                    <h1 style="margin:0;">${top['fyc']:,}</h1>
                </div><br>
                """, unsafe_allow_html=True)
        
        cfg = {"avatar": st.column_config.ImageColumn("Agent", width="small"), "fyc": st.column_config.NumberColumn("Monthly FYC", format="$%d")}
        st.dataframe(df[['avatar', 'username', 'fyc']].sort_values(by='fyc', ascending=False), column_config=cfg, use_container_width=True, hide_index=True)

    # Recruitment
    elif menu == "🤝 Recruitment":
        st.header("🤝 Team Growth Leaderboard")
        df = get_data("Yearly")
        c1, c2 = st.columns([2, 1])
        with c1:
            cfg = {"avatar": st.column_config.ImageColumn("Agent", width="small"), "recruit": st.column_config.NumberColumn("Total Recruits", format="%d")}
            st.dataframe(df[['avatar', 'username', 'recruit']].sort_values(by='recruit', ascending=False), column_config=cfg, use_container_width=True, hide_index=True)
        with c2:
            st.info("💡 Tip: Identify potential leaders from this list.")

    # Activities
    elif menu == "📝 Activities":
        st.header("📝 Daily Activity Logger")
        c1, c2 = st.columns([1, 1.5])
        with c1:
            with st.container(border=True):
                st.subheader("Log New Activity")
                d = st.date_input("Date")
                t = st.selectbox("Activity Type", ["Meeting (1分)", "Insurance Talk (2分)", "Closing (5分)"])
                n = st.text_area("Notes / Outcome")
                if st.button("SUBMIT LOG", type="primary", use_container_width=True):
                    add_act(st.session_state['user'], d, t, n)
                    st.toast("Activity Logged Successfully!", icon="✅")
        with c2:
            st.subheader("Recent History")
            st.dataframe(get_user_act(st.session_state['user']), use_container_width=True, hide_index=True)

    # Settings
    elif menu == "👤 Profile":
        st.header("User Profile")
        with st.container(border=True):
            c1, c2 = st.columns([1, 3])
            c1.image(st.session_state.get('avatar', ''), width=120)
            f = c2.file_uploader("Upload New Avatar (JPG/PNG)", type=['jpg', 'png'])
            if f and c2.button("UPDATE AVATAR", type="primary"):
                c = proc_img(f)
                if c:
                    update_avt(st.session_state['user'], c)
                    st.session_state['avatar'] = c
                    st.success("Avatar Updated!")
                    st.rerun()