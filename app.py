import streamlit as st
import pandas as pd
import datetime
import base64
import json
import gspread
import os
import io
import urllib.parse
from PIL import Image
from google.oauth2.service_account import Credentials
from gspread.exceptions import WorksheetNotFound

# --- 1. 系統設定 ---
st.set_page_config(page_title="TIM TEAM 2026", page_icon="🦁", layout="wide", initial_sidebar_state="expanded")

# --- Custom CSS (V50.1 Admin升級版) ---
st.markdown("""
<style>
    /* 全局設定 */
    [data-testid="stAppViewContainer"] { background-color: #ffffff !important; }
    [data-testid="stSidebar"] { background-color: #f8f9fa !important; border-right: 1px solid #e9ecef; }
    [data-testid="stHeader"] { background-color: rgba(0,0,0,0) !important; }
    h1, h2, h3, h4, h5, h6, p, div, span, label, li, .stMarkdown, .stText { color: #2c3e50 !important; font-family: 'Helvetica Neue', sans-serif; }
    h1, h2, h3 { color: #C5A028 !important; font-weight: 800 !important; letter-spacing: 0.5px; }

    /* 元件樣式優化 */
    div[data-testid="stMetric"], div.css-1r6slb0, .stContainer, div[data-testid="stExpander"] { background-color: #ffffff !important; border: 1px solid #e0e0e0 !important; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.05); transition: all 0.3s ease; }
    div[data-testid="stMetric"]:hover, .stContainer:hover { box-shadow: 0 6px 15px rgba(197, 160, 40, 0.15); }
    div[data-testid="stMetricValue"] { color: #2c3e50 !important; font-weight: 700; }
    div[data-testid="stMetricLabel"] { color: #7f8c8d !important; }

    /* 輸入框與按鈕 */
    .stTextInput > div > div > input, .stTextArea > div > div > textarea, .stDateInput > div > div > input, .stSelectbox > div > div { background-color: #fdfdfd !important; color: #2c3e50 !important; border: 1px solid #dce4ec !important; border-radius: 8px; }
    div.stButton > button { background: linear-gradient(135deg, #D4AF37 0%, #B38F21 100%) !important; color: #FFFFFF !important; border: none; border-radius: 8px; font-weight: 600; letter-spacing: 1px; box-shadow: 0 4px 10px rgba(212, 175, 55, 0.3); transition: transform 0.1s; }
    div.stButton > button:active { transform: scale(0.98); }
    div.stButton > button p { color: #FFFFFF !important; }
    
    /* 表格與圖片 */
    div[data-testid="stDataFrame"] { border: none; }
    div[data-testid="stDataFrame"] div[data-testid="stVerticalBlock"] { border-radius: 12px; overflow: hidden; border: 1px solid #eee; }
    img { border-radius: 50%; border: 3px solid #fff; box-shadow: 0 4px 8px rgba(0,0,0,0.1); }

    /* Admin 修改區專用 */
    .admin-edit-box { border: 2px dashed #C5A028; padding: 15px; border-radius: 10px; background-color: #fffdf0; }

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
@st.cache_data(ttl=5) # 縮短緩存時間，確保 Admin 修改後即時看到
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

# --- 4. Logic Functions ---
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

# 獲取所有活動 (包含 ID 以便修改)
def get_all_act():
    df = read_data("activities")
    if df.empty: return pd.DataFrame(columns=["id", "username", "date", "type", "points", "note"])
    df['date'] = pd.to_datetime(df['date'])
    # 將 ID 放在第一列方便查看
    cols = ['id', 'username', 'date', 'type', 'points', 'note']
    df = df[cols]
    return df.sort_values(by='date', ascending=False)

def get_user_act(u):
    df = read_data("activities")
    if df.empty: return pd.DataFrame()
    # 一般同事不需要看 ID
    return df[df['username'] == u].sort_values(by='date', ascending=False)[['date', 'type', 'points', 'note']]

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
            <div style='background-color: #ffffff; padding: 20px; border-radius: 10px; border: 1px solid #C5A028; text-align: center; margin-bottom: 20px; box-shadow: 0 4px 10px rgba(0,0,0,0.05);'>
                <h2 style='color: #C5A028 !important; margin:0;'>M + 2</h2>
                <h3 style='color: #4A4A4A !important; margin:5px 0 15px 0;'>= 百萬年薪之路 💰</h3>
                <div style='margin-top: 15px; padding-top: 10px; border-top: 1px dashed #ddd;'>
                    <span style='color: #666; font-size: 0.9em;'>2027 MDRT Requirement:</span><br>
                    <strong style='color: #D4AF37; font-size: 1.3em;'>HK$ 512,800</strong>
                </div>
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
            st.markdown(f"<h3 style='margin:0; color:#C5A028 !important;'>{st.session_state['user']}</h3>", unsafe_allow_html=True)
            st.caption(f"{st.session_state['role']} | TIM TEAM")
        st.divider()
        menu = st.radio("MAIN MENU", ["📊 Dashboard", "📝 打卡 (Check-in)", "⚖️ 獎罰 (Winner Takes All)", "🏆 挑戰 (Challenges)", "🤝 招募 (Recruit)", "📅 業績 (Monthly)", "👤 設定 (Profile)"])
        st.markdown("<br>"*3, unsafe_allow_html=True)
        if st.button("🔒 Logout", use_container_width=True, type="secondary"):
            st.session_state['logged_in'] = False; st.rerun()

    if menu == "📊 Dashboard":
        st.markdown(f"## 📊 {st.session_state['user']}, Let's Go MDRT!")
        
        # 每週戰報生成器 (Admin 專用)
        if st.session_state['role'] == 'Leader':
            with st.container(border=True):
                st.markdown("### 📢 每週戰報生成器 (Admin Only)")
                if st.button("📝 生成本週結算戰報"):
                    wk_df, start, end = get_weekly_data()
                    max_score = wk_df['wk_score'].max()
                    winners = wk_df[wk_df['wk_score'] == max_score]
                    losers = wk_df[wk_df['wk_count'] < 3]
                    penalty_total = len(losers) * 100
                    prize_per_winner = penalty_total / len(winners) if penalty_total > 0 and not winners.empty else 100 / len(winners) if not winners.empty else 0
                    
                    report = f"📅 *【TIM TEAM 本週戰報 ({start} ~ {end})】* 🦁\n\n"
                    if max_score > 0:
                        report += f"🏆 *本週 MVP (獨得獎金 ${int(prize_per_winner)}):*\n"
                        for i, w in winners.iterrows(): report += f"👑 *{w['username']}* ({int(w['wk_score'])}分)\n"
                        report += f"_多謝 {len(losers)} 位同事贊助獎金池！_\n\n" if penalty_total > 0 else "_全員達標！Tim 自掏 $100 請飲茶！_\n\n"
                    else: report += "⚠️ *本週全軍覆沒？* 無人開工？\n\n"

                    if not losers.empty:
                        report += f"💸 *【罰款名單 - 每人 $100】*\n_活動量不足 3 次，請自覺 PayMe 俾 Winner！_\n"
                        for i, l in losers.iterrows(): report += f"❌ {l['username']} (得 {int(l['wk_count'])} 次)\n"
                    else: report += "✅ *本週無人罰款！Excellent！*\n"

                    report += "\n📊 *詳細戰況：*\n"
                    for i, row in wk_df.sort_values(by='wk_score', ascending=False).iterrows():
                        report += f"{row['username']}: {int(row['wk_score'])}分 ({int(row['wk_count'])}次)\n"
                    report += "\n🚀 *新一週由零開始，大家加油！*"
                    
                    st.code(report)
                    encoded_text = urllib.parse.quote(report)
                    st.link_button("📤 Send to WhatsApp", f"https://wa.me/?text={encoded_text}")

        # Leaderboard
        df = get_data("Yearly")
        c1, c2, c3 = st.columns(3)
        c1.metric("💰 Team FYC", f"${df['fyc'].sum():,.0f}"); c2.metric("👥 Recruits", int(df['recruit'].sum())); c3.metric("🔥 Activities", int(df['Total_Score'].sum()))
        st.markdown("### 🏆 Leaderboard")
        mdrt_target = 512800
        df['mdrt_fraction'] = df['fyc'].apply(lambda x: f"${x:,.0f} / ${mdrt_target:,.0f}")
        df['mdrt_percent'] = df['fyc'] / mdrt_target
        df_sorted = df.sort_values(by='fyc', ascending=False)
        st.dataframe(
            df_sorted[['avatar', 'username', 'mdrt_fraction', 'mdrt_percent', 'recruit', 'Total_Score']],
            column_config={
                "avatar": st.column_config.ImageColumn("Avatar", width="small"),
                "username": st.column_config.TextColumn("Name"),
                "mdrt_fraction": st.column_config.TextColumn("MDRT 進度 (實數)"),
                "mdrt_percent": st.column_config.ProgressColumn("MDRT %", format="%.1f%%", min_value=0, max_value=1),
                "recruit": st.column_config.NumberColumn("Recruit", format="%d"),
                "Total_Score": st.column_config.NumberColumn("Activity", format="%d")
            },
            use_container_width=True, hide_index=True
        )

        if st.session_state['role'] == 'Leader':
            with st.expander("⚙️ 業績/招募管理 (Admin Only)"):
                c_a, c_b, c_c = st.columns(3)
                tgt = c_a.selectbox("User", df['username'].tolist()); mth = c_b.selectbox("Month", [f"2026-{i:02d}" for i in range(1,13)]); amt = c_c.number_input("Amount", step=1000)
                if st.button("Save FYC"): upd_fyc(tgt, mth, amt); st.toast("Saved!", icon="✅"); st.rerun()
                
                st.divider()
                c_d, c_e = st.columns(2)
                tgt_r = c_d.selectbox("User", df['username'].tolist(), key="r1"); rec = c_e.number_input("Recruits", step=1)
                if st.button("Save Recruit"): upd_rec(tgt_r, rec); st.toast("Saved!", icon="✅"); st.rerun()

    elif menu == "📝 打卡 (Check-in)":
        st.markdown("## 📝 New Activity")
        c1, c2 = st.columns([1.2, 1])
        
        # --- 左邊：輸入區 (保持不變) ---
        with c1:
            with st.container():
                d = st.date_input("日期", value=datetime.date.today()); t = st.selectbox("活動種類", ACTIVITY_TYPES)
                note_val = TEMPLATE_RECRUIT if "招募" in t else TEMPLATE_NEWBIE if "新人" in t else TEMPLATE_SALES
                n = st.text_area("備註", value=note_val, height=200)
                if st.button("✅ Submit", use_container_width=True): add_act(st.session_state['user'], d, t, n); st.toast("Saved!", icon="🦁"); st.rerun()
        
        # --- 右邊：History 區域 (修改了這裡：全團隊可見) ---
        with c2:
            st.markdown("### 📜 Team Activities (Live)")
            
            # 獲取所有人的紀錄
            all_acts = get_all_act()
            
            # 如果是 Leader (Admin)，顯示 ID 方便修改
            if st.session_state['role'] == 'Leader':
                st.info("👋 Admin 模式：你可修改任何紀錄")
                
                # Admin 看的表格 (包含 ID)
                st.dataframe(all_acts, use_container_width=True, height=400, hide_index=True)
                
                # Admin 修改工具
                st.markdown("<div class='admin-edit-box'>", unsafe_allow_html=True)
                st.markdown("#### 🛠 修改/刪除紀錄")
                target_id = st.number_input("輸入 ID (見上表第一列)", min_value=0, step=1)
                
                if target_id > 0:
                    record = get_act_by_id(target_id)
                    if record:
                        r = record[0] 
                        st.write(f"正在修改: **{r[1]}** 於 {r[2]} 的紀錄")
                        with st.form("admin_edit_form"):
                            new_date = st.date_input("新日期", value=pd.to_datetime(r[2]))
                            new_type = st.selectbox("新活動種類", ACTIVITY_TYPES, index=ACTIVITY_TYPES.index(r[3]) if r[3] in ACTIVITY_TYPES else 0)
                            new_note = st.text_area("新備註", value=r[5])
                            c_update, c_delete = st.columns(2)
                            with c_update:
                                if st.form_submit_button("✅ 更新"): upd_act(target_id, new_date, new_type, new_note); st.toast("Updated!"); st.rerun()
                            with c_delete:
                                if st.form_submit_button("🗑 刪除", type="primary"): del_act(target_id); st.toast("Deleted!"); st.rerun()
                    else:
                        st.warning("找不到此 ID")
                st.markdown("</div>", unsafe_allow_html=True)

            # 如果是普通 Member，看全團隊紀錄 (但隱藏 ID，唯讀)
            else:
                st.caption(f"👀 睇下其他同事做緊咩 (顯示最近 {len(all_acts)} 條紀錄)")
                
                # 整理表格：隱藏 ID，將 Username 放第一列，讓同事知道是誰做的
                if not all_acts.empty:
                    display_df = all_acts[['date', 'username', 'type', 'points', 'note']]
                    st.dataframe(
                        display_df, 
                        use_container_width=True, 
                        height=500, 
                        hide_index=True,
                        column_config={
                            "date": st.column_config.TextColumn("日期", width="small"),
                            "username": st.column_config.TextColumn("同事", width="small"),
                            "type": st.column_config.TextColumn("活動", width="medium"),
                            "points": st.column_config.NumberColumn("分", format="%d"),
                            "note": st.column_config.TextColumn("內容細節", width="large"),
                        }
                    )
                else:
                    st.info("暫時未有活動紀錄，快啲搶頭香！")
        
        # --- History 區域 (修改了這裡) ---
        with c2:
            st.markdown("### 📜 History")
            
            # 如果是 Leader (Admin)，顯示所有資料 + 修改介面
            if st.session_state['role'] == 'Leader':
                st.info("👋 Admin 模式：可查看及修改所有人的紀錄")
                all_acts = get_all_act()
                st.dataframe(all_acts, use_container_width=True, height=400)
                
                st.markdown("<div class='admin-edit-box'>", unsafe_allow_html=True)
                st.markdown("#### 🛠 修改/刪除紀錄")
                target_id = st.number_input("請輸入要修改的 ID (見左表第一列)", min_value=0, step=1)
                
                if target_id > 0:
                    # 嘗試讀取該 ID 的舊資料
                    record = get_act_by_id(target_id) # 這會返回 list
                    if record:
                        # record 格式可能為 [[id, user, date, type, pts, note]]
                        r = record[0] 
                        st.write(f"正在修改: **{r[1]}** 於 {r[2]} 的紀錄")
                        
                        with st.form("admin_edit_form"):
                            # 預設值
                            new_date = st.date_input("新日期", value=pd.to_datetime(r[2]))
                            new_type = st.selectbox("新活動種類", ACTIVITY_TYPES, index=ACTIVITY_TYPES.index(r[3]) if r[3] in ACTIVITY_TYPES else 0)
                            new_note = st.text_area("新備註", value=r[5])
                            
                            c_update, c_delete = st.columns(2)
                            with c_update:
                                if st.form_submit_button("✅ 更新紀錄"):
                                    upd_act(target_id, new_date, new_type, new_note)
                                    st.toast("Updated Successfully!"); st.rerun()
                            with c_delete:
                                if st.form_submit_button("🗑 刪除此紀錄", type="primary"):
                                    del_act(target_id)
                                    st.toast("Deleted Successfully!"); st.rerun()
                    else:
                        st.warning("找不到此 ID，請檢查列表。")
                st.markdown("</div>", unsafe_allow_html=True)

            # 如果是普通 Member，只顯示自己的，不能改
            else:
                st.dataframe(get_user_act(st.session_state['user']).head(10), use_container_width=True, hide_index=True)

    elif menu == "⚖️ 獎罰 (Winner Takes All)":
        df, start, end = get_weekly_data()
        st.markdown(f"## ⚖️ Winner Takes All ({start} ~ {end})")
        st.markdown("""
        <div class="challenge-header-box">
            <div class="challenge-title">📜 詳細遊戲規則 (Game Rules)：</div>
            <ul class="challenge-rules">
                <li><strong>結算時間：</strong> 逢星期日晚 23:59 系統自動結算。</li>
                <li><strong>罰款準則：</strong> 每週活動量 (Count) <strong>少於 3 次</strong> 者，需罰款 <strong>$100</strong>。</li>
                <li><strong>獎金歸屬：</strong> 所有罰款注入獎金池，由 <strong>最高分 (Score)</strong> 者獨得。</li>
                <li><strong>特殊情況：</strong>
                    <ul>
                        <li>若多人同為最高分，獎金平分。</li>
                        <li>若全隊達標 (無人罰款)，<strong>Tim 自掏 $100</strong> 作為獎勵 (最高分者得)。</li>
                        <li>若最高分者為 0 分，獎金累積至下週 (Rollover)。</li>
                    </ul>
                </li>
            </ul>
        </div>
        """, unsafe_allow_html=True)

        if not df.empty:
            max_score = df['wk_score'].max()
            winners = df[df['wk_score'] == max_score] if max_score > 0 else pd.DataFrame()
            pool = len(df[df['wk_count'] < 3]) * 100
            st.markdown(f"### 🏆 Prize Pool: <span style='color:#C5A028'>${pool if pool > 0 else 100}</span>", unsafe_allow_html=True)
            if not winners.empty:
                cols = st.columns(len(winners)); 
                for idx, row in winners.reset_index().iterrows(): cols[idx].image(row['avatar'], width=60); cols[idx].caption(f"👑 {row['username']}")
            st.dataframe(df[['avatar', 'username', 'wk_score', 'wk_count']].sort_values(by='wk_score', ascending=False),
                         column_config={"avatar": st.column_config.ImageColumn("", width="small"), "wk_score": st.column_config.ProgressColumn("Score", format="%d", max_value=max(10, max_score))},
                         use_container_width=True, hide_index=True)

    elif menu == "🏆 挑戰 (Challenges)":
        st.markdown("## 🏆 2026 年度挑戰")
        q1_df = get_q1_data()
        q1_target = 88000
        
        st.markdown("""
        <div class="challenge-header-box">
            <div class="challenge-title">🔥 Q1 88000 Challenge (1/1 - 31/3)</div>
            <p class="challenge-rules"><strong>目標：</strong> 第一季 (Q1) 累積 FYC 達 <strong>HK$ 88,000</strong>。<br>這是通往 MDRT 的第一張入場券，必須拿下！</p>
        </div>
        """, unsafe_allow_html=True)
        
        if not q1_df.empty:
            for i, r in q1_df.sort_values(by='q1_total', ascending=False).iterrows():
                progress = min(r['q1_total'] / q1_target, 1.0)
                st.markdown(f"""
                <div class="q1-player-card">
                    <div class="q1-avatar-box"><img src="{r['avatar']}"></div>
                    <div class="q1-info-box">
                        <div class="q1-name">{r['username']}</div>
                        <div class="q1-amount">${r['q1_total']:,.0f}</div>
                        <div class="q1-progress-container">
                            <div class="q1-progress-bar" style="width: {progress*100}%;"></div>
                        </div>
                        <div class="q1-target-label">Target: $88,000 ({progress*100:.1f}%)</div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
        
        st.divider()
        st.markdown("### 🎁 年度獎賞計劃")
        c1, c2 = st.columns(2)
        with c1: st.markdown('<div class="reward-card-premium"><span class="reward-icon">🚀</span><p class="reward-title-p">1st MDRT</p><p class="reward-prize-p">$20,000 Cash</p><p class="reward-desc-p">首位完成 $512,800 FYC 者獨得</p></div>', unsafe_allow_html=True)
        with c2: st.markdown('<div class="reward-card-premium"><span class="reward-icon">👑</span><p class="reward-title-p">Top FYC 冠軍</p><p class="reward-prize-p">$10,000 Cash</p><p class="reward-desc-p">全年業績最高者 (需 Min. 180,000 FYC)</p></div>', unsafe_allow_html=True)
        st.write("")
        c3, c4 = st.columns(2)
        with c3: st.markdown('<div class="reward-card-premium"><span class="reward-icon">✈️</span><p class="reward-title-p">招募冠軍</p><p class="reward-prize-p">雙人來回機票</p><p class="reward-desc-p">全年招募人數最多者 (需 Min. 2人)</p></div>', unsafe_allow_html=True)
        with c4: st.markdown('<div class="reward-card-premium"><span class="reward-icon">🍽️</span><p class="reward-title-p">Monthly Star</p><p class="reward-prize-p">Tim 請食飯</p><p class="reward-desc-p">單月 FYC 最高者 (需 Min. $20k)</p></div>', unsafe_allow_html=True)

    elif menu == "🤝 招募 (Recruit)":
        st.markdown("## 🤝 Recruit 龍虎榜"); df = get_data("Yearly")
        if not df.empty: st.dataframe(df[['avatar', 'username', 'recruit']].sort_values(by='recruit', ascending=False), column_config={"avatar": st.column_config.ImageColumn("", width="small"), "recruit": st.column_config.NumberColumn("招募", format="%d")}, use_container_width=True, hide_index=True)

    elif menu == "📅 業績 (Monthly)":
        st.markdown("## 📅 Monthly FYC")
        m = st.selectbox("Month", [f"2026-{i:02d}" for i in range(1,13)])
        
        df = get_data(month=m)
        
        if not df.empty:
            st.dataframe(
                df[['avatar', 'username', 'fyc']].sort_values(by='fyc', ascending=False),
                column_config={
                    "avatar": st.column_config.ImageColumn("", width="small"),
                    "fyc": st.column_config.NumberColumn("FYC", format="$%d")
                },
                use_container_width=True,
                hide_index=True
            )
        else:
            st.info("本月暫無數據")

    elif menu == "👤 設定 (Profile)":
        st.markdown("## 👤 User Profile")
        col1, col2 = st.columns([1, 2])
        with col1:
            st.image(st.session_state.get('avatar'), width=150)
        with col2:
            st.markdown(f"### {st.session_state['user']}")
            st.markdown(f"**Role:** {st.session_state['role']}")
            
            # 修改密碼
            with st.expander("🔐 Change Password"):
                new_pw = st.text_input("New Password", type="password")
                if st.button("Update Password"):
                    update_pw(st.session_state['user'], new_pw)
                    st.toast("Password Updated!", icon="✅")
            
            # 上載頭像
            with st.expander("🖼️ Change Avatar"):
                uploaded_file = st.file_uploader("Upload Image", type=['jpg', 'png', 'jpeg'])
                if uploaded_file is not None:
                    if st.button("Upload"):
                        img_str = proc_img(uploaded_file)
                        if img_str:
                            update_avt(st.session_state['user'], img_str)
                            st.session_state['avatar'] = img_str
                            st.toast("Avatar Updated!", icon="✅")
                            st.rerun()

