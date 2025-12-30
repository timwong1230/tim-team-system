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

# --- Custom CSS (黑金高對比版) ---
st.markdown("""
<style>
    /* 1. 全局背景與字體顏色 (強制白色) */
    .stApp {
        background-color: #0E1117;
        color: #FAFAFA;
    }
    
    /* 強制所有基本文字、Label、段落變成淺灰色，確保睇得倒 */
    h1, h2, h3, h4, h5, h6, p, div, span, label, li {
        color: #FAFAFA !important;
        font-family: 'Helvetica Neue', sans-serif;
    }

    /* 2. 特別指定標題做金色 */
    h1, h2, h3 {
        color: #D4AF37 !important;
    }

    /* 3. 側邊欄 */
    [data-testid="stSidebar"] {
        background-color: #161B22;
        border-right: 1px solid #30363D;
    }
    /* 側邊欄文字 */
    [data-testid="stSidebar"] * {
        color: #E6E6E6 !important;
    }

    /* 4. 卡片樣式 (Metrics) */
    div[data-testid="stMetric"], div.css-1r6slb0, .stContainer {
        background-color: #21262D;
        border: 1px solid #30363D;
        border-radius: 10px;
        padding: 15px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
    }
    /* Metric Label 修正 */
    div[data-testid="stMetricLabel"] p {
        color: #8B949E !important; /* 標籤用深灰 */
    }
    /* Metric Value 修正 */
    div[data-testid="stMetricValue"] div {
        color: #FFFFFF !important; /* 數值用全白 */
    }

    /* 5. 輸入框 (Input Fields) 修正 - 深底白字 */
    .stTextInput > div > div > input, 
    .stTextArea > div > div > textarea, 
    .stDateInput > div > div > input,
    .stSelectbox > div > div {
        background-color: #262730 !important;
        color: #FFFFFF !important;
        border-color: #4A4A4A !important;
    }
    /* 下拉選單文字修正 */
    .stSelectbox div[data-testid="stMarkdownContainer"] p {
        color: #FFFFFF !important;
    }

    /* 6. 按鈕樣式 - 漸變金 (黑字) */
    div.stButton > button {
        background: linear-gradient(135deg, #D4AF37 0%, #C5A028 100%);
        color: #000000 !important; /* 按鈕字一定要黑先睇到 */
        font-weight: bold;
        border: none;
        border-radius: 8px;
    }
    div.stButton > button:hover {
        background: linear-gradient(135deg, #FFD700 0%, #E6C200 100%);
        color: #000000 !important;
    }
    div.stButton > button p {
        color: #000000 !important; /* 強制按鈕內文字變黑 */
    }

    /* 7. 進度條顏色 */
    .stProgress > div > div > div > div {
        background-color: #D4AF37;
    }
    
    /* 8. 頭像 */
    img { border-radius: 50%; }

</style>
""", unsafe_allow_html=True)

# Google Sheets 設定
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

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
        else: return None
        creds = Credentials.from_service_account_info(key_dict, scopes=SCOPES)
        return gspread.authorize(creds)
    except: return None

def get_sheet(sheet_name):
    client = get_gs_client()
    if client:
        try:
            sh = client.open("tim_team_db")
            try: return sh.worksheet(sheet_name)
            except WorksheetNotFound:
                ws = sh.add_worksheet(title=sheet_name, rows=1000, cols=10)
                if sheet_name == "users": ws.append_row(["username", "password", "role", "team", "recruit", "avatar"])
                elif sheet_name == "monthly_fyc": ws.append_row(["id", "username", "month", "amount"])
                elif sheet_name == "activities": ws.append_row(["id", "username", "date", "type", "points", "note"])
                return ws
        except: return None
    return None

# --- 3. 數據庫操作 (Caching) ---
@st.cache_data(ttl=60)
def read_data(sheet_name):
    ws = get_sheet(sheet_name)
    if ws:
        try: return pd.DataFrame(ws.get_all_records())
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
                headers = ws.row_values(1)
                for col, val in data_dict.items():
                    if col in headers: ws.update_cell(cell.row, headers.index(col) + 1, val)
        elif action == "DELETE":
            cell = ws.find(str(row_id))
            if cell: ws.delete_rows(cell.row)
        clear_cache()
    except: st.error("操作失敗，請重試")

