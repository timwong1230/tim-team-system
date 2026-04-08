import streamlit as st
import pandas as pd
import datetime
import base64
import json
import gspread
import os
import io
import time
import urllib.parse
from PIL import Image
from google.oauth2.service_account import Credentials
from gspread.exceptions import WorksheetNotFound, APIError

# --- 1. 系統設定 ---
st.set_page_config(page_title="TIM TEAM 2026", page_icon="🦁", layout="wide", initial_sidebar_state="expanded")

# --- Custom CSS (V50.23: 專業美學版) ---
st.markdown("""
<style>
    /* 全局設定 */
    [data-testid="stAppViewContainer"] { background-color: #f8f9fa !important; } 
    [data-testid="stSidebar"] { background-color: #ffffff !important; border-right: 1px solid #e9ecef; }
    [data-testid="stHeader"] { background-color: rgba(0,0,0,0) !important; }
    h1, h2, h3, h4, h5, h6, p, div, span, label, li, .stMarkdown, .stText { color: #2c3e50 !important; font-family: 'Helvetica Neue', sans-serif; }
    h1, h2, h3 { color: #C5A028 !important; font-weight: 800 !important; letter-spacing: 0.5px; }

    /* Sidebar Menu */
    div[role="radiogroup"] > label > div:first-child { display: none !important; }
    div[role="radiogroup"] label {
        background-color: #ffffff !important; padding: 12px 15px !important; margin-bottom: 8px !important;
        border-radius: 10px !important; border: 1px solid #e9ecef !important;
        box-shadow: 0 2px 4px rgba(0,0,0,0.03) !important; transition: all 0.3s ease !important; width: 100% !important;
    }
    div[role="radiogroup"] label:hover {
        border-color: #D4AF37 !important; background-color: #FFF8E1 !important;
        transform: translateX(5px); box-shadow: 0 4px 8px rgba(212, 175, 55, 0.2) !important;
    }

    /* Standard Components */
    div[data-testid="stMetric"], div.css-1r6slb0, .stContainer, div[data-testid="stExpander"] { background-color: #ffffff !important; border: 1px solid #e0e0e0 !important; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.05); transition: all 0.3s ease; }
    .stTextInput > div > div > input, .stTextArea > div > div > textarea, .stDateInput > div > div > input, .stSelectbox > div > div { background-color: #fdfdfd !important; border: 1px solid #dce4ec !important; border-radius: 8px; }
    div.stButton > button { background: linear-gradient(135deg, #D4AF37 0%, #B38F21 100%) !important; color: #FFFFFF !important; border: none; border-radius: 8px; font-weight: 600; letter-spacing: 1px; box-shadow: 0 4px 10px rgba(212, 175, 55, 0.3); width: 100%;}
    img { border-radius: 50%; }

    /* Admin Box */
    .admin-edit-box { border: 2px dashed #C5A028; padding: 15px; border-radius: 10px; background-color: #fffdf0; margin-top: 15px; }

    /* Timeline Card (Check-in 頁專用) */
    .activity-card { background-color: #ffffff; border-radius: 12px; padding: 16px; margin-bottom: 12px; border-left: 5px solid #e9ecef; box-shadow: 0 2px 8px rgba(0,0,0,0.05); transition: transform 0.2s;}
    .activity-card:hover { transform: translateY(-2px); box-shadow: 0 5px 15px rgba(0,0,0,0.1); }
    .card-signed { border-left-color: #D4AF37 !important; } 
    .card-meeting { border-left-color: #3498db !important; }
    .card-recruit { border-left-color: #9b59b6 !important; } 
    .card-admin { border-left-color: #95a5a6 !important; }
    .act-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
    .act-avatar { width: 40px; height: 40px; border-radius: 50%; object-fit: cover; margin-right: 10px; border: 2px solid #f0f0f0;}
    .act-name { font-weight: bold; color: #2c3e50; }
    .act-time { font-size: 0.85em; color: #95a5a6; }
    .act-badge { padding: 4px 10px; border-radius: 12px; font-size: 0.8em; font-weight: 600; letter-spacing: 0.5px; }
    .badge-signed { background-color: #FFF8E1; color: #D4AF37; border: 1px solid #D4AF37; }
    .badge-meeting { background-color: #ebf5fb; color: #3498db; border: 1px solid #3498db; }
    .badge-recruit { background-color: #f4ecf7; color: #9b59b6; border: 1px solid #9b59b6; }
    .badge-default { background-color: #f8f9fa; color: #7f8c8d; border: 1px solid #bdc3c7; }
    .act-content { background-color: #f8f9fa; padding: 10px; border-radius: 8px; color: #555; font-size: 0.95em; line-height: 1.5; margin-top: 5px;}

    /* Golden Frame Rewards */
    .reward-card-premium { 
        background: linear-gradient(145deg, #ffffff, #fffdf5); 
        border: 2px solid #D4AF37; 
        border-radius: 16px; padding: 25px 20px; text-align: center; 
        box-shadow: 0 10px 25px rgba(212, 175, 55, 0.15); 
        transition: all 0.3s ease; height: 100%; position: relative; overflow: hidden; 
    }
    .reward-card-premium::before { content: ""; position: absolute; top: 0; left: 0; width: 100%; height: 8px; background: linear-gradient(90deg, #D4AF37, #FDC830, #D4AF37); }
    .reward-card-premium:hover { transform: translateY(-5px); box-shadow: 0 15px 35px rgba(212, 175, 55, 0.3); }
    .reward-icon { font-size: 3em; margin-bottom: 15px; display: block; filter: drop-shadow(0 2px 2px rgba(0,0,0,0.1)); }
    .reward-title-p { color: #D4AF37; font-size: 1.3em; font-weight: 800; margin-bottom: 10px; text-transform: uppercase; letter-spacing: 1.5px; }
    .reward-prize-p { color: #c0392b; font-size: 1.6em; font-weight: 900; margin-bottom: 10px; text-shadow: 1px 1px 0px rgba(0,0,0,0.05); }
    .reward-desc-p { color: #7f8c8d; font-size: 0.9em; line-height: 1.4; font-weight: 500; }
    .challenge-header-box { background: linear-gradient(to right, #FFF8E1, #FFFFFF); border-left: 6px solid #D4AF37; padding: 25px; border-radius: 12px; box-shadow: 0 4px 15px rgba(0,0,0,0.05); margin-bottom: 25px; }
</style>
""", unsafe_allow_html=True)

