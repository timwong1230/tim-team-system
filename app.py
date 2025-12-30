import streamlit as st
import pandas as pd
import datetime
import base64
import json
import gspread
import os
import io
from PIL import Image
from google.oauth2.service_account import Credentials
from gspread.exceptions import WorksheetNotFound

# --- 1. 系統設定 (MDRT Premium Theme) ---
st.set_page_config(page_title="TIM TEAM 2026", page_icon="🦁", layout="wide", initial_sidebar_state="expanded")

# --- Custom CSS (黑金尊貴版) ---
st.markdown("""
<style>
    /* 全局背景 - 深色高級灰 */
    .stApp {
        background-color: #0E1117;
        color: #FAFAFA;
    }
    
    /* 側邊欄 */
    [data-testid="stSidebar"] {
        background-color: #161B22;
        border-right: 1px solid #30363D;
    }
    
    /* 卡片樣式 (Metrics & Containers) */
    div[data-testid="stMetric"], div.css-1r6slb0, .stContainer {
        background-color: #21262D;
        border: 1px solid #30363D;
        border-radius: 10px;
        padding: 15px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
        transition: transform 0.2s;
    }
    div[data-testid="stMetric"]:hover {
        transform: translateY(-2px);
        border-color: #D4AF37; /* 金色邊框 */
    }

    /* 按鈕樣式 - 漸變金 */
    div.stButton > button {
        background: linear-gradient(135deg, #D4AF37 0%, #C5A028 100%);
        color: #000000;
        font-weight: bold;
        border: none;
        border-radius: 8px;
        padding: 0.5rem 1rem;
        transition: all 0.3s ease;
    }
    div.stButton > button:hover {
        background: linear-gradient(135deg, #FFD700 0%, #E6C200 100%);
        box-shadow: 0 0 10px rgba(212, 175, 55, 0.5);
        color: #000;
        transform: scale(1.02);
    }
    
    /* Secondary Button (取消/刪除) */
    button[kind="secondary"] {
        background: transparent !important;
        border: 1px solid #FF4B4B !important;
        color: #FF4B4B !important;
    }

    /* 標題金色 */
    h1, h2, h3 {
        color: #D4AF37 !important;
        font-family: 'Helvetica Neue', sans-serif;
    }
    
    /* 進度條顏色 */
    .stProgress > div > div > div > div {
        background-color: #D4AF37;
    }

    /* Input Fields */
    .stTextInput > div > div > input, .stTextArea > div > div > textarea, .stDateInput > div > div > input {
        background-color: #0E1117;
        color: #fff;
        border-color: #30363D;
    }
    
    /* 頭像圓角 */
    img {
        border-radius: 50%;
    }
</style>
""", unsafe_allow_html=True)

# Google Sheets 設定
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

# --- 2. 連接 Google Sheets ---
@st.cache_resource
def get_gs_client():
    try:
        if "service_account" in st.secrets:
            json_str = st.secrets["service_account"]["key_content"]
            key_dict = json.loads(json_str)
        elif "GSPREAD_KEY" in os.environ:
            json_str = os.environ["GSPREAD_KEY"]
            key_dict = json.loads(json_str)
        else:
            return None
        creds = Credentials.from_service_account_info(key_dict, scopes=SCOPES)
        client = gspread.authorize(creds)
        return client
    except Exception:
        return None

def get_sheet(sheet_name):
    client = get_gs_client()
    if client:
        try:
            sh = client.open("tim_team_db")
            try:
                return sh.worksheet(sheet_name)
            except WorksheetNotFound:
                worksheet = sh.add_worksheet(title=sheet_name, rows=1000, cols=10)
                if sheet_name == "users":
                    worksheet.append_row(["username", "password", "role", "team", "recruit", "avatar"])
                elif sheet_name == "monthly_fyc":
                    worksheet.append_row(["id", "username", "month", "amount"])
                elif sheet_name == "activities":
                    worksheet.append_row(["id", "username", "date", "type", "points", "note"])
                return worksheet
        except Exception:
            st.toast("⚠️ 連線忙碌中，請稍後再試", icon="⏳")
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
        except: return pd.DataFrame()
    return pd.DataFrame()

def clear_cache(): st.cache_data.clear()

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
            if cell: ws.delete_rows(cell.row)
        clear_cache()
    except: st.error("操作失敗，請重試")

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

# --- 4. Logic Functions (Updated Image Processing) ---
def login(u, p):
    df = read_data("users")
    if df.empty: return []
    df['password'] = df['password'].astype(str)
    user = df[(df['username'] == u) & (df['password'] == str(p))]
    if not user.empty: return user.values.tolist()
    return []

