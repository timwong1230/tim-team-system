import streamlit as st
import pandas as pd
import datetime
import base64
import json
import gspread
import os
from google.oauth2.service_account import Credentials
from gspread.exceptions import WorksheetNotFound

# --- 1. 系統設定 ---
st.set_page_config(page_title="TIM TEAM 2026", page_icon="🦁", layout="wide")

# Google Sheets 設定
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

# --- 2. 連接 Google Sheets (V34.0 雙制式引擎) ---
@st.cache_resource
def get_gs_client():
    try:
        # 方法 A: 嘗試讀取 Streamlit Secrets (舊方法)
        if "service_account" in st.secrets:
            json_str = st.secrets["service_account"]["key_content"]
            key_dict = json.loads(json_str)
        # 方法 B: 嘗試讀取系統環境變數 (Render 新方法)
        elif "GSPREAD_KEY" in os.environ:
            json_str = os.environ["GSPREAD_KEY"]
            key_dict = json.loads(json_str)
        else:
            st.error("找不到鎖匙 (Secrets / Env Var)")
            return None

        creds = Credentials.from_service_account_info(key_dict, scopes=SCOPES)
        client = gspread.authorize(creds)
        return client
    except Exception as e:
        st.error(f"連線失敗: {e}")
        return None

def get_sheet(sheet_name):
    client = get_gs_client()
    if client:
        try:
            sh = client.open("tim_team_db")
            try:
                worksheet = sh.worksheet(sheet_name)
                return worksheet
            except WorksheetNotFound:
                worksheet = sh.add_worksheet(title=sheet_name, rows=1000, cols=10)
                if sheet_name == "users":
                    worksheet.append_row(["username", "password", "role", "team", "recruit", "avatar"])
                elif sheet_name == "monthly_fyc":
                    worksheet.append_row(["id", "username", "month", "amount"])
                elif sheet_name == "activities":
                    worksheet.append_row(["id", "username", "date", "type", "points", "note"])
                return worksheet
        except Exception as e:
            st.warning(f"⚠️ 系統繁忙 (Google API 限流)，請稍等 1 分鐘再試。")
            return None
    return None

# --- 3. 數據庫操作 (Caching) ---
@st.cache_data(ttl=60)
def read_data(sheet_name):
    ws = get_sheet(sheet_name)
    if ws:
        try:
            data = ws.get_all_records()
            return pd.DataFrame(data)
        except Exception:
            return pd.DataFrame()
    return pd.DataFrame()

def clear_cache():
    st.cache_data.clear()

def run_query_gs(action, sheet_name, data_dict=None, row_id=None):
    ws = get_sheet(sheet_name)
    if not ws: return

    try:
        if action == "INSERT":
            if sheet_name in ["activities", "monthly_fyc"]:
                records = ws.get_all_records()
                new_id = 1
                if records:
                    ids = [int(r['id']) for r in records if str(r['id']).isdigit()]
                    if ids: new_id = max(ids) + 1
                data_dict['id'] = new_id
            
            headers = ws.row_values(1)
            row_to_add = [data_dict.get(h, "") for h in headers]
            ws.append_row(row_to_add)

        elif action == "UPDATE":
            cell = ws.find(str(row_id))
            if cell:
                row_num = cell.row
                headers = ws.row_values(1)
                for col_name, val in data_dict.items():
                    if col_name in headers:
                        col_idx = headers.index(col_name) + 1
                        ws.update_cell(row_num, col_idx, val)

        elif action == "DELETE":
            cell = ws.find(str(row_id))
            if cell:
                ws.delete_rows(cell.row)
        
        clear_cache()
    except Exception as e:
        st.error(f"寫入失敗: {e}")