# Google Sheets 設定
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

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
                return ws
        except: return None
    return None

# --- 3. 防斷線資料庫讀取 ---
@st.cache_data(ttl=30)
def read_data(sheet_name):
    ws = get_sheet(sheet_name)
    schemas = {
        "users": ["username", "password", "role", "team", "recruit", "avatar", "last_read"],
        "monthly_fyc": ["id", "username", "month", "amount"],
        "activities": ["id", "username", "date", "type", "points", "note", "timestamp"]
    }
    expected_cols = schemas.get(sheet_name, [])
    
    for attempt in range(3): 
        if ws:
            try:
                data = ws.get_all_records()
                df = pd.DataFrame(data)
                if df.empty or not set(expected_cols).issubset(df.columns):
                    for col in expected_cols:
                        if col not in df.columns: df[col] = "" 
                    df = df[expected_cols] 
                
                if not df.empty:
                    st.session_state[f'backup_{sheet_name}'] = df 
                return df
            except Exception:
                time.sleep(1) 
                pass
                
    if f'backup_{sheet_name}' in st.session_state:
        return st.session_state[f'backup_{sheet_name}']
        
    return pd.DataFrame(columns=expected_cols)

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
            if not headers: 
                schemas = {
                    "monthly_fyc": ["id", "username", "month", "amount"],
                    "activities": ["id", "username", "date", "type", "points", "note", "timestamp"],
                    "users": ["username", "password", "role", "team", "recruit", "avatar", "last_read"]
                }
                headers = schemas.get(sheet_name, [])
                if headers: ws.append_row(headers)
            
            row_to_add = [str(data_dict.get(h, "")) for h in headers]
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
    except Exception as e: st.error(f"操作失敗: {e}")

def init_db_gs():
    
    try:
        ws = get_sheet("users")
        if ws:
            try: existing = ws.col_values(1)
            except: existing = []
            if not existing: 
                ws.append_row(["username", "password", "role", "team", "recruit", "avatar", "last_read"])
                existing = ["username"]
            defaults = [('Admin', 'admin123', 'Leader'), ('Tim', '1234', 'Member'), ('Oscar', '1234', 'Member'),
                        ('Catherine', '1234', 'Member'), ('Maggie', '1234', 'Member'), ('Wilson', '1234', 'Member')]
            for u in defaults:
                if u[0] not in existing:
                    url = f"https://ui-avatars.com/api/?name={u[0]}&background=d4af37&color=fff&size=128"
                    ws.append_row([u[0], u[1], u[2], "Tim Team", 0, url, ""])
                    clear_cache()
        for sn in ["monthly_fyc", "activities"]:
            ws_tmp = get_sheet(sn)
            if ws_tmp:
                try:
                    if not ws_tmp.row_values(1):
                        if sn == "monthly_fyc": ws_tmp.append_row(["id", "username", "month", "amount"])
                        if sn == "activities": ws_tmp.append_row(["id", "username", "date", "type", "points", "note", "timestamp"])
                except: pass
    except: pass

init_db_gs()