# V36.0 智能縮圖功能 - 解決 API Error 400
def proc_img(f):
    try:
        # 1. 開啟圖片
        image = Image.open(f)
        # 2. 強制縮細做 150x150 (足夠做頭像有餘)
        image = image.resize((150, 150))
        # 3. 轉做 Bytes
        img_byte_arr = io.BytesIO()
        image.save(img_byte_arr, format='PNG', optimize=True)
        # 4. 轉成 Base64
        return f"data:image/png;base64,{base64.b64encode(img_byte_arr.getvalue()).decode()}"
    except Exception as e:
        st.error(f"圖片處理失敗: {e}")
        return None

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

# --- Templates & Constants ---
TEMPLATE_SALES = "【客戶資料】\nName: \n講左3Q? 有咩feedback? \nFact Find 重點: \n\n【面談內容】\nSell左咩Plan? \n客戶反應/抗拒點: \n\n【下一步】\n下次見面日期: \nAction Items: "
TEMPLATE_RECRUIT = "【準增員資料】\nName: \n背景/現職: \n對現狀不滿 (Pain Points): \n對行業最大顧慮: \n\n【面談內容】\nSell 左咩 Vision?: \n有無邀請去Team Dinner / Recruitment Talk? \n\n【下一步】\n下次跟進日期: \nAction Items: "
TEMPLATE_NEWBIE = "【新人跟進】\n新人 Name: \n今日進度 (考牌/Training/出Code): \n遇到咩困難?: \nLeader 俾左咩建議?: \n\n【下一步】\nTarget: \n下次 Review 日期: "
ACTIVITY_TYPES = ["見面 (1分)", "傾保險 (2分)", "傾招募 (2分)", "新人報考試 (3分)", "簽單 (5分)", "新人出code (8分)"]

# --- 5. UI Layout ---
if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False

if not st.session_state['logged_in']:
    c1, c2, c3 = st.columns([1,1.5,1])
    with c2:
        st.markdown("<br><br>", unsafe_allow_html=True)
        # Login Card Container
        with st.container():
            st.markdown("<div style='text-align: center;'><h1>🦁 TIM TEAM 2026</h1></div>", unsafe_allow_html=True)
            st.markdown("""
            <div style='background-color: #21262D; padding: 20px; border-radius: 10px; border: 1px solid #D4AF37; text-align: center; margin-bottom: 20px;'>
                <h2 style='color: #D4AF37; margin:0;'>MDRT + 2 Recruits</h2>
                <h3 style='color: #FAFAFA; margin:5px 0 15px 0;'>= 百萬年薪之路 💰</h3>
                <p style='color: #8B949E; font-size: 0.9em;'>由基本做起 · 贏在起跑線</p>
            </div>
            """, unsafe_allow_html=True)
            u = st.text_input("Username", placeholder="e.g., Tim")
            p = st.text_input("Password", type="password", placeholder="••••••")
            if st.button("🚀 立即啟動 / LOGIN", use_container_width=True):
                d = login(u, p)
                if d:
                    st.session_state.update({'logged_in':True, 'user':d[0][0], 'role':d[0][2], 'avatar':d[0][5]})
                    st.toast(f"Welcome back, {d[0][0]}!", icon="🦁")
                    st.rerun()
                else: st.toast("Login Failed. 請檢查密碼", icon="❌")
