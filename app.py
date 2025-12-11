import streamlit as st
import pandas as pd
import sqlite3
import datetime
import base64

# --- 1. 系統設定 ---
st.set_page_config(page_title="TIM TEAM 2026", page_icon="🏆", layout="wide")
DB_FILE = 'tim_team.db'

st.markdown("""
<style>
    .stApp {background: linear-gradient(180deg, #f8f9fa 0%, #e9ecef 100%);}
    h1, h2, h3, p, div, label {font-family: 'Microsoft JhengHei', sans-serif;}
    [data-testid="stSidebar"] {background-color: #ffffff; border-right: 1px solid #eeeeee; box-shadow: 4px 0 15px rgba(0,0,0,0.02);}
    
    .reward-card {
        background: linear-gradient(135deg, #fff 0%, #fdfbfb 100%);
        border: 2px solid #d4af37;
        border-radius: 15px; padding: 20px;
        box-shadow: 0 4px 15px rgba(212, 175, 55, 0.2);
        text-align: center; margin-bottom: 20px;
    }
    .reward-title {color: #d4af37; font-size: 1.2em; font-weight: bold;}
    .reward-prize {color: #e74c3c; font-size: 1.5em; font-weight: 900;}
    
    div[data-testid="stMetric"] {
        background: rgba(255, 255, 255, 0.9);
        border: 1px solid #ddd; border-radius: 12px; padding: 15px;
        box-shadow: 0 2px 5px rgba(0,0,0,0.05);
    }
    div.stButton > button {
        background: linear-gradient(135deg, #0f2027 0%, #203a43 50%, #2c5364 100%);
        color: white; border: none; border-radius: 8px; padding: 10px 20px;
        transition: all 0.3s ease;
    }
    div.stButton > button:hover {transform: scale(1.02); color: #d4af37;}
    img[src^="data:image"] {border-radius: 50%; border: 3px solid #d4af37; box-shadow: 0 4px 10px rgba(0,0,0,0.1);}
</style>
""", unsafe_allow_html=True)

# --- 2. DB Functions ---
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
            url = f"https://ui-avatars.com/api/?name={u[0]}&background=d4af37&color=fff&size=128"
            run_query("INSERT INTO users VALUES (?,?,?,?,?,?)", (u[0], u[1], u[2], 'Tim Team', 0, url))

init_db()

# --- 3. Logic ---
def login(u, p): return run_query('SELECT * FROM users WHERE username=? AND password=?', (u, p), fetch=True)
def update_avt(u, i): run_query("UPDATE users SET avatar=? WHERE username=?", (i, u))
def update_pw(u, p): run_query("UPDATE users SET password=? WHERE username=?", (p, u))
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
def get_q1_data():
    with sqlite3.connect(DB_FILE) as c:
        users = pd.read_sql("SELECT username, avatar FROM users WHERE role='Member'", c)
        q1 = pd.read_sql("SELECT username, SUM(amount) as q1_total FROM monthly_fyc WHERE month IN ('2026-01', '2026-02', '2026-03') GROUP BY username", c)
    return pd.merge(users, q1, on='username', how='left').fillna(0)
def get_user_act(u):
    with sqlite3.connect(DB_FILE) as c: return pd.read_sql(f"SELECT date, type, points, note FROM activities WHERE username='{u}' ORDER BY date DESC", c)
def proc_img(f):
    try: return f"data:image/png;base64,{base64.b64encode(f.getvalue()).decode()}" if f else None
    except: return None

# --- 4. UI ---
if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False

if not st.session_state['logged_in']:
    c1, c2, c3 = st.columns([1,1.5,1])
    with c2:
        st.markdown("<br><br>", unsafe_allow_html=True)
        with st.container(border=True):
            st.markdown("<h1 style='text-align: center; color: #d4af37;'>🦁 TIM TEAM</h1>", unsafe_allow_html=True)
            u = st.text_input("用戶名")
            p = st.text_input("密碼", type="password")
            if st.button("立即登入", use_container_width=True):
                d = login(u, p)
                if d:
                    st.session_state.update({'logged_in':True, 'user':d[0][0], 'role':d[0][2], 'avatar':d[0][5]})
                    st.rerun()
                else: st.error("帳號或密碼錯誤")