# 初始化
def init_db_gs():
    ws = get_sheet("users")
    if ws:
        try: existing = ws.col_values(1)
        except: existing = []
        defaults = [('Admin', 'admin123', 'Leader'), ('Tim', '1234', 'Member'), ('Oscar', '1234', 'Member'),
                    ('Catherine', '1234', 'Member'), ('Maggie', '1234', 'Member'), ('Wilson', '1234', 'Member')]
        for u in defaults:
            if u[0] not in existing:
                url = f"https://ui-avatars.com/api/?name={u[0]}&background=d4af37&color=fff&size=128"
                ws.append_row([u[0], u[1], u[2], "Tim Team", 0, url])
                clear_cache()
init_db_gs()

# --- 4. Logic Functions (V37.0 超級壓縮版) ---
def login(u, p):
    df = read_data("users")
    if df.empty: return []
    df['password'] = df['password'].astype(str)
    user = df[(df['username'] == u) & (df['password'] == str(p))]
    return user.values.tolist() if not user.empty else []

def proc_img(f):
    try:
        image = Image.open(f)
        if image.mode in ("RGBA", "P"): image = image.convert("RGB")
        image = image.resize((100, 100))
        img_byte_arr = io.BytesIO()
        image.save(img_byte_arr, format='JPEG', quality=80)
        return f"data:image/jpeg;base64,{base64.b64encode(img_byte_arr.getvalue()).decode()}"
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
    pts = 8 if "出code" in t else 5 if "簽單" in t else 3 if "報考試" in t else 2 if "傾" in t else 1
    run_query_gs("INSERT", "activities", {"username": u, "date": str(d), "type": t, "points": pts, "note": n})

def upd_fyc(u, m, a):
    df = read_data("monthly_fyc")
    exist = df[(df['username'] == u) & (df['month'] == m)]
    if not exist.empty: run_query_gs("UPDATE", "monthly_fyc", {"amount": a}, row_id=exist.iloc[0]['id'])
    else: run_query_gs("INSERT", "monthly_fyc", {"username": u, "month": m, "amount": a})

def upd_rec(u, a):
    ws = get_sheet("users")
    cell = ws.find(u)
    if cell: ws.update_cell(cell.row, ws.row_values(1).index("recruit") + 1, a); clear_cache()

def del_act(id): run_query_gs("DELETE", "activities", row_id=id)

def upd_act(id, d, t, n):
    pts = 8 if "出code" in t else 5 if "簽單" in t else 3 if "報考試" in t else 2 if "傾" in t else 1
    run_query_gs("UPDATE", "activities", {"date": str(d), "type": t, "points": pts, "note": n}, row_id=id)

def get_act_by_id(id): return read_data("activities")[read_data("activities")['id'] == id].values.tolist()

def get_user_act(u):
    df = read_data("activities")
    return df[df['username'] == u].sort_values(by='date', ascending=False)[['date', 'type', 'points', 'note']] if not df.empty else pd.DataFrame()

def get_data(month=None):
    users = read_data("users")
    if users.empty: return pd.DataFrame()
    users = users[users['role'] == 'Member'][['username', 'team', 'recruit', 'avatar']]
    fyc_df, act_df = read_data("monthly_fyc"), read_data("activities")
    
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
        return pd.merge(users, q1_sum, on='username', how='left').fillna(0)
    return pd.DataFrame(columns=['username', 'q1_total'])

def get_weekly_data():
    today = datetime.date.today()
    start = today - datetime.timedelta(days=today.weekday())
    users = read_data("users")
    if users.empty: return pd.DataFrame(), start, today
    users = users[users['role'] == 'Member'][['username', 'avatar']]
    act_df = read_data("activities")
    
    stats = pd.DataFrame(columns=['username', 'wk_score', 'wk_count'])
    if not act_df.empty:
        act_df['date'] = pd.to_datetime(act_df['date']).dt.date
        this_week = act_df[act_df['date'] >= start]
        if not this_week.empty:
            stats = this_week.groupby('username').agg({'points': ['sum', 'count']}).reset_index()
            stats.columns = ['username', 'wk_score', 'wk_count']
    return pd.merge(users, stats, on='username', how='left').fillna(0), start, today

