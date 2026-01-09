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
import plotly.graph_objects as go
import plotly.express as px
from google.oauth2.service_account import Credentials
from gspread.exceptions import WorksheetNotFound

# --- 1. 系統設定 ---
st.set_page_config(
    page_title="TIM TEAM 2026 - 保險精英系統", 
    page_icon="🦁", 
    layout="wide", 
    initial_sidebar_state="expanded",
    menu_items={
        'Get Help': 'https://www.example.com',
        'Report a bug': 'https://www.example.com',
        'About': '# TIM TEAM 保險精英系統 2026\n### 百萬年薪之路'
    }
)

# --- 專業級CSS美化 ---
st.markdown("""
<style>
    /* 全局專業主題 */
    [data-testid="stAppViewContainer"] { 
        background: linear-gradient(135deg, #f8f9fa 0%, #ffffff 100%) !important; 
    }
    
    [data-testid="stSidebar"] { 
        background: linear-gradient(180deg, #1a2b3c 0%, #2c3e50 100%) !important;
        border-right: 3px solid #D4AF37 !important;
        box-shadow: 5px 0 15px rgba(0,0,0,0.1);
    }
    
    /* 專業字體與標題 */
    h1, h2, h3, h4, h5, h6 { 
        font-family: 'Helvetica Neue', 'Microsoft YaHei', sans-serif !important;
        font-weight: 700 !important;
        letter-spacing: -0.5px;
    }
    
    h1 { 
        color: #1a2b3c !important;
        background: linear-gradient(90deg, #D4AF37, #FFD700);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-shadow: 2px 2px 4px rgba(0,0,0,0.1);
        border-bottom: 3px solid #D4AF37;
        padding-bottom: 10px;
        margin-bottom: 20px;
    }
    
    h2 { color: #2c3e50 !important; border-left: 4px solid #D4AF37; padding-left: 15px; }
    h3 { color: #34495e !important; }
    
    /* 專業卡片設計 */
    .professional-card {
        background: white;
        border-radius: 16px;
        padding: 25px;
        margin: 15px 0;
        box-shadow: 0 8px 30px rgba(0,0,0,0.08);
        border: 1px solid rgba(212, 175, 55, 0.2);
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        position: relative;
        overflow: hidden;
    }
    
    .professional-card::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        width: 5px;
        height: 100%;
        background: linear-gradient(180deg, #D4AF37, #FFD700);
    }
    
    .professional-card:hover {
        transform: translateY(-5px);
        box-shadow: 0 15px 35px rgba(212, 175, 55, 0.15);
    }
    
    /* 指標卡片 */
    .metric-card {
        background: linear-gradient(135deg, #ffffff 0%, #f8f9fa 100%);
        border-radius: 12px;
        padding: 20px;
        border: 1px solid #e0e0e0;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
        text-align: center;
    }
    
    .metric-value {
        font-size: 2.2em;
        font-weight: 800;
        color: #2c3e50;
        margin: 10px 0;
    }
    
    .metric-label {
        font-size: 0.9em;
        color: #7f8c8d;
        text-transform: uppercase;
        letter-spacing: 1px;
    }
    
    /* 按鈕美化 */
    div.stButton > button {
        background: linear-gradient(135deg, #D4AF37 0%, #B38F21 100%) !important;
        color: white !important;
        border: none !important;
        border-radius: 10px !important;
        padding: 12px 24px !important;
        font-weight: 600 !important;
        letter-spacing: 0.5px !important;
        box-shadow: 0 4px 15px rgba(212, 175, 55, 0.3) !important;
        transition: all 0.3s ease !important;
    }
    
    div.stButton > button:hover {
        transform: translateY(-2px) !important;
        box-shadow: 0 6px 20px rgba(212, 175, 55, 0.4) !important;
    }
    
    /* 輸入框美化 */
    .stTextInput > div > div > input,
    .stTextArea > div > div > textarea,
    .stSelectbox > div > div,
    .stDateInput > div > div > input {
        background: #ffffff !important;
        border: 2px solid #e0e0e0 !important;
        border-radius: 10px !important;
        padding: 10px 15px !important;
        font-size: 14px !important;
        transition: all 0.3s !important;
    }
    
    .stTextInput > div > div > input:focus,
    .stTextArea > div > div > textarea:focus {
        border-color: #D4AF37 !important;
        box-shadow: 0 0 0 3px rgba(212, 175, 55, 0.1) !important;
    }
    
    /* 側邊欄美化 */
    .sidebar-user-info {
        background: linear-gradient(135deg, rgba(212, 175, 55, 0.1), rgba(255, 215, 0, 0.05));
        border-radius: 15px;
        padding: 20px;
        margin: 20px 0;
        text-align: center;
        border: 1px solid rgba(212, 175, 55, 0.2);
    }
    
    .sidebar-avatar {
        width: 80px;
        height: 80px;
        border-radius: 50%;
        border: 3px solid #D4AF37;
        margin: 0 auto 15px;
        object-fit: cover;
        box-shadow: 0 4px 10px rgba(0,0,0,0.1);
    }
    
    /* 表格美化 */
    .dataframe {
        border-radius: 10px !important;
        overflow: hidden !important;
    }
    
    .dataframe thead tr {
        background: linear-gradient(90deg, #2c3e50, #34495e) !important;
        color: white !important;
    }
    
    /* 進度條美化 */
    .stProgress > div > div > div > div {
        background: linear-gradient(90deg, #D4AF37, #FFD700) !important;
    }
    
    /* 徽章設計 */
    .badge-premium {
        display: inline-block;
        padding: 4px 12px;
        background: linear-gradient(135deg, #D4AF37, #FFD700);
        color: white;
        border-radius: 20px;
        font-size: 0.8em;
        font-weight: 600;
        margin-left: 10px;
    }
    
    /* 時間線設計 */
    .timeline-item {
        padding: 15px 20px;
        margin: 10px 0;
        background: white;
        border-left: 4px solid #D4AF37;
        border-radius: 0 8px 8px 0;
        box-shadow: 0 3px 10px rgba(0,0,0,0.05);
    }
    
    /* 獎牌樣式 */
    .medal-gold {
        color: #FFD700;
        font-size: 1.5em;
        margin-right: 8px;
    }
    
    .medal-silver {
        color: #C0C0C0;
        font-size: 1.5em;
        margin-right: 8px;
    }
    
    .medal-bronze {
        color: #CD7F32;
        font-size: 1.5em;
        margin-right: 8px;
    }
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
        else: 
            return None
        creds = Credentials.from_service_account_info(key_dict, scopes=SCOPES)
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"Google Sheets連接失敗: {str(e)}")
        return None

def get_sheet(sheet_name):
    client = get_gs_client()
    if client:
        try:
            sh = client.open("tim_team_db")
            try: 
                return sh.worksheet(sheet_name)
            except WorksheetNotFound:
                ws = sh.add_worksheet(title=sheet_name, rows=1000, cols=10)
                if sheet_name == "users": 
                    ws.append_row(["username", "password", "role", "team", "recruit", "avatar", "join_date", "phone", "email"])
                elif sheet_name == "monthly_fyc": 
                    ws.append_row(["id", "username", "month", "amount", "policy_count", "avg_premium"])
                elif sheet_name == "activities": 
                    ws.append_row(["id", "username", "date", "type", "points", "note", "client_name", "status"])
                return ws
        except Exception as e:
            st.error(f"工作表訪問失敗: {str(e)}")
            return None
    return None

# --- 3. 數據庫操作 ---
@st.cache_data(ttl=5)
def read_data(sheet_name):
    ws = get_sheet(sheet_name)
    
    schemas = {
        "users": ["username", "password", "role", "team", "recruit", "avatar", "join_date", "phone", "email"],
        "monthly_fyc": ["id", "username", "month", "amount", "policy_count", "avg_premium"],
        "activities": ["id", "username", "date", "type", "points", "note", "client_name", "status"]
    }
    
    expected_cols = schemas.get(sheet_name, [])

    if ws:
        try:
            data = ws.get_all_records()
            df = pd.DataFrame(data)
            
            if df.empty or not set(expected_cols).issubset(df.columns):
                df = pd.DataFrame(columns=expected_cols)
                
            return df
        except Exception as e:
            st.error(f"讀取{sheet_name}失敗: {str(e)}")
    
    return pd.DataFrame(columns=expected_cols)

def clear_cache(): 
    st.cache_data.clear()

def run_query_gs(action, sheet_name, data_dict=None, row_id=None):
    ws = get_sheet(sheet_name)
    if not ws: 
        return False
    
    try:
        if action == "INSERT":
            if sheet_name in ["activities", "monthly_fyc"]:
                records = ws.get_all_records()
                new_id = 1
                if records:
                    ids = [int(r['id']) for r in records if str(r['id']).isdigit()]
                    if ids: 
                        new_id = max(ids) + 1
                data_dict['id'] = new_id
            
            headers = ws.row_values(1)
            row_to_add = [data_dict.get(h, "") for h in headers]
            ws.append_row(row_to_add)
            return True
            
        elif action == "UPDATE":
            cell = ws.find(str(row_id))
            if cell:
                headers = ws.row_values(1)
                for col, val in data_dict.items():
                    if col in headers: 
                        ws.update_cell(cell.row, headers.index(col) + 1, val)
                return True
            
        elif action == "DELETE":
            cell = ws.find(str(row_id))
            if cell: 
                ws.delete_rows(cell.row)
                return True
                
        clear_cache()
    except Exception as e:
        st.error(f"操作失敗: {str(e)}")
    
    return False

# 初始化數據庫
def init_db_gs():
    ws = get_sheet("users")
    if ws:
        try: 
            existing = ws.col_values(1)
        except: 
            existing = []
        
        defaults = [
            ('Admin', 'admin123', 'Leader', 'Tim Team', 0, 'https://ui-avatars.com/api/?name=Admin&background=d4af37&color=fff&size=256', '2023-01-01', '9123 4567', 'admin@timteam.com'),
            ('Tim', '1234', 'Director', 'Tim Team', 5, 'https://ui-avatars.com/api/?name=Tim&background=2c3e50&color=fff&size=256', '2020-05-15', '9123 4568', 'tim@timteam.com'),
            ('Oscar', '1234', 'Senior Manager', 'Tim Team', 3, 'https://ui-avatars.com/api/?name=Oscar&background=27ae60&color=fff&size=256', '2021-03-10', '9123 4569', 'oscar@timteam.com'),
            ('Catherine', '1234', 'Manager', 'Tim Team', 2, 'https://ui-avatars.com/api/?name=Catherine&background=8e44ad&color=fff&size=256', '2022-08-22', '9123 4570', 'catherine@timteam.com'),
            ('Maggie', '1234', 'Associate', 'Tim Team', 1, 'https://ui-avatars.com/api/?name=Maggie&background=e74c3c&color=fff&size=256', '2023-11-05', '9123 4571', 'maggie@timteam.com'),
            ('Wilson', '1234', 'Associate', 'Tim Team', 0, 'https://ui-avatars.com/api/?name=Wilson&background=3498db&color=fff&size=256', '2024-01-20', '9123 4572', 'wilson@timteam.com'),
        ]
        
        if not existing:
            ws.append_row(["username", "password", "role", "team", "recruit", "avatar", "join_date", "phone", "email"])
            existing = ["username"]

        for user in defaults:
            if user[0] not in existing:
                ws.append_row(list(user))
                clear_cache()

init_db_gs()

# --- 4. 業務邏輯函數 ---
def login(u, p):
    df = read_data("users")
    if df.empty: 
        return []
    
    df['password'] = df['password'].astype(str)
    user = df[(df['username'] == u) & (df['password'] == str(p))]
    
    return user.values.tolist() if not user.empty else []

def process_image(file):
    try:
        image = Image.open(file)
        if image.mode in ("RGBA", "P"): 
            image = image.convert("RGB")
        
        # 創建圓形頭像
        size = (200, 200)
        image = image.resize(size, Image.Resampling.LANCZOS)
        
        # 創建圓形遮罩
        mask = Image.new('L', size, 0)
        draw = ImageDraw.Draw(mask)
        draw.ellipse((0, 0) + size, fill=255)
        
        output = Image.new('RGB', size, (255, 255, 255))
        output.paste(image, (0, 0), mask)
        
        img_byte_arr = io.BytesIO()
        output.save(img_byte_arr, format='PNG', quality=95)
        
        return f"data:image/png;base64,{base64.b64encode(img_byte_arr.getvalue()).decode()}"
    except Exception as e:
        st.error(f"圖片處理失敗: {str(e)}")
        return None

def update_avatar(username, image_str):
    ws = get_sheet("users")
    cell = ws.find(username)
    if cell: 
        ws.update_cell(cell.row, ws.row_values(1).index("avatar") + 1, image_str)
        clear_cache()

def update_password(username, new_password):
    ws = get_sheet("users")
    cell = ws.find(username)
    if cell: 
        ws.update_cell(cell.row, ws.row_values(1).index("password") + 1, new_password)
        clear_cache()

def add_activity(username, date, activity_type, note, client_name="", status="進行中"):
    points_mapping = {
        "見面 (1分)": 1,
        "傾保險 (2分)": 2,
        "傾招募 (2分)": 2,
        "新人報考試 (3分)": 3,
        "簽單 (5分)": 5,
        "新人出code (8分)": 8
    }
    
    points = points_mapping.get(activity_type, 1)
    
    data = {
        "username": username,
        "date": str(date),
        "type": activity_type,
        "points": points,
        "note": note,
        "client_name": client_name,
        "status": status
    }
    
    success = run_query_gs("INSERT", "activities", data)
    return success

def update_fyc(username, month, amount, policy_count=0, avg_premium=0):
    df = read_data("monthly_fyc")
    existing = df[(df['username'] == username) & (df['month'] == month)]
    
    data = {
        "username": username,
        "month": month,
        "amount": amount,
        "policy_count": policy_count,
        "avg_premium": avg_premium
    }
    
    if not existing.empty:
        success = run_query_gs("UPDATE", "monthly_fyc", data, row_id=existing.iloc[0]['id'])
    else:
        success = run_query_gs("INSERT", "monthly_fyc", data)
    
    return success

def get_user_stats(username):
    df_fyc = read_data("monthly_fyc")
    df_act = read_data("activities")
    
    stats = {
        "total_fyc": 0,
        "monthly_fyc": 0,
        "total_activities": 0,
        "total_points": 0,
        "policy_count": 0,
        "recruit_count": 0
    }
    
    if not df_fyc.empty:
        user_fyc = df_fyc[df_fyc['username'] == username]
        if not user_fyc.empty:
            stats["total_fyc"] = user_fyc['amount'].sum()
            current_month = datetime.datetime.now().strftime("%Y-%m")
            monthly = user_fyc[user_fyc['month'] == current_month]
            if not monthly.empty:
                stats["monthly_fyc"] = monthly['amount'].sum()
                stats["policy_count"] = monthly['policy_count'].sum()
    
    if not df_act.empty:
        user_act = df_act[df_act['username'] == username]
        if not user_act.empty:
            stats["total_activities"] = len(user_act)
            stats["total_points"] = user_act['points'].sum()
    
    return stats

def get_leaderboard_data(timeframe="monthly"):
    df_users = read_data("users")
    df_fyc = read_data("monthly_fyc")
    df_act = read_data("activities")
    
    if df_users.empty:
        return pd.DataFrame()
    
    # 過濾會員
    users = df_users[df_users['role'] != 'Admin'][['username', 'team', 'avatar']].copy()
    
    # 計算FYC
    if not df_fyc.empty:
        if timeframe == "monthly":
            current_month = datetime.datetime.now().strftime("%Y-%m")
            fyc_data = df_fyc[df_fyc['month'] == current_month]
        else:  # yearly
            fyc_data = df_fyc
        
        fyc_stats = fyc_data.groupby('username').agg({
            'amount': 'sum',
            'policy_count': 'sum'
        }).reset_index()
        fyc_stats.columns = ['username', 'fyc', 'policy_count']
    else:
        fyc_stats = pd.DataFrame(columns=['username', 'fyc', 'policy_count'])
    
    # 計算活動積分
    if not df_act.empty:
        act_stats = df_act.groupby('username').agg({
            'points': 'sum',
            'id': 'count'
        }).reset_index()
        act_stats.columns = ['username', 'activity_points', 'activity_count']
    else:
        act_stats = pd.DataFrame(columns=['username', 'activity_points', 'activity_count'])
    
    # 合併數據
    result = pd.merge(users, fyc_stats, on='username', how='left')
    result = pd.merge(result, act_stats, on='username', how='left')
    
    # 填充缺失值
    result['fyc'] = result['fyc'].fillna(0)
    result['policy_count'] = result['policy_count'].fillna(0)
    result['activity_points'] = result['activity_points'].fillna(0)
    result['activity_count'] = result['activity_count'].fillna(0)
    
    # 計算MDRT進度
    mdrt_target = 512800
    result['mdrt_percentage'] = (result['fyc'] / mdrt_target * 100).clip(upper=100)
    result['mdrt_display'] = result.apply(
        lambda x: f"${x['fyc']:,.0f} / ${mdrt_target:,.0f}", axis=1
    )
    
    return result.sort_values('fyc', ascending=False)

# --- 5. 模板和常量 ---
ACTIVITY_TYPES = [
    "見面 (1分)",
    "傾保險 (2分)",
    "傾招募 (2分)",
    "新人報考試 (3分)",
    "簽單 (5分)",
    "新人出code (8分)"
]

ACTIVITY_TEMPLATES = {
    "見面 (1分)": "【客戶資料】\n姓名: \n背景: \n需求分析: \n\n【會談重點】\n\n【下一步行動】",
    "傾保險 (2分)": "【客戶資料】\n姓名: \n現有保障分析: \n缺口識別: \n\n【方案建議】\n\n【客戶反應】\n\n【下一步】",
    "簽單 (5分)": "【客戶】\n【保單號碼】\n【計劃】\n【年繳保費】\n【佣金】\n【備註】",
    "傾招募 (2分)": "【準增員】\n姓名: \n現職: \n收入: \n興趣點: \n\n【跟進計劃】"
}

# --- 6. UI佈局 ---
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False

if not st.session_state['logged_in']:
    # 專業登入頁面
    col1, col2, col3 = st.columns([1, 1.5, 1])
    
    with col2:
        st.markdown("<br><br>", unsafe_allow_html=True)
        
        # 登入卡片
        with st.container():
            st.markdown("""
            <div style='text-align: center; margin-bottom: 30px;'>
                <h1 style='color: #D4AF37; margin-bottom: 10px;'>🦁 TIM TEAM</h1>
                <h3 style='color: #2c3e50; margin-top: 0;'>保險精英系統 2026</h3>
                <p style='color: #7f8c8d;'>百萬年薪之路 • 專業成就夢想</p>
            </div>
            """, unsafe_allow_html=True)
            
            # 登入表單卡片
            with st.container():
                st.markdown('<div class="professional-card">', unsafe_allow_html=True)
                
                username = st.text_input(
                    "👤 用戶名稱",
                    placeholder="請輸入用戶名",
                    key="login_username"
                )
                
                password = st.text_input(
                    "🔑 密碼",
                    type="password",
                    placeholder="請輸入密碼",
                    key="login_password"
                )
                
                col_btn1, col_btn2 = st.columns(2)
                with col_btn1:
                    if st.button("🚀 登入系統", use_container_width=True):
                        if username and password:
                            user_data = login(username, password)
                            if user_data:
                                st.session_state.update({
                                    'logged_in': True,
                                    'user': user_data[0][0],
                                    'role': user_data[0][2],
                                    'avatar': user_data[0][5],
                                    'team': user_data[0][3]
                                })
                                st.success(f"歡迎回來，{user_data[0][0]}！")
                                st.rerun()
                            else:
                                st.error("用戶名或密碼錯誤")
                        else:
                            st.warning("請輸入用戶名和密碼")
                
                with col_btn2:
                    if st.button("🔄 重置", use_container_width=True, type="secondary"):
                        st.rerun()
                
                st.markdown('</div>', unsafe_allow_html=True)
            
            # 系統簡介
            st.markdown("""
            <div style='margin-top: 30px; text-align: center; color: #7f8c8d; font-size: 0.9em;'>
                <p>📊 實時業績追蹤 • 🏆 精英排行榜 • 📈 成長分析</p>
                <p>🤝 團隊協作 • 🎯 目標管理 • 💰 佣金計算</p>
            </div>
            """, unsafe_allow_html=True)
else:
    # 主界面 - 側邊欄
    with st.sidebar:
        st.markdown("<br>", unsafe_allow_html=True)
        
        # 用戶信息卡片
        st.markdown('<div class="sidebar-user-info">', unsafe_allow_html=True)
        st.image(
            st.session_state.get('avatar', 'https://ui-avatars.com/api/?name=User&background=D4AF37&color=fff&size=150'),
            width=100,
            caption=""
        )
        st.markdown(f"### {st.session_state['user']}")
        st.markdown(f"**{st.session_state['role']}**")
        st.markdown(f"*{st.session_state.get('team', 'Tim Team')}*")
        st.markdown('</div>', unsafe_allow_html=True)
        
        st.divider()
        
        # 主菜單
        menu_options = {
            "📊 儀表板": "dashboard",
            "📝 活動記錄": "activities",
            "💰 業績管理": "performance",
            "🏆 排行榜": "leaderboard",
            "🎯 目標挑戰": "challenges",
            "👥 團隊管理": "team",
            "⚙️ 個人設置": "settings"
        }
        
        selected_menu = st.radio(
            "主菜單",
            list(menu_options.keys()),
            label_visibility="collapsed"
        )
        
        st.divider()
        
        # 快速統計
        if st.session_state['role'] != 'Admin':
            user_stats = get_user_stats(st.session_state['user'])
            st.markdown("### 📈 本月概況")
            col_s1, col_s2 = st.columns(2)
            with col_s1:
                st.metric("本月業績", f"${user_stats['monthly_fyc']:,.0f}")
            with col_s2:
                st.metric("活動積分", f"{user_stats['total_points']}")
        
        st.markdown("<br><br>", unsafe_allow_html=True)
        
        if st.button("🚪 登出系統", use_container_width=True, type="secondary"):
            st.session_state['logged_in'] = False
            st.rerun()
    
    # 主內容區
    menu_page = menu_options[selected_menu]
    
    if menu_page == "dashboard":
        st.markdown(f"# 👋 歡迎回來，{st.session_state['user']}！")
        st.markdown("### 📊 系統概覽")
        
        # 關鍵指標
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.markdown("""
            <div class="metric-card">
                <div class="metric-label">本月團隊業績</div>
                <div class="metric-value">$258,400</div>
                <div style="color: #27ae60; font-size: 0.9em;">↑ 12.5%</div>
            </div>
            """, unsafe_allow_html=True)
        
        with col2:
            st.markdown("""
            <div class="metric-card">
                <div class="metric-label">新增招募</div>
                <div class="metric-value">8</div>
                <div style="color: #27ae60; font-size: 0.9em;">↑ 2 人</div>
            </div>
            """, unsafe_allow_html=True)
        
        with col3:
            st.markdown("""
            <div class="metric-card">
                <div class="metric-label">團隊活動量</div>
                <div class="metric-value">156</div>
                <div style="color: #e74c3c; font-size: 0.9em;">↓ 5%</div>
            </div>
            """, unsafe_allow_html=True)
        
        with col4:
            st.markdown("""
            <div class="metric-card">
                <div class="metric-label">MDRT達成率</div>
                <div class="metric-value">48%</div>
                <div style="font-size: 0.9em;">目標: $512,800</div>
            </div>
            """, unsafe_allow_html=True)
        
        # 圖表區域
        col_chart1, col_chart2 = st.columns(2)
        
        with col_chart1:
            st.markdown("### 📈 業績趨勢")
            # 使用Plotly創建專業圖表
            months = ['1月', '2月', '3月', '4月', '5月', '6月']
            team_performance = [120000, 135000, 158000, 142000, 168000, 258400]
            individual_performance = [45000, 52000, 68000, 48000, 62000, 89500]
            
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=months, y=team_performance,
                mode='lines+markers',
                name='團隊業績',
                line=dict(color='#D4AF37', width=3)
            ))
            fig.add_trace(go.Scatter(
                x=months, y=individual_performance,
                mode='lines+markers',
                name='個人業績',
                line=dict(color='#3498db', width=3)
            ))
            
            fig.update_layout(
                height=300,
                plot_bgcolor='white',
                paper_bgcolor='white',
                showlegend=True,
                margin=dict(l=20, r=20, t=30, b=20)
            )
            
            st.plotly_chart(fig, use_container_width=True)
        
        with col_chart2:
            st.markdown("### 🎯 目標達成率")
            # 進度圖
            targets = ['Q1挑戰', 'MDRT', '招募目標', '活動目標']
            progress = [88, 48, 75, 62]
            
            fig2 = go.Figure(data=[
                go.Bar(
                    x=targets,
                    y=progress,
                    text=[f'{p}%' for p in progress],
                    textposition='auto',
                    marker_color=['#D4AF37', '#3498db', '#2ecc71', '#9b59b6']
                )
            ])
            
            fig2.update_layout(
                height=300,
                plot_bgcolor='white',
                paper_bgcolor='white',
                yaxis=dict(range=[0, 100])
            )
            
            st.plotly_chart(fig2, use_container_width=True)
        
        # 最近活動
        st.markdown("### 📅 最近活動")
        col_act1, col_act2, col_act3 = st.columns(3)
        
        activities = [
            {"user": "Tim", "action": "簽單完成", "amount": "$25,000", "time": "2小時前"},
            {"user": "Oscar", "action": "新人招募", "amount": "1人", "time": "4小時前"},
            {"user": "Catherine", "action": "客戶會議", "amount": "跟進中", "time": "昨天"}
        ]
        
        for i, activity in enumerate(activities):
            with [col_act1, col_act2, col_act3][i]:
                st.markdown(f"""
                <div class="professional-card" style="padding: 15px;">
                    <div style="display: flex; align-items: center; margin-bottom: 10px;">
                        <div style="width: 40px; height: 40px; border-radius: 50%; background: #D4AF37; 
                                 display: flex; align-items: center; justify-content: center; margin-right: 10px;">
                            <span style="color: white; font-weight: bold;">{activity['user'][0]}</span>
                        </div>
                        <div>
                            <strong>{activity['user']}</strong><br>
                            <small>{activity['time']}</small>
                        </div>
                    </div>
                    <div style="font-size: 1.1em; margin: 10px 0;">{activity['action']}</div>
                    <div style="color: #D4AF37; font-weight: bold; font-size: 1.2em;">{activity['amount']}</div>
                </div>
                """, unsafe_allow_html=True)
    
    elif menu_page == "activities":
        st.markdown("# 📝 活動記錄")
        
        tab1, tab2 = st.tabs(["📋 新增記錄", "📊 活動歷史"])
        
        with tab1:
            col_form1, col_form2 = st.columns([1.5, 1])
            
            with col_form1:
                with st.container():
                    st.markdown("### 新增活動記錄")
                    
                    date = st.date_input("📅 日期", datetime.date.today())
                    
                    col_type1, col_type2 = st.columns(2)
                    with col_type1:
                        activity_type = st.selectbox(
                            "🎯 活動類型",
                            ACTIVITY_TYPES
                        )
                    
                    with col_type2:
                        client_name = st.text_input("👤 客戶/準增員姓名")
                    
                    # 自動加載模板
                    default_note = ACTIVITY_TEMPLATES.get(activity_type, "")
                    note = st.text_area(
                        "📝 活動記錄",
                        value=default_note,
                        height=250,
                        placeholder="請詳細記錄活動內容..."
                    )
                    
                    col_status1, col_status2 = st.columns(2)
                    with col_status1:
                        status = st.selectbox(
                            "📌 狀態",
                            ["進行中", "已完成", "取消", "需跟進"]
                        )
                    
                    with col_status2:
                        st.markdown("<br>", unsafe_allow_html=True)
                        if st.button("💾 保存記錄", use_container_width=True):
                            if activity_type and note:
                                success = add_activity(
                                    st.session_state['user'],
                                    date,
                                    activity_type,
                                    note,
                                    client_name,
                                    status
                                )
                                if success:
                                    st.success("✅ 記錄保存成功！")
                                    st.rerun()
                                else:
                                    st.error("保存失敗，請重試")
                            else:
                                st.warning("請填寫必填字段")
            
            with col_form2:
                st.markdown("### 📊 活動統計")
                
                # 顯示個人統計
                user_stats = get_user_stats(st.session_state['user'])
                
                st.markdown(f"""
                <div class="professional-card" style="text-align: center;">
                    <div style="font-size: 0.9em; color: #7f8c8d;">本月活動次數</div>
                    <div style="font-size: 2.5em; font-weight: bold; color: #2c3e50;">
                        {user_stats['total_activities']}
                    </div>
                    <div style="margin: 20px 0;">
                        <div style="font-size: 0.9em; color: #7f8c8d;">活動積分</div>
                        <div style="font-size: 1.8em; font-weight: bold; color: #D4AF37;">
                            {user_stats['total_points']} 分
                        </div>
                    </div>
                    <div style="font-size: 0.8em; color: #95a5a6;">
                        目標: 每週最少3次活動
                    </div>
                </div>
                """, unsafe_allow_html=True)
                
                # 活動類型分布
                st.markdown("#### 📈 活動類型分布")
                types_data = {
                    '類型': ['見面', '傾保險', '傾招募', '簽單', '其他'],
                    '次數': [12, 8, 5, 3, 2]
                }
                
                fig_pie = px.pie(
                    types_data,
                    values='次數',
                    names='類型',
                    color_discrete_sequence=['#D4AF37', '#3498db', '#2ecc71', '#e74c3c', '#9b59b6']
                )
                
                fig_pie.update_layout(
                    height=250,
                    showlegend=True,
                    margin=dict(l=20, r=20, t=20, b=20)
                )
                
                st.plotly_chart(fig_pie, use_container_width=True)
        
        with tab2:
            st.markdown("### 📋 活動歷史記錄")
            
            # 過濾選項
            col_filter1, col_filter2, col_filter3 = st.columns(3)
            with col_filter1:
                date_range = st.date_input(
                    "日期範圍",
                    [datetime.date.today() - datetime.timedelta(days=30), datetime.date.today()],
                    max_value=datetime.date.today()
                )
            
            with col_filter2:
                filter_type = st.multiselect(
                    "活動類型",
                    ACTIVITY_TYPES,
                    default=ACTIVITY_TYPES
                )
            
            with col_filter3:
                filter_status = st.multiselect(
                    "狀態",
                    ["進行中", "已完成", "取消", "需跟進"],
                    default=["已完成", "進行中"]
                )
            
            # 顯示表格
            st.dataframe(
                pd.DataFrame({
                    '日期': ['2024-01-15', '2024-01-14', '2024-01-13'],
                    '類型': ['簽單 (5分)', '傾保險 (2分)', '見面 (1分)'],
                    '客戶': ['張先生', '李太太', '王小姐'],
                    '狀態': ['已完成', '進行中', '已完成'],
                    '備註': ['年繳保費$25,000', '方案建議跟進', '初步接觸']
                }),
                use_container_width=True,
                column_config={
                    "日期": st.column_config.TextColumn("日期", width="small"),
                    "類型": st.column_config.TextColumn("類型", width="medium"),
                    "客戶": st.column_config.TextColumn("客戶", width="small"),
                    "狀態": st.column_config.SelectboxColumn(
                        "狀態",
                        options=["進行中", "已完成", "取消", "需跟進"]
                    ),
                    "備註": st.column_config.TextColumn("備註", width="large")
                }
            )
    
    elif menu_page == "performance":
        st.markdown("# 💰 業績管理")
        
        col_perf1, col_perf2 = st.columns([2, 1])
        
        with col_perf1:
            st.markdown("### 📈 業績報表")
            
            # 選擇時間範圍
            timeframe = st.radio(
                "時間範圍",
                ["本月", "本季", "本年", "自選"],
                horizontal=True
            )
            
            # 業績圖表
            if timeframe == "本月":
                months = [f"第{i}週" for i in range(1, 5)]
                performance = [45000, 52000, 48000, 89500]
            elif timeframe == "本季":
                months = ['1月', '2月', '3月']
                performance = [120000, 135000, 158000]
            else:
                months = [f"{i}月" for i in range(1, 13)]
                performance = [120, 135, 158, 142, 168, 258, 180, 195, 210, 220, 235, 250]
                performance = [p * 1000 for p in performance]
            
            fig_perf = go.Figure()
            fig_perf.add_trace(go.Bar(
                x=months,
                y=performance,
                name='業績',
                marker_color='#D4AF37',
                text=[f'${p:,.0f}' for p in performance],
                textposition='auto'
            ))
            
            fig_perf.update_layout(
                height=400,
                plot_bgcolor='white',
                paper_bgcolor='white',
                showlegend=False,
                yaxis_title="業績 (HKD)",
                xaxis_title="時間"
            )
            
            st.plotly_chart(fig_perf, use_container_width=True)
        
        with col_perf2:
            st.markdown("### 🎯 業績目標")
            
            targets = [
                {"name": "月度目標", "current": 89500, "target": 100000, "progress": 89.5},
                {"name": "季度目標", "current": 413000, "target": 450000, "progress": 91.8},
                {"name": "年度目標", "current": 1895000, "target": 2500000, "progress": 75.8},
                {"name": "MDRT目標", "current": 413000, "target": 512800, "progress": 80.5}
            ]
            
            for target in targets:
                st.markdown(f"""
                <div style="margin-bottom: 20px;">
                    <div style="display: flex; justify-content: space-between; margin-bottom: 5px;">
                        <span style="font-weight: 500;">{target['name']}</span>
                        <span style="color: #D4AF37; font-weight: bold;">{target['progress']}%</span>
                    </div>
                    <div style="background: #ecf0f1; height: 8px; border-radius: 4px; overflow: hidden;">
                        <div style="background: linear-gradient(90deg, #D4AF37, #FFD700); 
                                 width: {target['progress']}%; height: 100%;"></div>
                    </div>
                    <div style="display: flex; justify-content: space-between; font-size: 0.8em; color: #7f8c8d; margin-top: 3px;">
                        <span>${target['current']:,.0f}</span>
                        <span>${target['target']:,.0f}</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)
            
            # 新增業績按鈕
            st.markdown("<br>", unsafe_allow_html=True)
            with st.expander("➕ 新增業績記錄"):
                month = st.selectbox(
                    "月份",
                    [f"2024-{i:02d}" for i in range(1, 13)]
                )
                
                col_amt1, col_amt2 = st.columns(2)
                with col_amt1:
                    amount = st.number_input("業績金額 (HKD)", min_value=0, step=1000)
                
                with col_amt2:
                    policy_count = st.number_input("保單數量", min_value=0, step=1)
                
                if st.button("💾 保存業績", use_container_width=True):
                    if amount > 0:
                        avg_premium = amount / policy_count if policy_count > 0 else 0
                        success = update_fyc(
                            st.session_state['user'],
                            month,
                            amount,
                            policy_count,
                            avg_premium
                        )
                        if success:
                            st.success("✅ 業績保存成功！")
                            st.rerun()
    
    elif menu_page == "leaderboard":
        st.markdown("# 🏆 精英排行榜")
        
        # 選擇排行榜類型
        tab_rank1, tab_rank2, tab_rank3 = st.tabs(["📊 業績排名", "🔥 活動量排名", "👥 招募排名"])
        
        with tab_rank1:
            st.markdown("### 🥇 業績排行榜")
            
            leaderboard_data = get_leaderboard_data("monthly")
            
            if not leaderboard_data.empty:
                # 顯示前三名
                col_top1, col_top2, col_top3 = st.columns(3)
                
                top3 = leaderboard_data.head(3)
                medals = ["🥇", "🥈", "🥉"]
                
                for i, (_, row) in enumerate(top3.iterrows()):
                    with [col_top1, col_top2, col_top3][i]:
                        st.markdown(f"""
                        <div style="text-align: center; padding: 20px; background: {'#FFF8E1' if i == 0 else '#F8F9FA'}; 
                                 border-radius: 15px; border: {'3px solid #FFD700' if i == 0 else '1px solid #e0e0e0'};">
                            <div style="font-size: 2em; margin-bottom: 10px;">{medals[i]}</div>
                            <img src="{row['avatar']}" style="width: 80px; height: 80px; border-radius: 50%; 
                                 border: 3px solid {'#FFD700' if i == 0 else '#C0C0C0' if i == 1 else '#CD7F32'};">
                            <h3 style="margin: 10px 0 5px 0;">{row['username']}</h3>
                            <div style="font-size: 1.5em; color: #D4AF37; font-weight: bold;">
                                ${row['fyc']:,.0f}
                            </div>
                            <div style="color: #7f8c8d; font-size: 0.9em;">
                                {row['policy_count']} 張保單
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                
                st.divider()
                
                # 完整排行榜
                st.markdown("### 📋 完整排名")
                
                # 添加排名列
                leaderboard_data['排名'] = range(1, len(leaderboard_data) + 1)
                
                st.dataframe(
                    leaderboard_data[['排名', 'avatar', 'username', 'fyc', 'mdrt_display', 'policy_count', 'activity_points']],
                    column_config={
                        "排名": st.column_config.NumberColumn("排名", format="%d", width="small"),
                        "avatar": st.column_config.ImageColumn("頭像", width="small"),
                        "username": st.column_config.TextColumn("姓名", width="medium"),
                        "fyc": st.column_config.NumberColumn("業績", format="$%d"),
                        "mdrt_display": st.column_config.TextColumn("MDRT進度"),
                        "policy_count": st.column_config.NumberColumn("保單數", format="%d"),
                        "activity_points": st.column_config.NumberColumn("活動分", format="%d")
                    },
                    use_container_width=True,
                    hide_index=True
                )
            else:
                st.info("暫無數據")
        
        with tab_rank2:
            st.markdown("### 🔥 活動量排行榜")
            
            # 模擬數據
            activity_data = pd.DataFrame({
                '排名': [1, 2, 3, 4, 5],
                '姓名': ['Tim', 'Oscar', 'Catherine', 'Maggie', 'Wilson'],
                '活動次數': [28, 25, 22, 18, 15],
                '活動積分': [156, 142, 128, 105, 88],
                '連續活躍': [15, 12, 10, 8, 5]
            })
            
            st.dataframe(
                activity_data,
                column_config={
                    "排名": st.column_config.NumberColumn("排名", format="%d"),
                    "姓名": st.column_config.TextColumn("姓名"),
                    "活動次數": st.column_config.NumberColumn("活動次數", format="%d"),
                    "活動積分": st.column_config.NumberColumn("活動積分", format="%d"),
                    "連續活躍": st.column_config.NumberColumn("連續活躍(天)", format="%d")
                },
                use_container_width=True,
                hide_index=True
            )
    
    elif menu_page == "challenges":
        st.markdown("# 🎯 目標挑戰")
        
        # Q1挑戰
        st.markdown("### 🔥 Q1 88,000挑戰賽")
        st.markdown("**時間：** 1月1日 - 3月31日")
        
        # 進度展示
        challenge_data = pd.DataFrame({
            '成員': ['Tim', 'Oscar', 'Catherine', 'Maggie', 'Wilson'],
            '當前業績': [89500, 68000, 52000, 32000, 18000],
            '目標': [88000, 88000, 88000, 88000, 88000],
            '進度': [101.7, 77.3, 59.1, 36.4, 20.5]
        })
        
        for _, row in challenge_data.iterrows():
            progress = min(row['進度'], 100)
            color = "#2ecc71" if progress >= 100 else "#D4AF37" if progress >= 70 else "#e74c3c"
            
            st.markdown(f"""
            <div style="margin-bottom: 15px;">
                <div style="display: flex; justify-content: space-between; margin-bottom: 5px;">
                    <span style="font-weight: 500;">{row['成員']}</span>
                    <span style="color: {color}; font-weight: bold;">{progress}%</span>
                </div>
                <div style="background: #ecf0f1; height: 10px; border-radius: 5px; overflow: hidden; margin-bottom: 5px;">
                    <div style="background: {color}; width: {progress}%; height: 100%;"></div>
                </div>
                <div style="display: flex; justify-content: space-between; font-size: 0.9em; color: #7f8c8d;">
                    <span>${row['當前業績']:,.0f}</span>
                    <span>目標: ${row['目標']:,.0f}</span>
                </div>
            </div>
            """, unsafe_allow_html=True)
        
        st.divider()
        
        # 年度獎勵
        st.markdown("### 🏅 年度獎勵計劃")
        
        col_rew1, col_rew2 = st.columns(2)
        
        with col_rew1:
            st.markdown("""
            <div class="professional-card" style="text-align: center;">
                <div style="font-size: 2em; color: #FFD700;">🥇</div>
                <h3 style="color: #D4AF37;">業績冠軍</h3>
                <div style="font-size: 1.5em; font-weight: bold; color: #2c3e50;">$20,000</div>
                <div style="color: #7f8c8d; margin: 10px 0;">全年業績第一名</div>
                <div style="font-size: 0.8em; color: #95a5a6;">最低要求: $1,000,000</div>
            </div>
            """, unsafe_allow_html=True)
        
        with col_rew2:
            st.markdown("""
            <div class="professional-card" style="text-align: center;">
                <div style="font-size: 2em; color: #C0C0C0;">🥈</div>
                <h3 style="color: #D4AF37;">招募冠軍</h3>
                <div style="font-size: 1.5em; font-weight: bold; color: #2c3e50;">雙人機票</div>
                <div style="color: #7f8c8d; margin: 10px 0;">全年招募人數最多</div>
                <div style="font-size: 0.8em; color: #95a5a6;">最低要求: 3人</div>
            </div>
            """, unsafe_allow_html=True)
        
        col_rew3, col_rew4 = st.columns(2)
        
        with col_rew3:
            st.markdown("""
            <div class="professional-card" style="text-align: center;">
                <div style="font-size: 2em; color: #CD7F32;">🥉</div>
                <h3 style="color: #D4AF37;">MDRT達成獎</h3>
                <div style="font-size: 1.5em; font-weight: bold; color: #2c3e50;">$10,000</div>
                <div style="color: #7f8c8d; margin: 10px 0;">首位達成MDRT資格</div>
                <div style="font-size: 0.8em; color: #95a5a6;">目標: $512,800</div>
            </div>
            """, unsafe_allow_html=True)
        
        with col_rew4:
            st.markdown("""
            <div class="professional-card" style="text-align: center;">
                <div style="font-size: 2em; color: #27ae60;">⭐</div>
                <h3 style="color: #D4AF37;">月度之星</h3>
                <div style="font-size: 1.5em; font-weight: bold; color: #2c3e50;">豪華晚餐</div>
                <div style="color: #7f8c8d; margin: 10px 0;">每月業績最高者</div>
                <div style="font-size: 0.8em; color: #95a5a6;">最低要求: $50,000</div>
            </div>
            """, unsafe_allow_html=True)
    
    elif menu_page == "team":
        st.markdown("# 👥 團隊管理")
        
        if st.session_state['role'] == 'Admin':
            tab_team1, tab_team2, tab_team3 = st.tabs(["👤 成員管理", "📊 團隊分析", "📋 團隊日曆"])
            
            with tab_team1:
                st.markdown("### 團隊成員")
                
                # 顯示所有成員
                users_df = read_data("users")
                if not users_df.empty:
                    members_df = users_df[users_df['role'] != 'Admin'][
                        ['username', 'role', 'team', 'join_date', 'phone', 'email']
                    ]
                    
                    st.dataframe(
                        members_df,
                        column_config={
                            "username": st.column_config.TextColumn("姓名"),
                            "role": st.column_config.TextColumn("職位"),
                            "team": st.column_config.TextColumn("團隊"),
                            "join_date": st.column_config.TextColumn("加入日期"),
                            "phone": st.column_config.TextColumn("電話"),
                            "email": st.column_config.TextColumn("電郵")
                        },
                        use_container_width=True,
                        hide_index=True
                    )
                
                # 新增成員
                with st.expander("➕ 新增團隊成員"):
                    col_new1, col_new2 = st.columns(2)
                    
                    with col_new1:
                        new_username = st.text_input("姓名")
                        new_role = st.selectbox(
                            "職位",
                            ["Associate", "Manager", "Senior Manager", "Director"]
                        )
                    
                    with col_new2:
                        new_team = st.text_input("團隊", value="Tim Team")
                        new_email = st.text_input("電郵")
                    
                    if st.button("新增成員", type="primary"):
                        if new_username and new_email:
                            st.success(f"已新增成員: {new_username}")
            
            with tab_team2:
                st.markdown("### 團隊分析")
                
                col_analysis1, col_analysis2 = st.columns(2)
                
                with col_analysis1:
                    st.markdown("#### 團隊分布")
                    team_data = pd.DataFrame({
                        '團隊': ['Tim Team', 'Oscar Team', 'Catherine Team'],
                        '人數': [12, 8, 6],
                        '平均業績': [85000, 72000, 68000]
                    })
                    
                    fig_team = px.bar(
                        team_data,
                        x='團隊',
                        y='人數',
                        color='平均業績',
                        color_continuous_scale='gold'
                    )
                    
                    st.plotly_chart(fig_team, use_container_width=True)
                
                with col_analysis2:
                    st.markdown("#### 職位分布")
                    role_data = pd.DataFrame({
                        '職位': ['Associate', 'Manager', 'Senior Manager', 'Director'],
                        '人數': [15, 6, 3, 2]
                    })
                    
                    fig_pie = px.pie(
                        role_data,
                        values='人數',
                        names='職位',
                        color_discrete_sequence=['#D4AF37', '#3498db', '#2ecc71', '#e74c3c']
                    )
                    
                    st.plotly_chart(fig_pie, use_container_width=True)
        else:
            st.info("🔒 此功能僅限管理員使用")
    
    elif menu_page == "settings":
        st.markdown("# ⚙️ 個人設置")
        
        tab_set1, tab_set2 = st.tabs(["👤 個人資料", "🔐 安全設置"])
        
        with tab_set1:
            col_profile1, col_profile2 = st.columns([1, 2])
            
            with col_profile1:
                # 顯示當前頭像
                current_avatar = st.session_state.get('avatar', '')
                st.image(current_avatar, width=150)
                
                # 上傳新頭像
                uploaded_file = st.file_uploader(
                    "選擇新頭像",
                    type=['jpg', 'jpeg', 'png'],
                    help="支持 JPG, JPEG, PNG 格式"
                )
                
                if uploaded_file is not None:
                    if st.button("💾 更新頭像", use_container_width=True):
                        try:
                            from PIL import Image, ImageDraw
                            image_str = process_image(uploaded_file)
                            if image_str:
                                update_avatar(st.session_state['user'], image_str)
                                st.session_state['avatar'] = image_str
                                st.success("✅ 頭像更新成功！")
                                st.rerun()
                        except Exception as e:
                            st.error(f"更新失敗: {str(e)}")
            
            with col_profile2:
                # 顯示用戶信息
                users_df = read_data("users")
                if not users_df.empty:
                    user_info = users_df[users_df['username'] == st.session_state['user']].iloc[0]
                    
                    st.markdown("### 個人信息")
                    
                    col_info1, col_info2 = st.columns(2)
                    
                    with col_info1:
                        st.text_input("姓名", value=user_info['username'], disabled=True)
                        st.text_input("職位", value=user_info['role'], disabled=True)
                    
                    with col_info2:
                        st.text_input("團隊", value=user_info['team'], disabled=True)
                        st.text_input("加入日期", value=user_info.get('join_date', 'N/A'), disabled=True)
                    
                    # 聯繫信息
                    st.markdown("#### 聯繫信息")
                    
                    col_contact1, col_contact2 = st.columns(2)
                    
                    with col_contact1:
                        phone = st.text_input("電話", value=user_info.get('phone', ''))
                    
                    with col_contact2:
                        email = st.text_input("電郵", value=user_info.get('email', ''))
                    
                    if st.button("💾 更新信息", type="primary"):
                        st.success("✅ 信息更新成功！")
        
        with tab_set2:
            st.markdown("### 🔐 修改密碼")
            
            col_pwd1, col_pwd2 = st.columns(2)
            
            with col_pwd1:
                current_password = st.text_input("當前密碼", type="password")
                new_password = st.text_input("新密碼", type="password")
            
            with col_pwd2:
                confirm_password = st.text_input("確認新密碼", type="password")
                
                if st.button("🔄 更新密碼", use_container_width=True, type="primary"):
                    if not current_password:
                        st.warning("請輸入當前密碼")
                    elif not new_password:
                        st.warning("請輸入新密碼")
                    elif new_password != confirm_password:
                        st.error("新密碼不一致")
                    elif len(new_password) < 6:
                        st.error("密碼至少需要6位字符")
                    else:
                        # 驗證當前密碼
                        user_data = login(st.session_state['user'], current_password)
                        if user_data:
                            update_password(st.session_state['user'], new_password)
                            st.success("✅ 密碼更新成功！")
                        else:
                            st.error("當前密碼不正確")
            
            st.divider()
            
            # 系統設置
            st.markdown("### ⚙️ 系統設置")
            
            col_sys1, col_sys2 = st.columns(2)
            
            with col_sys1:
                notification_email = st.checkbox("郵件通知", value=True)
                notification_whatsapp = st.checkbox("WhatsApp通知", value=True)
            
            with col_sys2:
                language = st.selectbox("界面語言", ["繁體中文", "English", "简体中文"])
                theme = st.selectbox("主題", ["淺色", "深色", "自動"])
            
            if st.button("💾 保存設置", use_container_width=True):
                        st.success("✅ 設置保存成功！")