# 初始化 (防重覆)
def init_db_gs():
    ws = get_sheet("users")
    if ws:
        try: existing_users = ws.col_values(1)
        except: existing_users = []
        default_users = [('Admin', 'admin123', 'Leader'), ('Tim', '1234', 'Member'), ('Oscar', '1234', 'Member'),
                         ('Catherine', '1234', 'Member'), ('Maggie', '1234', 'Member'), ('Wilson', '1234', 'Member')]
        for u in default_users:
            if u[0] not in existing_users:
                url = f"https://ui-avatars.com/api/?name={u[0]}&background=d4af37&color=fff&size=128"
                user_data = {"username": u[0], "password": u[1], "role": u[2], "team": "Tim Team", "recruit": 0, "avatar": url}
                row = [user_data.get("username"), user_data.get("password"), user_data.get("role"), 
                       user_data.get("team"), user_data.get("recruit"), user_data.get("avatar")]
                ws.append_row(row)
                clear_cache()
init_db_gs()

# --- 4. Logic Functions ---
def login(u, p):
    df = read_data("users")
    if df.empty: return []
    df['password'] = df['password'].astype(str)
    user = df[(df['username'] == u) & (df['password'] == str(p))]
    if not user.empty: return user.values.tolist()
    return []

def update_avt(u, i): 
    ws = get_sheet("users")
    cell = ws.find(u)
    if cell: ws.update_cell(cell.row, ws.row_values(1).index("avatar") + 1, i); clear_cache()

def update_pw(u, p):
    ws = get_sheet("users")
    cell = ws.find(u)
    if cell: ws.update_cell(cell.row, ws.row_values(1).index("password") + 1, p); clear_cache()

def add_act(u, d, t, n):
    pts = 1
    if "出code" in t: pts = 8
    elif "簽單" in t: pts = 5
    elif "報考試" in t: pts = 3
    elif "傾" in t: pts = 2
    data = {"username": u, "date": str(d), "type": t, "points": pts, "note": n}
    run_query_gs("INSERT", "activities", data)

def upd_fyc(u, m, a):
    df = read_data("monthly_fyc")
    exist = df[(df['username'] == u) & (df['month'] == m)]
    if not exist.empty:
        run_query_gs("UPDATE", "monthly_fyc", {"amount": a}, row_id=exist.iloc[0]['id'])
    else:
        run_query_gs("INSERT", "monthly_fyc", {"username": u, "month": m, "amount": a})

def upd_rec(u, a):
    ws = get_sheet("users")
    cell = ws.find(u)
    if cell: ws.update_cell(cell.row, ws.row_values(1).index("recruit") + 1, a); clear_cache()

def del_act(id): run_query_gs("DELETE", "activities", row_id=id)

def upd_act(id, d, t, n):
    pts = 1
    if "出code" in t: pts = 8
    elif "簽單" in t: pts = 5
    elif "報考試" in t: pts = 3
    elif "傾" in t: pts = 2
    run_query_gs("UPDATE", "activities", {"date": str(d), "type": t, "points": pts, "note": n}, row_id=id)

def get_act_by_id(id):
    df = read_data("activities")
    return df[df['id'] == id].values.tolist()

def get_all_act():
    df = read_data("activities")
    if df.empty: return pd.DataFrame(columns=["id", "username", "date", "type", "points", "note"])
    df['date'] = pd.to_datetime(df['date'])
    return df.sort_values(by='date', ascending=False)

def get_data(month=None):
    users = read_data("users")
    if users.empty: return pd.DataFrame()
    users = users[users['role'] == 'Member'][['username', 'team', 'recruit', 'avatar']]
    fyc_df = read_data("monthly_fyc")
    act_df = read_data("activities")
    if month == "Yearly":
        fyc = fyc_df.groupby('username')['amount'].sum().reset_index().rename(columns={'amount': 'fyc'}) if not fyc_df.empty else pd.DataFrame(columns=['username', 'fyc'])
    else:
        fyc = fyc_df[fyc_df['month'] == month][['username', 'amount']].rename(columns={'amount': 'fyc'}) if not fyc_df.empty else pd.DataFrame(columns=['username', 'fyc'])
    act = act_df.groupby('username')['points'].sum().reset_index().rename(columns={'points': 'Total_Score'}) if not act_df.empty else pd.DataFrame(columns=['username', 'Total_Score'])
    df = pd.merge(users, fyc, on='username', how='left').fillna(0)
    df = pd.merge(df, act, on='username', how='left').fillna(0)
    return df