else:
    # Sidebar Profile
    with st.sidebar:
        st.markdown("<br>", unsafe_allow_html=True)
        c_avt, c_txt = st.columns([1, 2])
        with c_avt: st.image(st.session_state.get('avatar',''), width=80)
        with c_txt: 
            st.markdown(f"<h3 style='margin:0; color:#D4AF37;'>{st.session_state['user']}</h3>", unsafe_allow_html=True)
            st.caption(f"{st.session_state['role']} | TIM TEAM")
        st.divider()
        menu = st.radio("MAIN MENU", ["📊 Dashboard", "📝 打卡 (Check-in)", "⚖️ 獎罰 (Winner Takes All)", "🏆 挑戰 (Challenges)", "🤝 招募 (Recruit)", "📅 業績 (Monthly)", "👤 設定 (Profile)"])
        st.markdown("<br>"*3, unsafe_allow_html=True)
        if st.button("🔒 Logout", use_container_width=True, type="secondary"):
            st.session_state['logged_in'] = False
            st.rerun()

    # --- Pages Content ---
    if menu == "📊 Dashboard":
        st.markdown(f"## 📊 {st.session_state['user']}, Let's Go MDRT!")
        df = get_data("Yearly")
        
        # Hero Metrics
        c1, c2, c3 = st.columns(3)
        total_fyc = df['fyc'].sum()
        total_rec = int(df['recruit'].sum())
        c1.metric("💰 全年團隊 FYC", f"${total_fyc:,.0f}", delta="MDRT Goal")
        c2.metric("👥 總招募人數", f"{total_rec}", delta="Target: +10")
        c3.metric("🔥 總活動量", int(df['Total_Score'].sum()), delta="Keep Going")

        st.markdown("### 🏆 Leaderboard")
        with st.container():
            st.dataframe(
                df[['avatar', 'username', 'fyc', 'recruit', 'Total_Score']].sort_values(by='fyc', ascending=False),
                column_config={
                    "avatar": st.column_config.ImageColumn("同事", width="small"),
                    "username": "Name",
                    "fyc": st.column_config.ProgressColumn("MDRT Progress ($800k)", format="$%d", max_value=800000),
                    "recruit": st.column_config.NumberColumn("招募", format="%d 人"),
                    "Total_Score": st.column_config.NumberColumn("活動分", format="%d")
                },
                use_container_width=True,
                hide_index=True
            )

        if st.session_state['role'] == 'Leader':
            with st.expander("⚙️ Admin Tools (只限 Leader)", expanded=False):
                t1, t2, t3 = st.tabs(["Update FYC", "Update Recruit", "Manage Records"])
                with t1:
                    c_a, c_b, c_c = st.columns(3)
                    tgt = c_a.selectbox("同事", df['username'].tolist())
                    mth = c_b.selectbox("月份", [f"2026-{i:02d}" for i in range(1,13)])
                    amt = c_c.number_input("FYC ($)", step=1000)
                    if st.button("💾 Save FYC"): upd_fyc(tgt, mth, amt); st.toast("FYC Updated!", icon="✅"); st.rerun()
                with t2:
                    c_a, c_b = st.columns(2)
                    tgt_r = c_a.selectbox("同事", df['username'].tolist(), key="r1")
                    rec = c_b.number_input("招募數", step=1)
                    if st.button("💾 Save Recruit"): upd_rec(tgt_r, rec); st.toast("Recruit Updated!", icon="✅"); st.rerun()
                with t3:
                    did = st.number_input("輸入要刪除的 Record ID", step=1)
                    if st.button("🗑️ Delete Record", type="primary"): del_act(did); st.toast("Record Deleted", icon="🗑️"); st.rerun()

    elif menu == "📝 打卡 (Check-in)":
        st.markdown("## 📝 New Activity")
        c1, c2 = st.columns([1.2, 1])
        
        with c1:
            with st.container():
                st.info("💡 每日一 Check，MDRT 越近！")
                d = st.date_input("日期", value=datetime.date.today())
                t = st.selectbox("活動種類", ACTIVITY_TYPES)
                
                if "招募" in t: default_note = TEMPLATE_RECRUIT
                elif "新人" in t: default_note = TEMPLATE_NEWBIE
                else: default_note = TEMPLATE_SALES

                n = st.text_area("備註 / Feedback", value=default_note, height=200)
                
                if st.button("✅ 提交紀錄 (Submit)", use_container_width=True):
                    add_act(st.session_state['user'], d, t, n)
                    st.toast("紀錄已儲存！Good Job!", icon="🦁")
                    st.rerun()

        with c2:
            st.markdown("### 📜 最近 10 條紀錄")
            my_acts = get_user_act(st.session_state['user']).head(10)
            st.dataframe(
                my_acts, 
                column_config={
                    "date": "日期", "type": "種類", "points": "分", "note": "備註"
                },
                use_container_width=True, hide_index=True
            )

    elif menu == "⚖️ 獎罰 (Winner Takes All)":
        df, start, end = get_weekly_data()
        st.markdown(f"## ⚖️ Winner Takes All ({start} ~ {end})")
        st.markdown("""
        <div style='background-color: #21262D; border-left: 5px solid #D4AF37; padding: 15px; margin-bottom: 20px;'>
            <strong style='color: #D4AF37;'>本週規則：</strong> <br>
            1. 活動量 < 3次 👉 罰款 $100 <br>
            2. 罰款注入獎金池 👉 <strong>最高分者獨得!</strong> 👑
        </div>
        """, unsafe_allow_html=True)

        if not df.empty:
            lazy_ppl = df[df['wk_count'] < 3]
            penalty_pool = len(lazy_ppl) * 100
            max_score = df['wk_score'].max()
            winners = df[df['wk_score'] == max_score]
            
            if max_score > 0:
                total_prize = penalty_pool if penalty_pool > 0 else 100
                st.markdown(f"### 🏆 Current Prize Pool: <span style='color:#00FF00; font-size:1.5em'>${total_prize}</span>", unsafe_allow_html=True)
                cols = st.columns(len(winners)) if len(winners) < 4 else st.columns(4)
                for idx, row in winners.reset_index().iterrows():
                    with cols[idx % 4]:
                        st.image(row['avatar'], width=60)
                        st.caption(f"👑 {row['username']}")
            else:
                st.warning("⚠️ 本週暫無戰況，快啲去打卡！")

            st.markdown("### 📊 本週戰況")
            st.dataframe(
                df[['avatar', 'username', 'wk_score', 'wk_count']].sort_values(by='wk_score', ascending=False),
                column_config={
                    "avatar": st.column_config.ImageColumn("User", width="small"),
                    "username": "Name",
                    "wk_score": st.column_config.ProgressColumn("Score", format="%d", min_value=0, max_value=max(10, max_score)),
                    "wk_count": st.column_config.NumberColumn("Count (Min 3)", format="%d 次")
                },
                use_container_width=True, hide_index=True
            )

    elif menu == "🏆 挑戰 (Challenges)":
        st.markdown("## 🏆 Q1 88000 Challenge")
        q1_df = get_q1_data()
        if not q1_df.empty:
            st.dataframe(
                q1_df.sort_values(by='q1_total', ascending=False),
                column_config={
                    "avatar": st.column_config.ImageColumn("Avatar", width="small"),
                    "username": "Name",
                    "q1_total": st.column_config.ProgressColumn("Progress ($88,000)", format="$%d", max_value=88000)
                },
                use_container_width=True, hide_index=True
            )
        
        st.divider()
        st.markdown("### 🎁 Rewards")
        c1, c2, c3, c4 = st.columns(4)
        c1.info("🚀 **1st MDRT**\n\n$20,000 Cash")
        c2.info("👑 **Top FYC**\n\n$10,000 Cash")
        c3.info("✈️ **Top Recruit**\n\n雙人機票")
        c4.info("🍽️ **Monthly Star**\n\nTim 請食飯")

    elif menu == "🤝 招募 (Recruit)":
        st.markdown("## 🤝 Recruit 龍虎榜")
        df = get_data("Yearly")
        if not df.empty:
            st.dataframe(
                df[['avatar', 'username', 'recruit']].sort_values(by='recruit', ascending=False),
                column_config={
                    "avatar": st.column_config.ImageColumn("", width="small"),
                    "username": "Name",
                    "recruit": st.column_config.NumberColumn("招募人數", format="%d 人")
                },
                use_container_width=True, hide_index=True
            )

    elif menu == "📅 業績 (Monthly)":
        st.markdown("## 📅 Monthly FYC")
        m = st.selectbox("Select Month", [f"2026-{i:02d}" for i in range(1,13)])
        df = get_data(m)
        if not df.empty and df['fyc'].sum() > 0:
            top = df.sort_values(by='fyc', ascending=False).iloc[0]
            st.success(f"🎉 本月 Top Sales: **{top['username']}** (${top['fyc']:,})")
            st.dataframe(
                df[['avatar', 'username', 'fyc']].sort_values(by='fyc', ascending=False),
                column_config={
                    "avatar": st.column_config.ImageColumn("", width="small"),
                    "fyc": st.column_config.ProgressColumn("FYC", format="$%d", max_value=100000)
                },
                use_container_width=True, hide_index=True
            )
        else:
            st.info("本月暫無業績紀錄，加油！")

    elif menu == "👤 設定 (Profile)":
        st.markdown("## 👤 User Profile")
        t1, t2 = st.tabs(["🖼️ Avatar", "🔐 Password"])
        with t1:
            c1, c2 = st.columns([1, 3])
            c1.image(st.session_state.get('avatar', ''), width=100)
            f = c2.file_uploader("Upload New Avatar", type=['jpg', 'png'])
            if f and c2.button("Update Avatar"):
                c = proc_img(f)
                if c: update_avt(st.session_state['user'], c); st.session_state['avatar'] = c; st.toast("Avatar Updated!", icon="📸"); st.rerun()
        with t2:
            op = st.text_input("Current Password", type="password")
            np = st.text_input("New Password", type="password")
            cp = st.text_input("Confirm New Password", type="password")
            if st.button("Change Password"):
                u = st.session_state['user']
                if login(u, op):
                    if np == cp and np != "": update_pw(u, np); st.toast("Password Changed!", icon="🔐"); st.rerun()
                    else: st.error("New passwords do not match")
                else: st.error("Wrong current password")