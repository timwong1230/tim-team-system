import streamlit as st
import pandas as pd
import sqlite3
import datetime
import base64

# --- 1. 系統設定 & UI 魔法 ---
st.set_page_config(page_title="TIM TEAM 2026", page_icon="🏆", layout="wide")
DB_FILE = 'tim_team.db'

st.markdown("""
<style>
    /* 皇家背景 */
    .stApp {background: linear-gradient(180deg, #f8f9fa 0%, #e9ecef 100%);}
    h1, h2, h3 {font-family: 'Microsoft JhengHei', sans-serif; color: #1a1a1a; font-weight: 700;}
    p, div, label {font-family: 'Microsoft JhengHei', sans-serif;}

    /* Sidebar */
    [data-testid="stSidebar"] {background-color: #ffffff; border-right: 1px solid #eeeeee; box-shadow: 4px 0 15px rgba(0,0,0,0.02);}
    
    /* 獎勵卡片特別樣式 */
    .reward-card {
        background: linear-gradient(135deg, #fff 0%, #fdfbfb 100%);
        border: 2px solid #d4af37;
        border-radius: 15px;
        padding: 20px;
        box-shadow: 0 4px 15px rgba(212, 175, 55, 0.2);
        text-align: center;
        margin-bottom: 20px;
    }
    .reward-title {color: #d4af37; font-size: 1.2em; font-weight: bold; margin-bottom: 10px;}
    .reward-prize {color: #e74c3c; font-size: 1.5em; font-weight: 900;}
    
    /* KPI Metric */
    div[data-testid="stMetric"] {
        background: rgba(255, 255, 255, 0.9);
        border: 1px solid #ddd;
        border-radius: 12px;
        padding: 15px;
        box-shadow: 0 2px 5px rgba(0,0,0,0.05);
    }

    /* 按鈕 */
    div.stButton > button {
        background: linear-gradient(135deg, #0f2027 0%, #203a43 50%, #2c5364 100%);
        color: white; border: none; border-radius: 8px; padding: 10px 20px;
        transition: all 0.3s ease;
    }
    div.stButton > button:hover {transform: scale(1.02); color: #d4af37;}

    /* 頭像 */
    img[src^="data:image"] {border-radius: 50%; border: 3px solid #d4af37; box-shadow: 0 4px 10px rgba(0,0,0,0.1);}
</style>
""", unsafe_allow_html=True)

# --- 2. 數據庫核心 ---
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

# --- 3. 邏輯函數 ---
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
def get_q1_data():
    # 專門計算 Q1 (1-3月) 的 FYC
    with sqlite3.connect(DB_FILE) as c:
        users = pd.read_sql("SELECT username, avatar FROM users WHERE role='Member'", c)
        q1_fyc = pd.read_sql("SELECT username, SUM(amount) as q1_total FROM monthly_fyc WHERE month IN ('2026-01', '2026-02', '2026-03') GROUP BY username", c)
    return pd.merge(users, q1_fyc, on='username', how='left').fillna(0)

def get_user_act(u):
    with sqlite3.connect(DB_FILE) as c: return pd.read_sql(f"SELECT date, type, points, note FROM activities WHERE username='{u}' ORDER BY date DESC", c)
def proc_img(f):
    try: return f"data:image/png;base64,{base64.b64encode(f.getvalue()).decode()}" if f else None
    except: return None