# --- Templates & Constants ---
TEMPLATE_SALES = "【客戶資料】\nName: \n講左3Q? 有咩feedback? \nFact Find 重點: \n\n【面談內容】\nSell左咩Plan? \n客戶反應/抗拒點: \n\n【下一步】\n下次見面日期: \nAction Items: "
TEMPLATE_RECRUIT = "【準增員資料】\nName: \n背景/現職: \n對現狀不滿 (Pain Points): \n對行業最大顧慮: \n\n【面談內容】\nSell 左咩 Vision?: \n有無邀請去Team Dinner / Recruitment Talk? \n\n【下一步】\n下次跟進日期: \nAction Items: "
TEMPLATE_NEWBIE = "【新人跟進】\n新人 Name: \n今日進度 (考牌/Training/出Code): \n遇到咩困難?: \nLeader 俾左咩建議?: \n\n【下一步】\nTarget: \n下次 Review 日期: "
ACTIVITY_TYPES = ["見面 (1分)", "傾保險 (2分)", "傾招募 (2分)", "新人報考試 (3分)", "簽單 (5分)", "新人出code (8分)"]

# --- UI Layout ---
if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False

if not st.session_state['logged_in']:
    c1, c2, c3 = st.columns([1,1.5,1])
    with c2:
        st.markdown("<br><br>", unsafe_allow_html=True)
        with st.container():
            st.markdown("<div style='text-align: center;'><h1>🦁 TIM TEAM 2026</h1></div>", unsafe_allow_html=True)
            st.markdown("""
            <div style='background-color: #21262D; padding: 20px; border-radius: 10px; border: 1px solid #D4AF37; text-align: center; margin-bottom: 20px;'>
                <h2 style='color: #D4AF37; margin:0;'>MDRT + 2 Recruits</h2>
                <h3 style='color: #FAFAFA; margin:5px 0 15px 0;'>= 百萬年薪之路 💰</h3>
            </div>
            """, unsafe_allow_html=True)
            u = st.text_input("Username", placeholder="e.g., Tim")
            p = st.text_input("Password", type="password", placeholder="••••••")
            if st.button("🚀 LOGIN", use_container_width=True):
                d = login(u, p)
                if d:
                    st.session_state.update({'logged_in':True, 'user':d[0][0], 'role':d[0][2], 'avatar':d[0][5]})
                    st.toast(f"Welcome back, {d[0][0]}!", icon="🦁"); st.rerun()
                else: st.toast("Login Failed", icon="❌")