def get_q1_data():
    users = read_data("users")
    if users.empty: return pd.DataFrame()
    users = users[users['role'] == 'Member'][['username', 'avatar']]
    fyc_df = read_data("monthly_fyc")
    if not fyc_df.empty:
        q1 = fyc_df[fyc_df['month'].isin(['2026-01', '2026-02', '2026-03'])]
        q1_sum = q1.groupby('username')['amount'].sum().reset_index().rename(columns={'amount': 'q1_total'})
    else: q1_sum = pd.DataFrame(columns=['username', 'q1_total'])
    return pd.merge(users, q1_sum, on='username', how='left').fillna(0)

def get_user_act(u):
    df = read_data("activities")
    if df.empty: return pd.DataFrame()
    return df[df['username'] == u].sort_values(by='date', ascending=False)[['date', 'type', 'points', 'note']]

def proc_img(f):
    try: return f"data:image/png;base64,{base64.b64encode(f.getvalue()).decode()}" if f else None
    except: return None

def get_weekly_data():
    today = datetime.date.today()
    start_week = today - datetime.timedelta(days=today.weekday())
    users = read_data("users")
    if users.empty: return pd.DataFrame(), start_week, today
    users = users[users['role'] == 'Member'][['username', 'avatar']]
    act_df = read_data("activities")
    if not act_df.empty:
        act_df['date'] = pd.to_datetime(act_df['date']).dt.date
        this_week = act_df[act_df['date'] >= start_week]
        if not this_week.empty:
            stats = this_week.groupby('username').agg({'points': ['sum', 'count']}).reset_index()
            stats.columns = ['username', 'wk_score', 'wk_count']
        else: stats = pd.DataFrame(columns=['username', 'wk_score', 'wk_count'])
    else: stats = pd.DataFrame(columns=['username', 'wk_score', 'wk_count'])
    df = pd.merge(users, stats, on='username', how='left').fillna(0)
    return df, start_week, today

# --- Templates & Constants (V31) ---
TEMPLATE_SALES = "【客戶資料】\nName: \n講左3Q? 有咩feedback? \nFact Find 重點: \n\n【面談內容】\nSell左咩Plan? \n客戶反應/抗拒點: \n\n【下一步】\n下次見面日期: \nAction Items: "
TEMPLATE_RECRUIT = "【準增員資料】\nName: \n背景/現職: \n對現狀不滿 (Pain Points): \n對行業最大顧慮: \n\n【面談內容】\nSell 左咩 Vision?: \n有無邀請去Team Dinner / Recruitment Talk? \n\n【下一步】\n下次跟進日期: \nAction Items: "
TEMPLATE_NEWBIE = "【新人跟進】\n新人 Name: \n今日進度 (考牌/Training/出Code): \n遇到咩困難?: \nLeader 俾左咩建議?: \n\n【下一步】\nTarget: \n下次 Review 日期: "
ACTIVITY_TYPES = ["見面 (1分)", "傾保險 (2分)", "傾招募 (2分)", "新人報考試 (3分)", "簽單 (5分)", "新人出code (8分)"]

# --- 5. UI ---
st.markdown("""
<style>
    .stApp {background: linear-gradient(180deg, #f8f9fa 0%, #e9ecef 100%);}
    h1, h2, h3, p, div, label {font-family: 'Microsoft JhengHei', sans-serif;}
    [data-testid="stSidebar"] {background-color: #ffffff; border-right: 1px solid #eeeeee; box-shadow: 4px 0 15px rgba(0,0,0,0.02);}
    .login-card {background: #fff; border-left: 6px solid #d4af37; padding: 20px; margin-bottom: 25px; border-radius: 8px; box-shadow: 0 4px 10px rgba(0,0,0,0.05); text-align: center;}
    .login-goal {color: #1a1a1a; font-size: 1.5em; font-weight: 900; margin-bottom: 10px;}
    .highlight {color: #d4af37; font-weight: bold; font-size: 1.1em;}
    .reward-card {background: linear-gradient(135deg, #fff 0%, #fdfbfb 100%); border: 2px solid #d4af37; border-radius: 15px; padding: 20px; box-shadow: 0 4px 15px rgba(212, 175, 55, 0.2); text-align: center; margin-bottom: 20px;}
    .reward-title {color: #d4af37; font-size: 1.2em; font-weight: bold;}
    .reward-prize {color: #e74c3c; font-size: 1.5em; font-weight: 900;}
    div[data-testid="stMetric"] {background: rgba(255, 255, 255, 0.9); border: 1px solid #ddd; border-radius: 12px; padding: 15px; box-shadow: 0 2px 5px rgba(0,0,0,0.05);}
    div.stButton > button {background: linear-gradient(135deg, #0f2027 0%, #203a43 50%, #2c5364 100%); color: white; border: none; border-radius: 8px; padding: 10px 20px; transition: all 0.3s ease;}
    div.stButton > button:hover {transform: scale(1.02); color: #d4af37;}
    img[src^="data:image"] {border-radius: 50%; border: 3px solid #d4af37; box-shadow: 0 4px 10px rgba(0,0,0,0.1);}
</style>
""", unsafe_allow_html=True)