# --- 執行一次性的帳戶清理 (防 API 超標版) ---
def remove_departed_members():
    ws = get_sheet("users")
    if ws:
        try:
            st.info("正在讀取資料...")
            # 1. 一次性讀取所有資料 (1 API Call)
            records = ws.get_all_records()
            if not records:
                st.warning("表格無資料。")
                return
                
            df = pd.DataFrame(records)
            original_count = len(df)
            
            # 2. 在系統本地端 (Pandas) 直接過濾掉 Wilson 和 Catherine
            df_clean = df[~df['username'].isin(['Wilson', 'Catherine'])]
            new_count = len(df_clean)
            
            if original_count == new_count:
                st.success("系統中已經無 Wilson 或 Catherine 嘅資料啦！")
                return
            
            st.info(f"搵到 {original_count - new_count} 筆舊紀錄，準備一次過刪除...")
            
            # 3. 準備寫入的新資料 (必須包含 Headers)
            updated_data = [df_clean.columns.values.tolist()] + df_clean.values.tolist()
            
            # 4. 一次性清空並覆寫 (2 API Calls，絕對唔會超標)
            ws.clear()
            ws.update(updated_data)
            
            st.success(f"✅ 清理成功！乾淨俐落，已經將 Wilson 同 Catherine 徹底移出系統！")
            clear_cache() # 清除緩存以更新畫面
            
        except Exception as e:
            st.error(f"清理失敗: {e}")

# 取消註解下一行來執行刪除，執行成功後請務必將它重新註解或刪除！
# remove_departed_members()

# --- 4. Logic Functions ---
def login(u, p):
    df = read_data("users")
    if df.empty: return []
    df = df.drop_duplicates(subset=['username'], keep='first')
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
    except Exception: return None

def update_avt(u, i): 
    ws = get_sheet("users"); cell = ws.find(u)
    if cell: ws.update_cell(cell.row, ws.row_values(1).index("avatar") + 1, i); clear_cache()

def update_pw(u, p):
    ws = get_sheet("users"); cell = ws.find(u)
    if cell: ws.update_cell(cell.row, ws.row_values(1).index("password") + 1, p); clear_cache()

def add_act(u, d, t, n):
    pts = 8 if "出code" in t else 5 if "簽單" in t else 3 if "報考試" in t else 2 if "傾" in t else 1
    run_query_gs("INSERT", "activities", {"username": u, "date": str(d), "type": t, "points": pts, "note": n, "timestamp": str(datetime.datetime.now())})

def upd_fyc(u, m, a):
    df = read_data("monthly_fyc")
    if not df.empty: df['month'] = df['month'].astype(str).str.strip()
    exist = df[(df['username'] == u) & (df['month'] == str(m))]
    if not exist.empty: run_query_gs("UPDATE", "monthly_fyc", {"amount": a}, row_id=exist.iloc[0]['id'])
    else: run_query_gs("INSERT", "monthly_fyc", {"username": u, "month": str(m), "amount": a})

def upd_rec(u, a):
    ws = get_sheet("users"); cell = ws.find(u)
    if cell: ws.update_cell(cell.row, ws.row_values(1).index("recruit") + 1, a); clear_cache()

def del_act(id): run_query_gs("DELETE", "activities", row_id=id)

def upd_act(id, d, t, n):
    pts = 8 if "出code" in t else 5 if "簽單" in t else 3 if "報考試" in t else 2 if "傾" in t else 1
    run_query_gs("UPDATE", "activities", {"date": str(d), "type": t, "points": pts, "note": n}, row_id=id)

def get_act_by_id(id): return read_data("activities")[read_data("activities")['id'] == id].values.tolist()

def get_all_act():
    df = read_data("activities")
    if df.empty: return pd.DataFrame(columns=["id", "username", "date", "type", "points", "note", "timestamp"])
    df['date'] = pd.to_datetime(df['date'], errors='coerce')
    df = df.drop_duplicates(subset=['username', 'date', 'type', 'note'], keep='first')
    return df.sort_values(by='date', ascending=False)

def get_data(month=None):
    base_columns = ['username', 'team', 'recruit', 'avatar', 'fyc', 'Total_Score']
    users = read_data("users")
    if users.empty: return pd.DataFrame(columns=base_columns)
    
    users = users.drop_duplicates(subset=['username'], keep='first')
    users = users[users['role'] == 'Member'][['username', 'team', 'recruit', 'avatar']]
    if users.empty: return pd.DataFrame(columns=base_columns)

    fyc_df, act_df = read_data("monthly_fyc"), read_data("activities")
    
    if not fyc_df.empty and 'amount' in fyc_df.columns:
        fyc_df['month'] = fyc_df['month'].astype(str).str.strip()
        fyc_df['amount'] = pd.to_numeric(fyc_df['amount'], errors='coerce').fillna(0)
        if month == "Yearly": fyc = fyc_df.groupby('username')['amount'].sum().reset_index().rename(columns={'amount': 'fyc'})
        else: fyc = fyc_df[fyc_df['month'] == str(month)][['username', 'amount']].rename(columns={'amount': 'fyc'})
    else: fyc = pd.DataFrame(columns=['username', 'fyc'])

    if not act_df.empty and 'points' in act_df.columns:
        act_df['points'] = pd.to_numeric(act_df['points'], errors='coerce').fillna(0)
        act = act_df.groupby('username')['points'].sum().reset_index().rename(columns={'points': 'Total_Score'})
    else: act = pd.DataFrame(columns=['username', 'Total_Score'])
    
    df = pd.merge(users, fyc, on='username', how='left').fillna(0)
    df = pd.merge(df, act, on='username', how='left').fillna(0)
    
    df['fyc'] = pd.to_numeric(df['fyc'], errors='coerce').fillna(0).astype(float)
    df['Total_Score'] = pd.to_numeric(df['Total_Score'], errors='coerce').fillna(0).astype(int)
    df['recruit'] = pd.to_numeric(df['recruit'], errors='coerce').fillna(0).astype(int)
    
    return df