# --- 4. 介面佈局 ---
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
    # Sidebar
    with st.sidebar:
        st.markdown("<br>", unsafe_allow_html=True)
        c_avt, c_txt = st.columns([1, 2])
        with c_avt: st.image(st.session_state.get('avatar',''), width=80)
        with c_txt: 
            st.markdown(f"**{st.session_state['user']}**")
            st.caption(f"{st.session_state['role']}")
        
        st.divider()
        menu = st.radio("功能導航", ["📊 團隊總覽", "🏆 年度挑戰", "📅 每月業績", "🤝 招募龍虎榜", "📝 活動打卡", "👤 個人設定"])
        st.markdown("<br>"*5, unsafe_allow_html=True)
        if st.button("安全登出", use_container_width=True):
            st.session_state['logged_in'] = False
            st.rerun()

    # 1. 團隊總覽 Dashboard
    if menu == "📊 團隊總覽":
        st.markdown("## 📊 2026 年度總覽")
        df = get_data("Yearly")
        
        # Admin 入數區 (置頂)
        if st.session_state['role'] == 'Leader':
            with st.expander("⚙️ Admin 快速入數 (Admin Only)", expanded=False):
                st.info("💡 更新呢度既數，所有 Challenge 同 Q1 榜會自動更新。")
                t1, t2, t3 = st.tabs(["💰 更新業績", "🤝 更新招募", "📝 管理紀錄"])
                with t1:
                    c_a, c_b, c_c = st.columns(3)
                    tgt = c_a.selectbox("同事", df['username'].tolist(), key="f1")
                    mth = c_b.selectbox("月份", [f"2026-{i:02d}" for i in range(1,13)])
                    amt = c_c.number_input("FYC 金額 ($)", step=1000)
                    if st.button("更新 FYC"):
                        upd_fyc(tgt, mth, amt)
                        st.success(f"已更新 {tgt}！")
                        st.rerun()
                with t2:
                    c_a, c_b = st.columns(2)
                    tgt_r = c_a.selectbox("同事", df['username'].tolist(), key="r1")
                    rec = c_b.number_input("最新招募總數", step=1)
                    if st.button("更新人數"):
                        upd_rec(tgt_r, rec)
                        st.success("已更新招募！")
                        st.rerun()
                with t3:
                    st.dataframe(get_all_act(), use_container_width=True, height=200)
                    ce, cd = st.columns(2)
                    with ce:
                        eid = st.number_input("修改 ID", step=1)
                        if eid>0 and st.button("修改"):
                            st.info("請在下方輸入新資料後再按一次") # 簡化邏輯
                    with cd:
                        did = st.number_input("刪除 ID", step=1)
                        if st.button("刪除"):
                            del_act(did)
                            st.success("刪除成功")
                            st.rerun()
            st.divider()

        c1, c2, c3 = st.columns(3)
        c1.metric("💰 全年總 FYC", f"${df['fyc'].sum():,}")
        c2.metric("🎯 總活動量", int(df['Total_Score'].sum()))
        c3.metric("👥 招募人數", int(df['recruit'].sum()))
        
        st.markdown("### 🏆 實時 MDRT 進度")
        with st.container(border=True):
            cfg = {
                "avatar": st.column_config.ImageColumn("頭像", width="small"), 
                "fyc": st.column_config.ProgressColumn("MDRT 進度 ($800k)", format="$%d", max_value=800000),
                "recruit": st.column_config.NumberColumn("招募")
            }
            st.dataframe(df[['avatar', 'username', 'fyc', 'recruit']].sort_values(by='fyc', ascending=False), column_config=cfg, use_container_width=True, hide_index=True)

    # 2. 年度挑戰 (新功能！)
    elif menu == "🏆 年度挑戰":
        st.markdown("## 🏆 2026 年度挑戰與獎賞")
        st.caption("只要達標，Tim 請你食飯、送錢、送機票！")
        
        # Q1 Challenge 專區
        st.markdown("### 🔥 Q1 88000 Challenge (1月 - 3月)")
        q1_df = get_q1_data()
        
        # 顯示 Q1 榜
        with st.container(border=True):
            col_list = st.columns(3)
            for index, row in q1_df.sort_values(by='q1_total', ascending=False).iterrows():
                with st.container():
                    c_img, c_bar = st.columns([1, 4])
                    with c_img: st.image(row['avatar'], width=50)
                    with c_bar:
                        st.markdown(f"**{row['username']}** (目前: ${row['q1_total']:,})")
                        prog = min(1.0, row['q1_total'] / 88000)
                        st.progress(prog)
                        if row['q1_total'] >= 88000:
                            st.caption("✅ 已達標！獲得貴重禮物一份！🎁")
                        else:
                            st.caption(f"尚欠: ${88000 - row['q1_total']:,}")
            st.info("💡 完成 88,000 FYC 即獲貴重禮物！")

        st.divider()
        st.markdown("### 🏅 全年大獎")

        c1, c2 = st.columns(2)
        
        # 1st MDRT
        with c1:
            st.markdown("""
            <div class="reward-card">
                <div class="reward-title">🚀 1st MDRT Challenge</div>
                <div>首位完成 MDRT 的同事</div>
                <div class="reward-prize">獎金 $20,000</div>
            </div>
            """, unsafe_allow_html=True)
            # Check Logic
            df = get_data("Yearly")
            mdrt_winners = df[df['fyc'] >= 800000]
            if not mdrt_winners.empty:
                winner = mdrt_winners.sort_values(by='fyc', ascending=False).iloc[0]
                st.success(f"👑 目前領先: {winner['username']} (${winner['fyc']:,})")
            else:
                top = df.sort_values(by='fyc', ascending=False).iloc[0]
                st.info(f"⚡ 目前領先: {top['username']} (${top['fyc']:,})")

        # Yearly Champion
        with c2:
            st.markdown("""
            <div class="reward-card">
                <div class="reward-title">👑 全年 FYC 冠軍</div>
                <div>FYC 18萬以上起計</div>
                <div class="reward-prize">獎金 $10,000</div>
            </div>
            """, unsafe_allow_html=True)
            top_fyc = df.sort_values(by='fyc', ascending=False).iloc[0]
            if top_fyc['fyc'] >= 180000:
                st.success(f"🔥 暫定冠軍: {top_fyc['username']} (${top_fyc['fyc']:,})")
            else:
                st.warning(f"目前最高: {top_fyc['username']} (未達門檻)")

        c3, c4 = st.columns(2)
        
        # Recruitment Champ
        with c3:
            st.markdown("""
            <div class="reward-card">
                <div class="reward-title">✈️ 全年招募冠軍</div>
                <div>招募 2 人以上起計</div>
                <div class="reward-prize">雙人來回機票</div>
            </div>
            """, unsafe_allow_html=True)
            top_rec = df.sort_values(by='recruit', ascending=False).iloc[0]
            if top_rec['recruit'] >= 2:
                st.success(f"🔥 暫定冠軍: {top_rec['username']} ({top_rec['recruit']}人)")
            else:
                st.warning("暫無人達標")

        # Monthly Champ
        with c4:
            st.markdown("""
            <div class="reward-card">
                <div class="reward-title">🍽️ 每月 FYC 冠軍</div>
                <div>該月 20,000 FYC 以上</div>
                <div class="reward-prize">Tim 請食飯</div>
            </div>
            """, unsafe_allow_html=True)
            st.caption("請前往「每月業績」頁面查看")

    # 3. 每月業績
    elif menu == "📅 每月業績":
        st.header("📅 每月業績 Review")
        m = st.selectbox("選擇月份", [f"2026-{i:02d}" for i in range(1,13)])
        df = get_data(m)
        
        if df['fyc'].sum() > 0:
            top = df.sort_values(by='fyc', ascending=False).iloc[0]
            # 檢查 Challenge 2 門檻
            if top['fyc'] >= 20000:
                st.markdown(f"""
                <div style="background: linear-gradient(135deg, #d4af37 0%, #f7ef8a 100%); padding: 20px; border-radius: 12px; color: #1a1a1a; text-align: center;">
                    <h3 style="margin:0;">🍽️ 本月食飯得主</h3>
                    <h1 style="margin:0; font-size: 3em;">{top['username']}</h1>
                    <h2 style="margin:0;">${top['fyc']:,}</h2>
                </div><br>
                """, unsafe_allow_html=True)
            else:
                st.info(f"本月最高: {top['username']} (${top['fyc']:,}) - 未達 20,000 吃飯門檻")
        
        cfg = {"avatar": st.column_config.ImageColumn("頭像", width="small"), "fyc": st.column_config.NumberColumn("本月 FYC", format="$%d")}
        st.dataframe(df[['avatar', 'username', 'fyc']].sort_values(by='fyc', ascending=False), column_config=cfg, use_container_width=True, hide_index=True)

    # 4. 招募榜
    elif menu == "🤝 招募龍虎榜":
        st.header("🤝 團隊招募榜")
        df = get_data("Yearly")
        with st.container(border=True):
             cfg = {"avatar": st.column_config.ImageColumn("頭像", width="small"), "recruit": st.column_config.NumberColumn("招募人數", format="%d")}
             st.dataframe(df[['avatar', 'username', 'recruit']].sort_values(by='recruit', ascending=False), column_config=cfg, use_container_width=True, hide_index=True)

    # 5. 活動打卡
    elif menu == "📝 活動打卡":
        st.header("📝 每日活動")
        c1, c2 = st.columns([1, 1.5])
        with c1:
            with st.container(border=True):
                d = st.date_input("日期")
                t = st.selectbox("種類", ["Meeting (1分)", "Insurance Talk (2分)", "Closing (5分)"])
                n = st.text_area("備註")
                if st.button("提交紀錄", type="primary", use_container_width=True):
                    add_act(st.session_state['user'], d, t, n)
                    st.toast("成功儲存！", icon="✅")
        with c2:
            st.dataframe(get_user_act(st.session_state['user']), use_container_width=True, hide_index=True)

    # 6. 設定
    elif menu == "👤 個人設定":
        st.header("個人檔案")
        with st.container(border=True):
            c1, c2 = st.columns([1, 3])
            c1.image(st.session_state.get('avatar', ''), width=120)
            f = c2.file_uploader("上傳頭像", type=['jpg', 'png'])
            if f and c2.button("更換頭像", type="primary"):
                c = proc_img(f)
                if c:
                    update_avt(st.session_state['user'], c)
                    st.session_state['avatar'] = c
                    st.success("更新成功！")
                    st.rerun()