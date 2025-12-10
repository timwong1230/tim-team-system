import streamlit as st
import pandas as pd
import sqlite3
import datetime
import base64

# --- Config & Style ---
st.set_page_config(page_title="TIM TEAM", page_icon="🦁", layout="wide")
DB_FILE = 'tim_team.db'

st.markdown("""
<style>
    .stApp {background-color: #F8F9FA;}
    [data-testid="stSidebar"] {background-color: #FFFFFF; border-right: 1px solid #E0E0E0;}
    div[data-testid="stMetric"] {background-color:#FFF; border:1px solid #E0E0E0; border-radius:12px; padding:15px;}
    [data-testid="stSidebar"] img {border-radius:50%; border:2px solid #fff; box-shadow:0 4px 6px rgba(0,0,0,0.1);}
</style>
""", unsafe_allow_html=True)

# --- Database ---
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
            url = f"https://ui-avatars.com/api/?name={u[0]}&background=random&color=fff"
            run_query("INSERT INTO users VALUES (?,?,?,?,?,?)", (u[0], u[1], u[2], 'Tim Team', 0, url))

init_db()

# --- Logic ---
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

# --- UI ---
if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False

if not st.session_state['logged_in']:
    c1, c2, c3 = st.columns([1,2,1])
    with c2:
        st.markdown("<br><br>", unsafe_allow_html=True)
        with st.container(border=True):
            st.title("🦁 Login")
            u = st.text_input("Username")
            p = st.text_input("Password", type="password")
            if st.button("Sign In", type="primary", use_container_width=True):
                d = login(u, p)
                if d:
                    st.session_state.update({'logged_in':True, 'user':d[0][0], 'role':d[0][2], 'avatar':d[0][5]})
                    st.rerun()
                else: st.error("Invalid")
else:
    with st.sidebar:
        st.image(st.session_state.get('avatar',''), width=80)
        st.markdown(f"### {st.session_state['user']}")
        st.caption(f"Role: {st.session_state['role']}")
        st.divider()
        menu = st.radio("Workspace", ["📊 Dashboard", "📅 Monthly FYC", "🤝 Recruitment", "📝 Activity Log", "👤 Settings"])
        st.markdown("<br>"*5, unsafe_allow_html=True)
        if st.button("Sign Out", use_container_width=True):
            st.session_state['logged_in'] = False
            st.rerun()

    if menu == "📊 Dashboard":
        st.header("Dashboard")
        df = get_data("Yearly")
        c1, c2, c3 = st.columns(3)
        c1.metric("💰 Total FYC", f"${df['fyc'].sum():,}")
        c2.metric("🎯 Activities", int(df['Total_Score'].sum()))
        c3.metric("👥 Recruits", int(df['recruit'].sum()))
        st.markdown("<br>", unsafe_allow_html=True)
        with st.container(border=True):
            st.subheader("🏆 MDRT Race 2026")
            cfg = {"avatar": st.column_config.ImageColumn("User", width="small"), "fyc": st.column_config.ProgressColumn("MDRT", format="$%d", max_value=800000)}
            st.dataframe(df[['avatar', 'username', 'fyc']].sort_values(by='fyc', ascending=False), column_config=cfg, use_container_width=True, hide_index=True)
        
        if st.session_state['role'] == 'Leader':
            st.markdown("<br>", unsafe_allow_html=True)
            with st.container(border=True):
                st.subheader("⚙️ Admin")
                t1, t2, t3 = st.tabs(["💰 FYC", "🤝 Recruit", "📝 Logs"])
                with t1:
                    c_a, c_b = st.columns(2)
                    tgt = c_a.selectbox("Member", df['username'].tolist(), key="f1")
                    mth = c_b.selectbox("Month", [f"2026-{i:02d}" for i in range(1,13)])
                    amt = st.number_input("Amount ($)", step=1000)
                    if st.button("Update FYC"):
                        upd_fyc(tgt, mth, amt)
                        st.success("Updated!")
                        st.rerun()
                with t2:
                    tgt_r = st.selectbox("Member", df['username'].tolist(), key="r1")
                    rec = st.number_input("Total Recruits", step=1)
                    if st.button("Update Recruit"):
                        upd_rec(tgt_r, rec)
                        st.success("Updated!")
                        st.rerun()
                with t3:
                    st.dataframe(get_all_act(), use_container_width=True, height=200)
                    ce, cd = st.columns(2)
                    with ce:
                        eid = st.number_input("Edit ID", step=1)
                        if eid > 0 and get_act_by_id(eid):
                            with st.expander(f"Edit {eid}", expanded=True):
                                nd = st.date_input("Date")
                                nt = st.selectbox("Type", ["Meeting (1分)", "Insurance Talk (2分)", "Closing (5分)"])
                                nn = st.text_area("Note")
                                if st.button("Confirm Edit"):
                                    upd_act(eid, nd, nt, nn)
                                    st.success("Edited!")
                                    st.rerun()
                    with cd:
                        did = st.number_input("Delete ID", step=1)
                        if st.button("Delete"):
                            del_act(did)
                            st.success("Deleted!")
                            st.rerun()

    elif menu == "📅 Monthly FYC":
        st.header("Monthly Performance")
        m = st.selectbox("Select Month", [f"2026-{i:02d}" for i in range(1,13)])
        df = get_data(m)
        if df['fyc'].sum() > 0:
            top = df.sort_values(by='fyc', ascending=False).iloc[0]
            if top['fyc'] > 0:
                st.balloons()
                st.info(f"🌟 Star: **{top['username']}** (${top['fyc']:,})")
        with st.container(border=True):
            cfg = {"avatar": st.column_config.ImageColumn("User", width="small"), "fyc": st.column_config.NumberColumn("FYC", format="$%d")}
            st.dataframe(df[['avatar', 'username', 'fyc']].sort_values(by='fyc', ascending=False), column_config=cfg, use_container_width=True, hide_index=True)

    elif menu == "🤝 Recruitment":
        st.header("Recruitment")
        df = get_data("Yearly")
        with st.container(border=True):
             cfg = {"avatar": st.column_config.ImageColumn("User", width="small"), "recruit": st.column_config.NumberColumn("Recruits", format="%d")}
             st.dataframe(df[['avatar', 'username', 'recruit']].sort_values(by='recruit', ascending=False), column_config=cfg, use_container_width=True, hide_index=True)

    elif menu == "📝 Activity Log":
        st.header("Activity Log")
        c1, c2 = st.columns([1, 1.5])
        with c1:
            with st.container(border=True):
                st.subheader("New Entry")
                d = st.date_input("Date")
                t = st.selectbox("Type", ["Meeting (1分)", "Insurance Talk (2分)", "Closing (5分)"])
                n = st.text_area("Note")
                if st.button("Submit", type="primary", use_container_width=True):
                    add_act(st.session_state['user'], d, t, n)
                    st.toast("Saved!", icon="✅")
        with c2:
            st.subheader("History")
            with st.container(border=True):
                st.dataframe(get_user_act(st.session_state['user']), use_container_width=True, hide_index=True)

    elif menu == "👤 Settings":
        st.header("Settings")
        with st.container(border=True):
            st.subheader("Change Avatar")
            c1, c2 = st.columns([1,3])
            c1.image(st.session_state.get('avatar', ''), width=100)
            f = c2.file_uploader("Upload", type=['jpg', 'png'])
            if f and c2.button("Update"):
                c = proc_img(f)
                if c:
                    update_avt(st.session_state['user'], c)
                    st.session_state['avatar'] = c
                    st.success("Updated!")
                    st.rerun()