def get_q1_data():
    users = read_data("users")
    if users.empty: return pd.DataFrame()
    users = users.drop_duplicates(subset=['username'], keep='first')
    users = users[users['role'] == 'Member'][['username', 'avatar']]
    fyc_df = read_data("monthly_fyc")
    if not fyc_df.empty:
        fyc_df['month'] = fyc_df['month'].astype(str).str.strip()
        fyc_df['amount'] = pd.to_numeric(fyc_df['amount'], errors='coerce').fillna(0)
        q1 = fyc_df[fyc_df['month'].isin(['2026-01', '2026-02', '2026-03'])]
        q1_sum = q1.groupby('username')['amount'].sum().reset_index().rename(columns={'amount': 'q1_total'})
        return pd.merge(users, q1_sum, on='username', how='left').fillna(0)
    return pd.DataFrame(columns=['username', 'q1_total'])

# --- 🔥 FIX: 強制安全轉換 Points 為數字，修復「上週無人開工」Bug 🔥 ---
def get_last_week_data():
    today = datetime.date.today()
    current_week_monday = today - datetime.timedelta(days=today.weekday())
    start = current_week_monday - datetime.timedelta(days=7) # 上週一
    end = start + datetime.timedelta(days=6) # 上週日
    
    users = read_data("users")
    if users.empty: return pd.DataFrame(columns=['username', 'wk_score', 'wk_count']), start, end
    users = users.drop_duplicates(subset=['username'], keep='first')
    users = users[users['role'] == 'Member'][['username', 'avatar']]
    
    act_df = read_data("activities")
    stats = pd.DataFrame(columns=['username', 'wk_score', 'wk_count'])
    
    if not act_df.empty:
        act_df['date'] = pd.to_datetime(act_df['date'], errors='coerce').dt.date
        # 這是關鍵修復：保證 points 變為純數字，讓系統能正確加總！
        act_df['points'] = pd.to_numeric(act_df['points'], errors='coerce').fillna(0).astype(int)
        
        last_week_acts = act_df[(act_df['date'] >= start) & (act_df['date'] <= end)]
        if not last_week_acts.empty:
            stats = last_week_acts.groupby('username').agg(
                wk_score=('points', 'sum'),
                wk_count=('points', 'count')
            ).reset_index()
            
    return pd.merge(users, stats, on='username', how='left').fillna(0), start, end

# --- FIX: 同樣修復本週數據的 Points 加總 ---
def get_weekly_data():
    today = datetime.date.today()
    start = today - datetime.timedelta(days=today.weekday())
    users = read_data("users")
    if users.empty: return pd.DataFrame(), start, today
    users = users.drop_duplicates(subset=['username'], keep='first')
    users = users[users['role'] == 'Member'][['username', 'avatar']]
    act_df = read_data("activities")
    stats = pd.DataFrame(columns=['username', 'wk_score', 'wk_count'])
    
    if not act_df.empty:
        act_df['date'] = pd.to_datetime(act_df['date'], errors='coerce').dt.date
        act_df['points'] = pd.to_numeric(act_df['points'], errors='coerce').fillna(0).astype(int)
        this_week = act_df[act_df['date'] >= start]
        if not this_week.empty:
            stats = this_week.groupby('username').agg(
                wk_score=('points', 'sum'),
                wk_count=('points', 'count')
            ).reset_index()
            
    return pd.merge(users, stats, on='username', how='left').fillna(0), start, today

# --- Notification Logic ---
def update_last_read_time(username):
    try:
        ws = get_sheet("users"); cell = ws.find(username)
        if cell:
            headers = ws.row_values(1)
            if "last_read" in headers: ws.update_cell(cell.row, headers.index("last_read") + 1, str(datetime.datetime.now())); clear_cache()
    except: pass

@st.dialog("🔥 團隊最新戰報 🔥")
def show_notification_modal(new_activities, current_user):
    st.markdown(f"**Hi {current_user}，你不在的時候，團隊發生了以下動態：**")
    for index, row in new_activities.iterrows():
        act_time = pd.to_datetime(row['timestamp']).strftime('%m/%d %H:%M') if row['timestamp'] else row['date']
        st.info(f"**👤 {row['username']}** - {row['type']}\n\n📄 {row['note']}\n\n🕒 *{act_time}*")
    st.markdown("---")
    if st.button("收到 / OK (我知道了)", type="primary", use_container_width=True):
        update_last_read_time(current_user); st.rerun()

