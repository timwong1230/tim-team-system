import streamlit as st
import pandas as pd
import sqlite3
import datetime
import base64

# --- 1. 系統設定 & UI 魔法 ---
st.set_page_config(page_title="TIM DIRECT TEAM", page_icon="🏆", layout="wide")
DB_FILE = 'tim_team.db'

st.markdown("""
<style>
    /* 全局背景：漸變灰白，簡潔大氣 */
    .stApp {background: linear-gradient(180deg, #f8f9fa 0%, #e9ecef 100%);}
    
    /* 字體設定 */
    h1, h2, h3 {font-family: 'Microsoft JhengHei', sans-serif; color: #1a1a1a; font-weight: 700;}
    p, div, label {font-family: 'Microsoft JhengHei', sans-serif;}

    /* 側邊欄 Sidebar：純白懸浮感 */
    [data-testid="stSidebar"] {
        background-color: #ffffff;
        border-right: 1px solid #eeeeee;
        box-shadow: 4px 0 15px rgba(0,0,0,0.02);
    }
    
    /* KPI 數字卡片：磨砂玻璃質感 + 金色邊框 */
    div[data-testid="stMetric"] {
        background: rgba(255, 255, 255, 0.9);
        border: 1px solid #d4af37; /* 金色邊 */
        border-radius: 12px;
        padding: 20px;
        box-shadow: 0 4px 12px rgba(212, 175, 55, 0.15);
        transition: transform 0.2s;
    }
    div[data-testid="stMetric"]:hover {
        transform: translateY(-5px);
        box-shadow: 0 8px 20px rgba(212, 175, 55, 0.3);
    }
    div[data-testid="stMetric"] label {color: #666;}
    div[data-testid="stMetric"] div[data-testid="stMetricValue"] {color: #d4af37; font-weight: 800;}

    /* 按鈕：深藍漸變 (專業感) */
    div.stButton > button {
        background: linear-gradient(135deg, #0f2027 0%, #203a43 50%, #2c5364 100%);
        color: white;
        border: none;
        border-radius: 8px;
        padding: 10px 20px;
        font-weight: 600;
        letter-spacing: 1px;
        transition: all 0.3s ease;
    }
    div.stButton > button:hover {
        transform: scale(1.02);
        box-shadow: 0 5px 15px rgba(0,0,0,0.2);
        color: #d4af37; /* Hover 變金字 */
    }

    /* 表格優化 */
    div[data-testid="stDataFrame"] {
        border-radius: 10px;
        border: 1px solid #eee;
        overflow: hidden;
        background: white;
        box-shadow: 0 2px 10px rgba(0,0,0,0.05);
    }

    /* 頭像：金色光環 */
    img[src^="data:image"] {
        border-radius: 50%;
        border: 3px solid #d4af37;
        padding: 2px;
        box-shadow: 0 4px 10px rgba(0,0,0,0.1);
    }
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
            # 使用金色背景頭像
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
def get_user_act(u):
    with sqlite3.connect(DB_FILE) as c: return pd.read_sql(f"SELECT date, type, points, note FROM activities WHERE username='{u}' ORDER BY date DESC", c)
def proc_img(f):
    try: return f"data:image/png;base64,{base64.b64encode(f.getvalue()).decode()}" if f else None
    except: return None

# --- 4. 介面佈局 ---
if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False

# 登入畫面
if not st.session_state['logged_in']:
    c1, c2, c3 = st.columns([1,1.5,1])
    with c2:
        st.markdown("<br><br>", unsafe_allow_html=True)
        with st.container(border=True):
            st.markdown("<h1 style='text-align: center; color: #d4af37;'>🦁 TIM TEAM</h1>", unsafe_allow_html=True)
            st.markdown("<p style='text-align: center;'>DIRECT TEAM 活動量管理系統</p>", unsafe_allow_html=True)
            u = st.text_input("用戶名")
            p = st.text_input("密碼", type="password")
            if st.button("立即登入", use_container_width=True):
                d = login(u, p)
                if d:
                    st.session_state.update({'logged_in':True, 'user':d[0][0], 'role':d[0][2], 'avatar':d[0][5]})
                    st.rerun()
                else: st.error("帳號或密碼錯誤")

# 主系統畫面
else:
    # 側邊欄
    with st.sidebar:
        st.markdown("<br>", unsafe_allow_html=True)
        c_avt, c_txt = st.columns([1, 2])
        with c_avt: st.image(st.session_state.get('avatar',''), width=80)
        with c_txt: 
            st.markdown(f"**{st.session_state['user']}**")
            st.caption(f"{st.session_state['role']}")
        
        st.divider()
        # 全中文 Menu
        menu = st.radio("功能導航", ["📊 團隊總覽", "📅 每月FYC", "🤝 招募龍虎榜", "📝 活動打卡", "👤 個人設定"])
        st.markdown("<br>"*5, unsafe_allow_html=True)
        if st.button("安全登出", use_container_width=True):
            st.session_state['logged_in'] = False
            st.rerun()

    # 1. 團隊總覽 Dashboard
    if menu == "📊 團隊總覽":
        st.markdown("## 📊 2026 年度總覽")
        st.caption("MDRT 之路，由今日開始。")
        
        df = get_data("Yearly")
        c1, c2, c3 = st.columns(3)
        c1.metric("💰 全年總業績 (FYC)", f"${df['fyc'].sum():,}", delta="目標: MDRT")
        c2.metric("🎯 總活動量", int(df['Total_Score'].sum()), delta="Active")
        c3.metric("👥 團隊招募人數", int(df['recruit'].sum()), delta="Growing")
        
        st.markdown("### 🏆 全年業績龍虎榜")
        with st.container(border=True):
            cfg = {
                "avatar": st.column_config.ImageColumn("頭像", width="small"), 
                "fyc": st.column_config.ProgressColumn("MDRT 進度 ($800k)", format="$%d", max_value=800000),
                "Total_Score": st.column_config.NumberColumn("活動分"),
                "recruit": st.column_config.NumberColumn("招募")
            }
            st.dataframe(
                df[['avatar', 'username', 'fyc', 'Total_Score', 'recruit']].sort_values(by='fyc', ascending=False),
                column_config=cfg, use_container_width=True, hide_index=True
            )
        
        # Admin 管理區
        if st.session_state['role'] == 'Leader':
            st.divider()
            st.subheader("⚙️ Admin 管理台")
            t1, t2, t3 = st.tabs(["💰 更新業績", "🤝 更新招募", "📝 管理紀錄"])
            
            with t1:
                c_a, c_b, c_c = st.columns(3)
                tgt = c_a.selectbox("同事", df['username'].tolist(), key="f1")
                mth = c_b.selectbox("月份", [f"2026-{i:02d}" for i in range(1,13)])
                amt = c_c.number_input("FYC 金額 ($)", step=1000)
                if st.button("確認更新 FYC"):
                    upd_fyc(tgt, mth, amt)
                    st.success(f"已更新 {tgt} 的業績！")
                    st.rerun()
            with t2:
                c_a, c_b = st.columns(2)
                tgt_r = c_a.selectbox("同事", df['username'].tolist(), key="r1")
                rec = c_b.number_input("最新招募總數", step=1)
                if st.button("確認更新人數"):
                    upd_rec(tgt_r, rec)
                    st.success("已更新招募人數！")
                    st.rerun()
            with t3:
                st.dataframe(get_all_act(), use_container_width=True, height=200)
                ce, cd = st.columns(2)
                with ce:
                    eid = st.number_input("輸入修改 ID", step=1)
                    if eid > 0 and get_act_by_id(eid):
                        with st.expander(f"修改紀錄 #{eid}", expanded=True):
                            nd = st.date_input("日期")
                            nt = st.selectbox("種類", ["Meeting (1分)", "Insurance Talk (2分)", "Closing (5分)"])
                            nn = st.text_area("備註")
                            if st.button("確認修改"):
                                upd_act(eid, nd, nt, nn)
                                st.success("修改成功！")
                                st.rerun()
                with cd:
                    did = st.number_input("輸入刪除 ID", step=1)
                    if st.button("確認刪除"):
                        del_act(did)
                        st.success("刪除成功！")
                        st.rerun()

    # 2. 每月FYC
    elif menu == "📅 每月FYC":
        st.header("📅 每月FYC之星")
        m = st.selectbox("選擇月份", [f"2026-{i:02d}" for i in range(1,13)])
        df = get_data(m)
        if df['fyc'].sum() > 0:
            top = df.sort_values(by='fyc', ascending=False).iloc[0]
            if top['fyc'] > 0:
                st.markdown(f"""
                <div style="background: linear-gradient(135deg, #d4af37 0%, #f7ef8a 100%); padding: 20px; border-radius: 12px; color: #1a1a1a; text-align: center; box-shadow: 0 4px 15px rgba(212, 175, 55, 0.3);">
                    <h3 style="margin:0;">👑 本月 Top Sales</h3>
                    <h1 style="margin:0; font-size: 3em;">{top['username']}</h1>
                    <h2 style="margin:0;">${top['fyc']:,}</h2>
                </div><br>
                """, unsafe_allow_html=True)
        
        cfg = {"avatar": st.column_config.ImageColumn("頭像", width="small"), "fyc": st.column_config.NumberColumn("本月 FYC", format="$%d")}
        st.dataframe(df[['avatar', 'username', 'fyc']].sort_values(by='fyc', ascending=False), column_config=cfg, use_container_width=True, hide_index=True)

    # 3. 招募榜
    elif menu == "🤝 招募龍虎榜":
        st.header("🤝 DIRECT TEAM招募龍虎榜")
        st.info("發展團隊係被動收入嘅核心！")
        df = get_data("Yearly")
        with st.container(border=True):
             cfg = {"avatar": st.column_config.ImageColumn("頭像", width="small"), "recruit": st.column_config.NumberColumn("招募人數", format="%d")}
             st.dataframe(df[['avatar', 'username', 'recruit']].sort_values(by='recruit', ascending=False), column_config=cfg, use_container_width=True, hide_index=True)

    # 4. 活動打卡
    elif menu == "📝 活動打卡":
        st.header("📝 每日活動打卡")
        c1, c2 = st.columns([1, 1.5])
        with c1:
            with st.container(border=True):
                st.subheader("新增紀錄")
                d = st.date_input("日期")
                t = st.selectbox("活動種類", ["Meeting (1分)", "Insurance Talk (2分)", "Closing (5分)"])
                n = st.text_area("備註 / 結果")
                if st.button("提交紀錄", type="primary", use_container_width=True):
                    add_act(st.session_state['user'], d, t, n)
                    st.toast("成功儲存！", icon="✅")
        with c2:
            st.subheader("過往紀錄")
            st.dataframe(get_user_act(st.session_state['user']), use_container_width=True, hide_index=True)

    # 5. 設定
    elif menu == "👤 個人設定":
        st.header("個人檔案設定")
        with st.container(border=True):
            st.subheader("更換頭像")
            c1, c2 = st.columns([1, 3])
            c1.image(st.session_state.get('avatar', ''), width=120)
            f = c2.file_uploader("上傳新相片 (JPG/PNG)", type=['jpg', 'png'])
            if f and c2.button("確認更換", type="primary"):
                c = proc_img(f)
                if c:
                    update_avt(st.session_state['user'], c)
                    st.session_state['avatar'] = c
                    st.success("頭像已更新！")
                    st.rerun()