else:
    with st.sidebar:
        st.markdown("<br>", unsafe_allow_html=True)
        c_avt, c_txt = st.columns([1, 2])
        with c_avt: st.image(st.session_state.get('avatar',''), width=80)
        with c_txt: 
            st.markdown(f"**{st.session_state['user']}**")
            st.caption(f"{st.session_state['role']}")
        st.divider()
        menu = st.radio("導航", ["📊 團隊總覽", "🏆 年度挑戰", "📅 每月業績", "🤝 招募龍虎榜", "📝 活動打卡", "👤 個人設定"])
        st.markdown("<br>"*5, unsafe_allow_html=True)
        if st.button("安全登出", use_container_width=True):
            st.session_state['logged_in'] = False
            st.rerun()

    if menu == "📊 團隊總覽":
        st.markdown("## 📊 2026 年度總覽")
        df = get_data("Yearly")
        if st.session_state['role'] == 'Leader':
            with st.expander("⚙️ Admin 管理台", expanded=False):
                t1, t2, t3, t4 = st.tabs(["💰 業績", "🤝 招募", "📝 紀錄", "🔑 密碼"])
                with t1:
                    c_a, c_b, c_c = st.columns(3)
                    tgt = c_a.selectbox("同事", df['username'].tolist(), key="f1")
                    mth = c_b.selectbox("月份", [f"2026-{i:02d}" for i in range(1,13)])
                    amt = c_c.number_input("FYC ($)", step=1000)
                    if st.button("更新 FYC"):
                        upd_fyc(tgt, mth, amt)
                        st.success("已更新！")
                        st.rerun()
                with t2:
                    c_a, c_b = st.columns(2)
                    tgt_r = c_a.selectbox("同事", df['username'].tolist(), key="r1")
                    rec = c_b.number_input("招募數", step=1)
                    if st.button("更新人數"):
                        upd_rec(tgt_r, rec)
                        st.success("已更新！")
                        st.rerun()
                with t3:
                    st.dataframe(get_all_act(), use_container_width=True, height=200)
                    ce, cd = st.columns(2)
                    with ce:
                        eid = st.number_input("修改 ID", step=1)
                        if eid>0 and st.button("修改"): st.info("請輸入資料")
                    with cd:
                        did = st.number_input("刪除 ID", step=1)
                        if st.button("刪除"):
                            del_act(did)
                            st.success("Deleted")
                            st.rerun()
                with t4:
                    st.info("⚠️ 強制重設同事密碼")
                    pw_u = st.selectbox("選擇同事", df['username'].tolist(), key="pw_u")
                    if st.button(f"重設 {pw_u} 密碼為 1234"):
                        update_pw(pw_u, "1234")
                        st.success(f"{pw_u} 密碼已重設為 1234")

        c1, c2, c3 = st.columns(3)
        c1.metric("💰 全年 FYC", f"${df['fyc'].sum():,}")
        c2.metric("🎯 總活動", int(df['Total_Score'].sum()))
        c3.metric("👥 招募", int(df['recruit'].sum()))
        
        st.markdown("### 🏆 實時 MDRT 進度")
        with st.container(border=True):
            cfg = {"avatar": st.column_config.ImageColumn("頭像", width="small"), "fyc": st.column_config.ProgressColumn("MDRT ($800k)", format="$%d", max_value=800000)}
            st.dataframe(df[['avatar', 'username', 'fyc', 'recruit']].sort_values(by='fyc', ascending=False), column_config=cfg, use_container_width=True, hide_index=True)

    elif menu == "🏆 年度挑戰":
        st.markdown("## 🏆 2026 年度挑戰")
        st.markdown("### 🔥 Q1 88000 Challenge")
        q1_df = get_q1_data()
        with st.container(border=True):
            for i, r in q1_df.sort_values(by='q1_total', ascending=False).iterrows():
                with st.container():
                    c_i, c_b = st.columns([1, 4])
                    with c_i: st.image(r['avatar'], width=50)
                    with c_b:
                        st.write(f"**{r['username']}** (${r['q1_total']:,})")
                        st.progress(min(1.0, r['q1_total']/88000))
        st.divider()
        c1, c2 = st.columns(2)
        with c1:
            st.markdown('<div class="reward-card"><div class="reward-title">🚀 1st MDRT</div><div class="reward-prize">$20,000</div></div>', unsafe_allow_html=True)
        with c2:
            st.markdown('<div class="reward-card"><div class="reward-title">👑 全年 FYC 冠軍</div><div class="reward-prize">$10,000</div></div>', unsafe_allow_html=True)
        c3, c4 = st.columns(2)
        with c3:
            st.markdown('<div class="reward-card"><div class="reward-title">✈️ 招募冠軍</div><div class="reward-prize">雙人機票</div></div>', unsafe_allow_html=True)
        with c4:
            st.markdown('<div class="reward-card"><div class="reward-title">🍽️ 每月冠軍</div><div class="reward-prize">Tim 請食飯</div></div>', unsafe_allow_html=True)

    elif menu == "📅 每月業績":
        st.header("📅 每月業績")
        m = st.selectbox("月份", [f"2026-{i:02d}" for i in range(1,13)])
        df = get_data(m)
        if df['fyc'].sum() > 0:
            top = df.sort_values(by='fyc', ascending=False).iloc[0]
            if top['fyc'] >= 20000:
                st.markdown(f"<div style='background:#f7ef8a;padding:20px;border-radius:10px;text-align:center;'><h3>🍽️ 本月食飯: {top['username']} (${top['fyc']:,})</h3></div><br>", unsafe_allow_html=True)
        cfg = {"avatar": st.column_config.ImageColumn("頭像", width="small"), "fyc": st.column_config.NumberColumn("FYC", format="$%d")}
        st.dataframe(df[['avatar', 'username', 'fyc']].sort_values(by='fyc', ascending=False), column_config=cfg, use_container_width=True, hide_index=True)

    elif menu == "🤝 招募龍虎榜":
        st.header("🤝 招募龍虎榜")
        df = get_data("Yearly")
        cfg = {"avatar": st.column_config.ImageColumn("頭像", width="small"), "recruit": st.column_config.NumberColumn("招募", format="%d")}
        st.dataframe(df[['avatar', 'username', 'recruit']].sort_values(by='recruit', ascending=False), column_config=cfg, use_container_width=True, hide_index=True)

    elif menu == "📝 活動打卡":
        st.header("📝 活動打卡")
        c1, c2 = st.columns([1, 1.5])
        with c1:
            with st.container(border=True):
                d = st.date_input("日期")
                t = st.selectbox("種類", ["Meeting (1分)", "Insurance Talk (2分)", "Closing (5分)"])
                n = st.text_area("備註")
                if st.button("提交紀錄", type="primary", use_container_width=True):
                    add_act(st.session_state['user'], d, t, n)
                    st.toast("Saved!", icon="✅")
        with c2:
            st.dataframe(get_user_act(st.session_state['user']), use_container_width=True, hide_index=True)

    elif menu == "👤 個人設定":
        st.header("個人設定")
        t1, t2 = st.tabs(["🖼️ 更換頭像", "🔐 修改密碼"])
        with t1:
            with st.container(border=True):
                c1, c2 = st.columns([1, 3])
                c1.image(st.session_state.get('avatar', ''), width=100)
                f = c2.file_uploader("Upload", type=['jpg', 'png'])
                if f and c2.button("更換頭像"):
                    c = proc_img(f)
                    if c:
                        update_avt(st.session_state['user'], c)
                        st.session_state['avatar'] = c
                        st.success("Updated")
                        st.rerun()
        with t2:
            with st.container(border=True):
                op = st.text_input("舊密碼", type="password")
                np = st.text_input("新密碼", type="password")
                cp = st.text_input("確認新密碼", type="password")
                if st.button("更改密碼"):
                    u = st.session_state['user']
                    # 驗證舊密碼
                    valid = login(u, op)
                    if valid:
                        if np == cp and np != "":
                            update_pw(u, np)
                            st.success("密碼已更改！請重新登入。")
                        else: st.error("新密碼不一致")
                    else: st.error("舊密碼錯誤")