def check_notifications(current_user):
    users_df = read_data("users"); act_df = read_data("activities")
    if users_df.empty or act_df.empty: return
    user_record = users_df[users_df['username'] == current_user]
    if user_record.empty: return
    last_read_str = str(user_record.iloc[0]['last_read'])
    try: last_read = pd.to_datetime(last_read_str) if last_read_str and last_read_str != "" else pd.to_datetime("2020-01-01")
    except: last_read = pd.to_datetime("2020-01-01")
    if 'timestamp' not in act_df.columns: return
    act_df['timestamp_dt'] = pd.to_datetime(act_df['timestamp'], errors='coerce')
    new_activities = act_df[(act_df['timestamp_dt'] > last_read) & (act_df['username'] != current_user)]
    if not new_activities.empty: show_notification_modal(new_activities, current_user)

# --- Templates & Constants ---
TEMPLATE_SALES = "【客戶資料】\nName: \n講左3Q? 有咩feedback? \nFact Find 重點: \n\n【面談內容】\nSell左咩Plan? \n客戶反應/抗拒點: \n\n【下一步】\n下次見面日期: \nAction Items: "
TEMPLATE_RECRUIT = "【準增員資料】\nName: \n背景/現職: \n對現狀不滿 (Pain Points): \n對行業最大顧慮: \n\n【面談內容】\nSell 左咩 Vision?: \n有無邀請去Team Dinner / Recruitment Talk? \n\n【下一步】\n下次跟進日期: \nAction Items: "
TEMPLATE_NEWBIE = "【新人跟進】\n新人 Name: \n今日進度 (考牌/Training/出Code): \n遇到咩困難?: \nLeader 俾左咩建議?: \n\n【下一步】\nTarget: \n下次 Review 日期: "
ACTIVITY_TYPES = ["見面 (1分)", "傾保險 (2分)", "傾招募 (2分)", "新人報考試 (3分)", "簽單 (5分)", "新人出code (8分)"]

def get_activity_style(act_type):
    if "簽單" in act_type: return "card-signed", "badge-signed"
    if "見面" in act_type or "傾" in act_type: return "card-meeting", "badge-meeting"
    if "招募" in act_type or "新人" in act_type: return "card-recruit", "badge-recruit"
    return "card-admin", "badge-default"

# --- UI Layout ---
if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False

if not st.session_state['logged_in']:
    c1, c2, c3 = st.columns([1,1.5,1])
    with c2:
        st.markdown("<br><br>", unsafe_allow_html=True)
        with st.container():
            st.markdown("<div style='text-align: center;'><h1>🦁 TIM TEAM 2026</h1></div>", unsafe_allow_html=True)
            st.markdown("""<div style='background-color: #ffffff; padding: 20px; border-radius: 10px; border: 1px solid #C5A028; text-align: center; margin-bottom: 20px; box-shadow: 0 4px 10px rgba(0,0,0,0.05);'><h2 style='color: #C5A028 !important; margin:0;'>M + 2</h2><h3 style='color: #4A4A4A !important; margin:5px 0 15px 0;'>= 百萬年薪之路 💰</h3><div style='margin-top: 15px; padding-top: 10px; border-top: 1px dashed #ddd;'><span style='color: #666; font-size: 0.9em;'>2027 MDRT Requirement:</span><br><strong style='color: #D4AF37; font-size: 1.3em;'>HK$ 512,800</strong></div></div>""", unsafe_allow_html=True)
            u = st.text_input("Username", placeholder="e.g., Tim")
            p = st.text_input("Password", type="password", placeholder="••••••")
            if st.button("🚀 LOGIN", use_container_width=True):
                d = login(u, p)
                if d:
                    st.session_state.update({'logged_in':True, 'user':d[0][0], 'role':d[0][2], 'avatar':d[0][5]})
                    st.toast(f"Welcome back, {d[0][0]}!", icon="🦁"); st.rerun()
                else: st.toast("Login Failed", icon="❌")