if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False

if not st.session_state['logged_in']:
    c1, c2, c3 = st.columns([1,1.5,1])
    with c2:
        st.markdown("<br><br>", unsafe_allow_html=True)
        with st.container(border=True):
            st.markdown("<h1 style='text-align: center; color: #d4af37;'>🦁 TIM TEAM 2026</h1>", unsafe_allow_html=True)
            st.markdown("""<div class="login-card"><div class="login-goal">🎯 年度目標：M + 2</div><div class="login-desc">由基本做起 · 持續做好活動量<br><span class="highlight">MDRT + 2 Recruits = 百萬年薪 💰</span></div></div>""", unsafe_allow_html=True)
            u = st.text_input("用戶名")
            p = st.text_input("密碼", type="password")
            if st.button("立即登入 · 開展百萬之路", use_container_width=True):
                d = login(u, p)
                if d:
                    st.session_state.update({'logged_in':True, 'user':d[0][0], 'role':d[0][2], 'avatar':d[0][5]})
                    st.rerun()
                else: st.error("帳號或密碼錯誤 (或系統繁忙)")
else:
    with st.sidebar:
        st.markdown("<br>", unsafe_allow_html=True)
        c_avt, c_txt = st.columns([1, 2])
        with c_avt: st.image(st.session_state.get('avatar',''), width=80)
        with c_txt: 
            st.markdown(f"**{st.session_state['user']}**")
            st.caption(f"{st.session_state['role']}")
        st.divider()
        menu = st.radio("導航", ["📊 團隊總覽", "⚖️ 活動量獎罰計劃", "🏆 年度挑戰", "📅 每月業績", "🤝 招募龍虎榜", "📝 活動打卡", "👤 設定"])
        st.markdown("<br>"*5, unsafe_allow_html=True)
        if st.button("安全登出", use_container_width=True):
            st.session_state['logged_in'] = False
            st.rerun()

    # --- Pages ---
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
                    if st.button("更新 FYC"): upd_fyc(tgt, mth, amt); st.success("已更新！"); st.rerun()
                with t2:
                    c_a, c_b = st.columns(2)
                    tgt_r = c_a.selectbox("同事", df['username'].tolist(), key="r1")
                    rec = c_b.number_input("招募數", step=1)
                    if st.button("更新人數"): upd_rec(tgt_r, rec); st.success("已更新！"); st.rerun()
                with t3:
                    st.dataframe(get_all_act(), use_container_width=True, height=200)
                    ce, cd = st.columns(2)
                    with ce:
                        eid = st.number_input("修改 ID", step=1)
                        if eid>0:
                            if get_act_by_id(eid):
                                with st.expander(f"修改 #{eid}", expanded=True):
                                    nd = st.date_input("日期")
                                    nt = st.selectbox("種類", ACTIVITY_TYPES)
                                    nn = st.text_area("備註")
                                    if st.button("確認修改"): upd_act(eid, nd, nt, nn); st.success("已修改"); st.rerun()
                    with cd:
                        did = st.number_input("刪除 ID", step=1)
                        if st.button("刪除"): del_act(did); st.success("Deleted"); st.rerun()
                with t4:
                    pw_u = st.selectbox("選擇同事", df['username'].tolist(), key="pw_u")
                    if st.button(f"重設 {pw_u} 為 1234"): update_pw(pw_u, "1234"); st.success("已重設")
        c1, c2, c3 = st.columns(3)
        if not df.empty:
            c1.metric("💰 全年 FYC", f"${df['fyc'].sum():,}")
            c2.metric("🎯 總活動", int(df['Total_Score'].sum()))
            c3.metric("👥 招募", int(df['recruit'].sum()))
            with st.container(border=True):
                cfg = {"avatar": st.column_config.ImageColumn("頭像", width="small"), "fyc": st.column_config.ProgressColumn("MDRT ($800k)", format="$%d", max_value=800000)}
                st.dataframe(df[['avatar', 'username', 'fyc', 'recruit']].sort_values(by='fyc', ascending=False), column_config=cfg, use_container_width=True, hide_index=True)

    elif menu == "⚖️ 活動量獎罰計劃":
        df, start, end = get_weekly_data()
        st.markdown(f"## ⚖️ 本週活動量獎罰計劃 ({start} 至 {end})")
        with st.expander("📜 查看遊戲規則 (Winner Takes All)", expanded=True):
            st.info("""1. 每週活動量不足 **3次** 者，罰款 **$100**。\n2. 罰款注入「每週獎金池」。\n3. **分數最高** 者獨得獎金。\n4. 若無人罰款，**Tim 送出 $100**。""")
        if not df.empty:
            lazy_ppl = df[df['wk_count'] < 3]
            penalty_pool = len(lazy_ppl) * 100
            max_score = df['wk_score'].max()
            winners = df[df['wk_score'] == max_score]
            if max_score == 0: st.warning("⚠️ 本週暫無任何活動紀錄。")
            else:
                c1, c2 = st.columns(2)
                with c1:
                    st.markdown("### 🏆 本週贏家")
                    with st.container(border=True):
                        total_prize = penalty_pool if penalty_pool > 0 else 100
                        src = f"來自 {len(lazy_ppl)} 位未達標同事" if penalty_pool > 0 else "全隊達標！Tim 請客"
                        share = total_prize / len(winners)
                        st.markdown(f"<h2 style='color:#27ae60; text-align:center;'>總獎金: ${total_prize}</h2>", unsafe_allow_html=True)
                        st.caption(f"💰 {src}")
                        st.divider()
                        for i, w in winners.iterrows():
                            c_img, c_info = st.columns([1, 4])
                            with c_img: st.image(w['avatar'], width=50)
                            with c_info: st.markdown(f"**{w['username']}** (分數: {int(w['wk_score'])})\n👉 **獲得: ${int(share)}**")
                with c2:
                    st.markdown("### ⚡ 罰款區 (<3次)")
                    with st.container(border=True):
                        if not lazy_ppl.empty:
                            st.error(f"共 ${penalty_pool} 注入獎金池。")
                            for i, l in lazy_ppl.iterrows(): st.markdown(f"❌ **{l['username']}** (次數: {int(l['wk_count'])}) - 罰 $100")
                        else: st.success("🎉 全員達標！")
            st.subheader("📊 本週戰況表")
            with st.container(border=True):
                cfg = {"avatar": st.column_config.ImageColumn("頭像", width="small"), "wk_score": st.column_config.NumberColumn("本週分數"), "wk_count": st.column_config.ProgressColumn("次數 (目標3次)", min_value=0, max_value=5, format="%d")}
                st.dataframe(df[['avatar', 'username', 'wk_score', 'wk_count']].sort_values(by='wk_score', ascending=False), column_config=cfg, use_container_width=True, hide_index=True)

    elif menu == "🏆 年度挑戰":
        st.markdown("## 🏆 2026 年度挑戰")
        q1_df = get_q1_data()
        st.markdown("### 🔥 Q1 88000 Challenge")
        if not q1_df.empty:
            with st.container(border=True):
                for i, r in q1_df.sort_values(by='q1_total', ascending=False).iterrows():
                    with st.container():
                        c_i, c_b = st.columns([1, 4])
                        with c_i: st.image(r['avatar'], width=50)
                        with c_b: st.write(f"**{r['username']}** (${r['q1_total']:,})"); st.progress(min(1.0, r['q1_total']/88000))
        st.divider()
        c1, c2 = st.columns(2)
        with c1: st.markdown('<div class="reward-card"><div class="reward-title">🚀 1st MDRT</div><div class="reward-prize">$20,000</div></div>', unsafe_allow_html=True)
        with c2: st.markdown('<div class="reward-card"><div class="reward-title">👑 全年 FYC 冠軍</div><div class="reward-prize">$10,000</div></div>', unsafe_allow_html=True)
        c3, c4 = st.columns(2)
        with c3: st.markdown('<div class="reward-card"><div class="reward-title">✈️ 招募冠軍</div><div class="reward-prize">雙人機票</div></div>', unsafe_allow_html=True)
        with c4: st.markdown('<div class="reward-card"><div class="reward-title">🍽️ 每月冠軍</div><div class="reward-prize">Tim 請食飯</div></div>', unsafe_allow_html=True)

    elif menu == "📅 每月業績":
        st.header("📅 每月業績")
        m = st.selectbox("月份", [f"2026-{i:02d}" for i in range(1,13)])
        df = get_data(m)
        if not df.empty and df['fyc'].sum() > 0:
            top = df.sort_values(by='fyc', ascending=False).iloc[0]
            if top['fyc'] >= 20000: st.markdown(f"<div style='background:#f7ef8a;padding:20px;border-radius:10px;text-align:center;'><h3>🍽️ 本月食飯: {top['username']} (${top['fyc']:,})</h3></div><br>", unsafe_allow_html=True)
        if not df.empty:
            cfg = {"avatar": st.column_config.ImageColumn("頭像", width="small"), "fyc": st.column_config.NumberColumn("FYC", format="$%d")}
            st.dataframe(df[['avatar', 'username', 'fyc']].sort_values(by='fyc', ascending=False), column_config=cfg, use_container_width=True, hide_index=True)

    elif menu == "🤝 招募龍虎榜":
        st.header("🤝 招募龍虎榜")
        df = get_data("Yearly")
        if not df.empty:
            cfg = {"avatar": st.column_config.ImageColumn("頭像", width="small"), "recruit": st.column_config.NumberColumn("招募", format="%d")}
            st.dataframe(df[['avatar', 'username', 'recruit']].sort_values(by='recruit', ascending=False), column_config=cfg, use_container_width=True, hide_index=True)

    elif menu == "📝 活動打卡":
        st.header("📝 活動打卡")
        c1, c2 = st.columns([1, 1.5])
        with c1:
            with st.container(border=True):
                d = st.date_input("日期")
                t = st.selectbox("種類", ACTIVITY_TYPES)
                
                if "招募" in t:
                    default_note = TEMPLATE_RECRUIT
                elif "新人" in t:
                    default_note = TEMPLATE_NEWBIE
                else:
                    default_note = TEMPLATE_SALES

                n = st.text_area("備註", value=default_note, height=220)
                if st.button("提交紀錄", type="primary", use_container_width=True):
                    add_act(st.session_state['user'], d, t, n)
                    st.toast("Saved!", icon="✅")
        with c2:
            st.dataframe(get_user_act(st.session_state['user']), use_container_width=True, hide_index=True)

    elif menu == "👤 設定":
        st.header("設定")
        t1, t2 = st.tabs(["🖼️ 頭像", "🔐 密碼"])
        with t1:
            c1, c2 = st.columns([1, 3])
            c1.image(st.session_state.get('avatar', ''), width=100)
            f = c2.file_uploader("Upload", type=['jpg', 'png'])
            if f and c2.button("更換"):
                c = proc_img(f)
                if c: update_avt(st.session_state['user'], c); st.session_state['avatar'] = c; st.success("Updated"); st.rerun()
        with t2:
            op = st.text_input("舊密碼", type="password")
            np = st.text_input("新密碼", type="password")
            cp = st.text_input("確認", type="password")
            if st.button("更改"):
                u = st.session_state['user']
                if login(u, op):
                    if np == cp and np != "": update_pw(u, np); st.success("成功更改"); st.rerun()
                    else: st.error("不一致")
                else: st.error("舊密碼錯")