else:
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
            st.session_state['logged_in'] = False; st.rerun()

    if menu == "📊 Dashboard":
        st.markdown(f"## 📊 {st.session_state['user']}, Let's Go MDRT!")
        df = get_data("Yearly")
        c1, c2, c3 = st.columns(3)
        c1.metric("💰 Team FYC", f"${df['fyc'].sum():,.0f}"); c2.metric("👥 Recruits", int(df['recruit'].sum())); c3.metric("🔥 Activities", int(df['Total_Score'].sum()))
        st.markdown("### 🏆 Leaderboard")
        st.dataframe(df[['avatar', 'username', 'fyc', 'recruit', 'Total_Score']].sort_values(by='fyc', ascending=False),
                     column_config={"avatar": st.column_config.ImageColumn("Avatar", width="small"), "fyc": st.column_config.ProgressColumn("MDRT", format="$%d", max_value=800000)},
                     use_container_width=True, hide_index=True)
        if st.session_state['role'] == 'Leader':
            with st.expander("⚙️ Admin Tools"):
                t1, t2, t3 = st.tabs(["FYC", "Recruit", "Delete"])
                with t1:
                    c_a, c_b, c_c = st.columns(3)
                    tgt = c_a.selectbox("User", df['username'].tolist()); mth = c_b.selectbox("Month", [f"2026-{i:02d}" for i in range(1,13)]); amt = c_c.number_input("Amount", step=1000)
                    if st.button("Save FYC"): upd_fyc(tgt, mth, amt); st.toast("Saved!", icon="✅"); st.rerun()
                with t2:
                    tgt_r = st.selectbox("User", df['username'].tolist(), key="r1"); rec = st.number_input("Recruits", step=1)
                    if st.button("Save Recruit"): upd_rec(tgt_r, rec); st.toast("Saved!", icon="✅"); st.rerun()
                with t3:
                    did = st.number_input("Delete ID", step=1)
                    if st.button("Delete"): del_act(did); st.toast("Deleted", icon="🗑️"); st.rerun()

    elif menu == "📝 打卡 (Check-in)":
        st.markdown("## 📝 New Activity")
        c1, c2 = st.columns([1.2, 1])
        with c1:
            with st.container():
                d = st.date_input("日期", value=datetime.date.today()); t = st.selectbox("活動種類", ACTIVITY_TYPES)
                note_val = TEMPLATE_RECRUIT if "招募" in t else TEMPLATE_NEWBIE if "新人" in t else TEMPLATE_SALES
                n = st.text_area("備註", value=note_val, height=200)
                if st.button("✅ Submit", use_container_width=True): add_act(st.session_state['user'], d, t, n); st.toast("Saved!", icon="🦁"); st.rerun()
        with c2:
            st.markdown("### 📜 History"); st.dataframe(get_user_act(st.session_state['user']).head(10), use_container_width=True, hide_index=True)

    elif menu == "⚖️ 獎罰 (Winner Takes All)":
        df, start, end = get_weekly_data()
        st.markdown(f"## ⚖️ Winner Takes All ({start} ~ {end})")
        st.info("規則: 活動量 < 3次 👉 罰款 $100 (注入獎金池) 👉 最高分者獨得!")
        if not df.empty:
            max_score = df['wk_score'].max()
            winners = df[df['wk_score'] == max_score] if max_score > 0 else pd.DataFrame()
            pool = len(df[df['wk_count'] < 3]) * 100
            st.markdown(f"### 🏆 Prize Pool: <span style='color:#00FF00'>${pool if pool > 0 else 100}</span>", unsafe_allow_html=True)
            if not winners.empty:
                cols = st.columns(len(winners)); 
                for idx, row in winners.reset_index().iterrows(): cols[idx].image(row['avatar'], width=60); cols[idx].caption(f"👑 {row['username']}")
            st.dataframe(df[['avatar', 'username', 'wk_score', 'wk_count']].sort_values(by='wk_score', ascending=False),
                         column_config={"avatar": st.column_config.ImageColumn("", width="small"), "wk_score": st.column_config.ProgressColumn("Score", format="%d", max_value=max(10, max_score))},
                         use_container_width=True, hide_index=True)

    elif menu == "🏆 挑戰 (Challenges)":
        st.markdown("## 🏆 Q1 Challenge"); q1 = get_q1_data()
        if not q1.empty: st.dataframe(q1.sort_values(by='q1_total', ascending=False), column_config={"avatar": st.column_config.ImageColumn("", width="small"), "q1_total": st.column_config.ProgressColumn("Target $88k", format="$%d", max_value=88000)}, use_container_width=True, hide_index=True)
        st.divider(); c1, c2, c3, c4 = st.columns(4)
        c1.info("🚀 1st MDRT\n$20,000"); c2.info("👑 Top FYC\n$10,000"); c3.info("✈️ Recruit\nTicket"); c4.info("🍽️ Star\nDinner")

    elif menu == "🤝 招募 (Recruit)":
        st.markdown("## 🤝 Recruit 龍虎榜"); df = get_data("Yearly")
        if not df.empty: st.dataframe(df[['avatar', 'username', 'recruit']].sort_values(by='recruit', ascending=False), column_config={"avatar": st.column_config.ImageColumn("", width="small")}, use_container_width=True, hide_index=True)

    elif menu == "📅 業績 (Monthly)":
        st.markdown("## 📅 Monthly FYC"); m = st.selectbox("Month", [f"2026-{i:02d}" for i in range(1,13)]); df = get_data(m)
        if not df.empty and df['fyc'].sum() > 0: st.success(f"🎉 Top Sales: **{df.sort_values(by='fyc', ascending=False).iloc[0]['username']}**")
        if not df.empty: st.dataframe(df[['avatar', 'username', 'fyc']].sort_values(by='fyc', ascending=False), column_config={"avatar": st.column_config.ImageColumn("", width="small"), "fyc": st.column_config.ProgressColumn("FYC", format="$%d", max_value=100000)}, use_container_width=True, hide_index=True)

    elif menu == "👤 設定 (Profile)":
        st.markdown("## 👤 Profile"); t1, t2 = st.tabs(["Avatar", "Password"])
        with t1:
            c1, c2 = st.columns([1, 3]); c1.image(st.session_state.get('avatar', ''), width=100)
            f = c2.file_uploader("New Avatar", type=['jpg', 'png'])
            if f and c2.button("Update"): 
                c = proc_img(f)
                if c: update_avt(st.session_state['user'], c); st.session_state['avatar'] = c; st.toast("Updated!", icon="📸"); st.rerun()
        with t2:
            op = st.text_input("Old PW", type="password"); np = st.text_input("New PW", type="password"); cp = st.text_input("Confirm", type="password")
            if st.button("Change PW"):
                if login(st.session_state['user'], op): 
                    if np==cp and np: update_pw(st.session_state['user'], np); st.toast("Changed!", icon="🔐"); st.rerun()
                    else: st.error("Mismatch")
                else: st.error("Wrong PW")