else:
    check_notifications(st.session_state['user'])
    with st.sidebar:
        st.markdown("<br>", unsafe_allow_html=True)
        c_avt, c_txt = st.columns([1, 2])
        with c_avt: st.image(st.session_state.get('avatar',''), width=80)
        with c_txt: 
            st.markdown(f"<h3 style='margin:0; color:#C5A028 !important;'>{st.session_state['user']}</h3>", unsafe_allow_html=True)
            st.caption(f"{st.session_state['role']} | TIM TEAM")
        st.divider()
        menu = st.radio("MAIN MENU", ["📊 Dashboard 團隊報表", "📝 Check-in 打卡", "⚖️ Challenge 獎罰", "🏆 Year Goal 年度挑戰", "🤝 Recruit 招募龍虎榜", "📅 Monthly 業績表", "👤 Profile 設定"], label_visibility="collapsed")
        st.markdown("<br>"*3, unsafe_allow_html=True)
        if st.button("🔒 Logout", use_container_width=True, type="secondary"): st.session_state['logged_in'] = False; st.rerun()

    # --- 頁面路由 ---
    if "Dashboard" in menu:
        st.markdown(f"## 📊 {st.session_state['user']}, Let's Go MDRT!")
        if st.session_state['role'] == 'Leader':
            with st.container(border=True):
                st.markdown("### 📢 每週戰報生成器 (Admin Only)")
                if st.button("📝 生成上週結算戰報"):
                    wk_df, start, end = get_last_week_data()
                    max_score = wk_df['wk_score'].max() if not wk_df.empty else 0
                    winners = wk_df[wk_df['wk_score'] == max_score] if not wk_df.empty and max_score > 0 else pd.DataFrame()
                    losers = wk_df[wk_df['wk_count'] < 3] if not wk_df.empty else pd.DataFrame()
                    penalty_total = len(losers) * 100
                    prize_per_winner = penalty_total / len(winners) if penalty_total > 0 and not winners.empty else 100 / len(winners) if not winners.empty else 0
                    
                    report = f"📅 *【TIM TEAM 上週戰報 ({start} ~ {end})】* 🦁\n\n"
                    if max_score > 0 and not winners.empty:
                        report += f"🏆 *上週 MVP (獨得獎金 ${int(prize_per_winner)}):*\n"
                        for i, w in winners.iterrows(): report += f"👑 *{w['username']}* ({int(w['wk_score'])}分)\n"
                        report += f"_多謝 {len(losers)} 位同事贊助獎金池！_\n\n" if penalty_total > 0 else "_全員達標！Tim 自掏 $100 請飲茶！_\n\n"
                    else: report += "⚠️ *上週全軍覆沒？* 無人開工？\n\n"
                    
                    if not losers.empty:
                        report += f"💸 *【罰款名單 - 每人 $100】*\n_活動量不足 3 次，請自覺 PayMe 俾 Winner！_\n"
                        for i, l in losers.iterrows(): report += f"❌ {l['username']} (得 {int(l['wk_count'])} 次)\n"
                    else: report += "✅ *上週無人罰款！Excellent！*\n"
                    
                    report += "\n📊 *詳細戰況：*\n"
                    if not wk_df.empty:
                        for i, row in wk_df.sort_values(by='wk_score', ascending=False).iterrows():
                            report += f"{row['username']}: {int(row['wk_score'])}分 ({int(row['wk_count'])}次)\n"
                    report += "\n🚀 *新一週由零開始，大家加油！*"
                    st.code(report)
                    st.link_button("📤 Send to WhatsApp", f"https://wa.me/?text={urllib.parse.quote(report)}")

        df = get_data("Yearly")
        c1, c2, c3 = st.columns(3)
        c1.metric("💰 Team FYC", f"${df['fyc'].sum():,.0f}"); c2.metric("👥 Recruits", int(df['recruit'].sum())); c3.metric("🔥 Activities", int(df['Total_Score'].sum()))
        st.markdown("### 🏆 Leaderboard")
        mdrt_target = 512800
        df['mdrt_fraction'] = df['fyc'].apply(lambda x: f"${x:,.0f} / ${mdrt_target:,.0f}")
        
        # 🔥 FIX 4: 修正百分比算法 (* 100)，解決顯示 0.1% 的 Bug
        df['mdrt_percent'] = (df['fyc'] / mdrt_target) * 100
        df_sorted = df.sort_values(by='fyc', ascending=False)
        
        st.dataframe(df_sorted[['avatar', 'username', 'mdrt_fraction', 'mdrt_percent', 'recruit', 'Total_Score']],
            column_config={
                "avatar": st.column_config.ImageColumn("Avatar", width="medium"),
                "username": st.column_config.TextColumn("Name", width="small"),
                "mdrt_fraction": st.column_config.TextColumn("MDRT 進度 (實數)"),
                "mdrt_percent": st.column_config.ProgressColumn("MDRT %", format="%.1f%%", min_value=0, max_value=100),
                "recruit": st.column_config.NumberColumn("Recruit", format="%d"),
                "Total_Score": st.column_config.NumberColumn("Activity", format="%d")
            }, use_container_width=True, hide_index=True)

        if st.session_state['role'] == 'Leader':
            with st.expander("⚙️ 業績/招募管理 (Admin Only)"):
                c_a, c_b, c_c = st.columns(3)
                user_list = df['username'].unique().tolist()
                tgt = c_a.selectbox("User", user_list); mth = c_b.selectbox("Month", [f"2026-{i:02d}" for i in range(1,13)]); amt = c_c.number_input("Amount", step=1000)
                if st.button("Save FYC"): upd_fyc(tgt, mth, amt); st.toast("Saved!", icon="✅"); st.rerun()
                st.divider()
                c_d, c_e = st.columns(2)
                tgt_r = c_d.selectbox("User", user_list, key="r1"); rec = c_e.number_input("Recruits", step=1)
                if st.button("Save Recruit"): upd_rec(tgt_r, rec); st.toast("Saved!", icon="✅"); st.rerun()

    elif "Check-in" in menu:
        st.markdown("## 📝 Activity Center")
        tab_new, tab_hist = st.tabs(["✍️ 立即打卡 (Check-in)", "👀 團隊動態 (Team Feed)"])
        
        with tab_new:
            # 🔥 採用 Form 杜絕連按 Double Submit 的問題
            with st.form("checkin_form", clear_on_submit=True):
                with st.container(border=True):
                    c_date, c_type = st.columns([1, 1])
                    with c_date: d = st.date_input("📅 日期", value=datetime.date.today())
                    with c_type: t = st.selectbox("📌 活動種類", ACTIVITY_TYPES)
                    note_val = TEMPLATE_RECRUIT if "招募" in t else TEMPLATE_NEWBIE if "新人" in t else TEMPLATE_SALES
                    n = st.text_area("📝 內容詳情 / 備註", value=note_val, height=180, help="請詳細記錄客戶反應或下一步行動")
                    st.markdown("<br>", unsafe_allow_html=True)
                    submitted = st.form_submit_button("🚀 提交打卡 (Submit)", type="primary")
                    if submitted: 
                        add_act(st.session_state['user'], d, t, n)
                        st.toast("提交成功！", icon="✅")

        with tab_hist:
            st.markdown("### 📜 Timeline")
            users_df = read_data("users").drop_duplicates(subset=['username'], keep='first')
            user_options = users_df['username'].unique() if not users_df.empty else []
            filter_user = st.multiselect("🔍 篩選同事 (Filter)", options=user_options)
            
            all_acts = get_all_act()
            if not all_acts.empty:
                users_mini = users_df[['username', 'avatar']]
                all_acts = pd.merge(all_acts, users_mini, on='username', how='left')
                display_df = all_acts[all_acts['username'].isin(filter_user)] if filter_user else all_acts
                
                for idx, row in display_df.iterrows():
                    act_date = pd.to_datetime(row['date']).strftime('%Y-%m-%d')
                    act_time = pd.to_datetime(row['timestamp']).strftime('%H:%M') if row['timestamp'] else ""
                    avatar_url = row['avatar'] if isinstance(row['avatar'], str) and row['avatar'].startswith('http') else "https://ui-avatars.com/api/?background=random&color=fff&name=" + row['username']
                    card_class, badge_class = get_activity_style(row['type'])
                    
                    st.markdown(f"""
                    <div class="activity-card {card_class}">
                        <div class="act-header">
                            <div class="act-user-info">
                                <img src="{avatar_url}" class="act-avatar">
                                <div><div class="act-name">{row['username']}</div><div class="act-time">{act_date} {act_time}</div></div>
                            </div>
                            <div class="act-badge {badge_class}">{row['type']}</div>
                        </div>
                        <div class="act-content">{row['note'].replace(chr(10), '<br>')}</div>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.info("暫無動態，快啲去 Check-in！")

    elif "Challenge" in menu:
        df, start, end = get_weekly_data()
        st.markdown(f"## ⚖️ Winner Takes All ({start} ~ {end})")
        st.markdown("""<div class="challenge-header-box"><div class="challenge-title">📜 詳細遊戲規則 (Game Rules)：</div><ul class="challenge-rules"><li><strong>結算時間：</strong> 逢星期日晚 23:59 系統自動結算。</li><li><strong>罰款準則：</strong> 每週活動量 (Count) <strong>少於 3 次</strong> 者，需罰款 <strong>$100</strong>。</li><li><strong>獎金歸屬：</strong> 所有罰款注入獎金池，由 <strong>最高分 (Score)</strong> 者獨得。</li></ul></div>""", unsafe_allow_html=True)
        if not df.empty:
            max_score = df['wk_score'].max(); winners = df[df['wk_score'] == max_score] if max_score > 0 else pd.DataFrame()
            pool = len(df[df['wk_count'] < 3]) * 100
            st.markdown(f"### 🏆 Prize Pool: <span style='color:#C5A028'>${pool if pool > 0 else 100}</span>", unsafe_allow_html=True)
            if not winners.empty:
                cols = st.columns(len(winners)); 
                for idx, row in winners.reset_index().iterrows(): cols[idx].image(row['avatar'], width=60); cols[idx].caption(f"👑 {row['username']}")
            st.dataframe(df[['avatar', 'username', 'wk_score', 'wk_count']].sort_values(by='wk_score', ascending=False),
                         column_config={"avatar": st.column_config.ImageColumn("", width="small"), "wk_score": st.column_config.ProgressColumn("Score", format="%d", max_value=max(10, max_score))}, use_container_width=True, hide_index=True)

    elif "Year Goal" in menu:
        st.markdown("## 🏆 2026 年度挑戰")
        q1_df = get_q1_data(); q1_target = 88000
        st.markdown("""<div class="challenge-header-box"><div class="challenge-title">🔥 Q1 88000 Challenge (1/1 - 31/3)</div><p class="challenge-rules"><strong>目標：</strong> 第一季 (Q1) 累積 FYC 達 <strong>HK$ 88,000</strong>。<br>這是通往 MDRT 的第一張入場券，必須拿下！</p></div>""", unsafe_allow_html=True)
        if not q1_df.empty:
            st.dataframe(
                q1_df[['avatar', 'username', 'q1_total']].sort_values(by='q1_total', ascending=False),
                column_config={
                    "avatar": st.column_config.ImageColumn("Avatar", width="medium"),
                    "username": st.column_config.TextColumn("Name", width="small"),
                    "q1_total": st.column_config.ProgressColumn("Q1 Progress ($88k)", format="$%d", min_value=0, max_value=88000, width="medium"),
                }, use_container_width=True, hide_index=True
            )
        else: st.info("暫無 Q1 業績數據，加油！")
        st.divider(); st.markdown("### 🎁 年度獎賞計劃")
        c1, c2 = st.columns(2)
        with c1: st.markdown('<div class="reward-card-premium"><span class="reward-icon">🚀</span><p class="reward-title-p">1st MDRT</p><p class="reward-prize-p">$20,000 Cash</p><p class="reward-desc-p">首位完成 $512,800 FYC 者獨得</p></div>', unsafe_allow_html=True)
        with c2: st.markdown('<div class="reward-card-premium"><span class="reward-icon">👑</span><p class="reward-title-p">Top FYC 冠軍</p><p class="reward-prize-p">$10,000 Cash</p><p class="reward-desc-p">全年業績最高者 (需 Min. 180,000 FYC)</p></div>', unsafe_allow_html=True)
        st.write(""); c3, c4 = st.columns(2)
        with c3: st.markdown('<div class="reward-card-premium"><span class="reward-icon">✈️</span><p class="reward-title-p">招募冠軍</p><p class="reward-prize-p">雙人來回機票</p><p class="reward-desc-p">全年招募人數最多者 (需 Min. 2人)</p></div>', unsafe_allow_html=True)
        with c4: st.markdown('<div class="reward-card-premium"><span class="reward-icon">🍽️</span><p class="reward-title-p">Monthly Star</p><p class="reward-prize-p">Tim 請食飯</p><p class="reward-desc-p">單月 FYC 最高者 (需 Min. $20k)</p></div>', unsafe_allow_html=True)

    elif "Recruit" in menu:
        st.markdown("## 🤝 Recruit 龍虎榜")
        df = get_data("Yearly")
        if not df.empty:
            df['recruit'] = pd.to_numeric(df['recruit'], errors='coerce').fillna(0).astype(int)
            df['avatar'] = df['avatar'].astype(str)
            st.dataframe(
                df[['avatar', 'username', 'recruit']].sort_values(by='recruit', ascending=False),
                column_config={
                    "avatar": st.column_config.ImageColumn("Avatar", width="small"),
                    "username": st.column_config.TextColumn("Agent"),
                    "recruit": st.column_config.ProgressColumn("Recruits (Headcount)", format="%d", min_value=0, max_value=10)
                }, use_container_width=True, hide_index=True
            )
        else: st.info("暫無招募數據，大家加油！")

    elif "Monthly" in menu:
        st.markdown("## 📅 Monthly FYC 龍虎榜")
        m = st.selectbox("Month", [f"2026-{i:02d}" for i in range(1,13)])
        df = get_data(month=m)
        if not df.empty:
            df['fyc'] = pd.to_numeric(df['fyc'], errors='coerce').fillna(0).astype(float)
            df['avatar'] = df['avatar'].astype(str)
            max_fyc = df['fyc'].max() if df['fyc'].max() > 0 else 50000
            st.dataframe(
                df[['avatar', 'username', 'fyc']].sort_values(by='fyc', ascending=False),
                column_config={
                    "avatar": st.column_config.ImageColumn("Avatar", width="small"),
                    "username": st.column_config.TextColumn("Agent"),
                    "fyc": st.column_config.ProgressColumn("FYC Achievement", format="$%d", min_value=0, max_value=max_fyc)
                }, use_container_width=True, hide_index=True
            )
        else: st.info("本月暫無數據")

    elif "Profile" in menu:
        st.markdown("## 👤 User Profile")
        col1, col2 = st.columns([1, 2])
        with col1: st.image(st.session_state.get('avatar'), width=150)
        with col2:
            st.markdown(f"### {st.session_state['user']}"); st.markdown(f"**Role:** {st.session_state['role']}")
            with st.expander("🔐 Change Password"):
                new_pw = st.text_input("New Password", type="password")
                if st.button("Update Password"): update_pw(st.session_state['user'], new_pw); st.toast("Password Updated!", icon="✅")
            with st.expander("🖼️ Change Avatar"):
                uploaded_file = st.file_uploader("Upload Image", type=['jpg', 'png', 'jpeg'])
                if uploaded_file is not None:
                    if st.button("Upload"):
                        img_str = proc_img(uploaded_file)
                        if img_str: update_avt(st.session_state['user'], img_str); st.session_state['avatar'] = img_str; st.toast("Avatar Updated!", icon="✅"); st.rerun()
