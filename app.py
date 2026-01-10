import streamlit as st
import pandas as pd
import json
import os
from datetime import datetime

# --- 設定檔案名稱 ---
DATA_FILE = 'activity_log.csv' 
STATUS_FILE = 'user_status.json'

# --- 1. 資料庫讀寫功能 ---

def load_data():
    """讀取活動紀錄，並強制轉換時間格式"""
    if not os.path.exists(DATA_FILE):
        # 初始化檔案
        df = pd.DataFrame(columns=['Timestamp', 'Agent', 'Activity', 'Summary'])
        df.to_csv(DATA_FILE, index=False)
        return df
    
    try:
        df = pd.read_csv(DATA_FILE)
        # 🔥 強制轉為 datetime 物件，確保時間比對正常
        df['Timestamp'] = pd.to_datetime(df['Timestamp'])
        return df
    except Exception as e:
        st.error(f"讀取資料庫錯誤: {e}")
        return pd.DataFrame()

def save_activity(agent, activity, summary):
    """儲存新活動"""
    df = load_data()
    new_data = pd.DataFrame({
        'Timestamp': [datetime.now()],
        'Agent': [agent],
        'Activity': [activity],
        'Summary': [summary]
    })
    # 使用 concat 寫入
    df = pd.concat([df, new_data], ignore_index=True)
    df.to_csv(DATA_FILE, index=False)

# --- 2. 通知系統功能 (彈窗邏輯) ---

def get_last_read_time(username):
    """獲取用戶上次已讀時間"""
    if not os.path.exists(STATUS_FILE):
        return datetime.min 
    try:
        with open(STATUS_FILE, 'r') as f:
            data = json.load(f)
        time_str = data.get(username)
        if time_str:
            return datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
    except:
        pass
    return datetime.min

def update_last_read_time(username):
    """更新用戶已讀時間為現在"""
    data = {}
    if os.path.exists(STATUS_FILE):
        try:
            with open(STATUS_FILE, 'r') as f:
                data = json.load(f)
        except:
            data = {}
    
    data[username] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(STATUS_FILE, 'w') as f:
        json.dump(data, f)

@st.dialog("🔥 團隊最新戰報 🔥")
def show_notification_modal(new_activities, current_user):
    st.markdown(f"**Hi {current_user}，你不在的時候，團隊發生了以下動態：**")
    
    for index, row in new_activities.iterrows():
        time_str = row['Timestamp'].strftime("%m/%d %H:%M")
        st.info(f"""
        **👤 {row['Agent']}** - {row['Activity']}
        \n📄 {row['Summary']}
        \n🕒 *{time_str}*
        """)
    
    st.markdown("---")
    
    if st.button("收到 / OK (我知道了)", type="primary", use_container_width=True):
        update_last_read_time(current_user)
        st.rerun()

def check_notifications(current_user):
    """檢查是否有新動態並觸發彈窗"""
    df = load_data()
    if df.empty:
        return

    # 1. 獲取上次讀取時間
    last_read = get_last_read_time(current_user)
    
    # 2. 篩選：時間 > 上次讀取 AND 不是自己做的
    new_activities = df[
        (df['Timestamp'] > last_read) & 
        (df['Agent'] != current_user)
    ]
    
    # 3. 觸發彈窗
    if not new_activities.empty:
        show_notification_modal(new_activities, current_user)

# --- 3. 主程式介面 ---

def main():
    # 設定網頁標題與寬版佈局
    st.set_page_config(page_title="FWD Team Power", page_icon="🚀", layout="wide")

    # --- 側邊欄：模擬登入 & 打卡 ---
    st.sidebar.header("🔐 登入模擬")
    users = ["Tim", "Leslie", "May", "Peter", "Jason", "Kylie"]
    current_user = st.sidebar.selectbox("切換使用者身分", users)
    
    st.sidebar.divider()
    
    st.sidebar.header("📝 新增活動")
    act_agent = st.sidebar.selectbox("是誰做的?", users, index=0)
    act_type = st.sidebar.selectbox("做了咩?", ["簽單 (Signed)", "見客 (Meeting)", "約客 (Call)", "交單 (Admin)"])
    act_summary = st.sidebar.text_input("詳情", "例如：簽左張儲蓄單 30k")
    
    if st.sidebar.button("提交活動"):
        save_activity(act_agent, act_type, act_summary)
        st.sidebar.success(f"已新增 {act_agent} 的紀錄！")
    
    # --- 核心邏輯：先檢查彈窗 ---
    check_notifications(current_user)

    # --- 主畫面內容 ---
    st.title(f"🚀 Team Activity Dashboard")
    st.markdown(f"Welcome back, **{current_user}**! Let's hit MDRT! 💪")
    
    df = load_data()

    if df.empty:
        st.info("暫無數據，請在側邊欄新增活動。")
        return

    # --- 分頁設計 (Tabs) ---
    tab1, tab2, tab3 = st.tabs(["🏆 龍虎榜 (Leaderboard)", "📊 團隊分析", "📝 詳細紀錄"])

    # Tab 1: 龍虎榜
    with tab1:
        st.subheader("🔥 本月活動量排名")
        
        # 計算每人活動次數
        leaderboard = df['Agent'].value_counts().reset_index()
        leaderboard.columns = ['Agent', 'Count']
        
        if not leaderboard.empty:
            top_agent = leaderboard.iloc[0]['Agent']
            top_count = leaderboard.iloc[0]['Count']
            
            col1, col2 = st.columns([1, 3])
            with col1:
                st.metric(label="👑 目前冠軍", value=top_agent, delta=f"{top_count} Activities")
            with col2:
                # 橫向長條圖
                st.bar_chart(leaderboard.set_index('Agent'), color="#FF4B4B", horizontal=True)
        else:
            st.write("尚無足夠數據顯示排名")

    # Tab 2: 團隊分析
    with tab2:
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("活動類型分佈")
            type_counts = df['Activity'].value_counts()
            st.bar_chart(type_counts)
            
        with col2:
            st.subheader("最新動態 (Top 5)")
            recent_df = df.sort_values(by='Timestamp', ascending=False).head(5)
            for i, row in recent_df.iterrows():
                time_display = row['Timestamp'].strftime('%H:%M')
                st.caption(f"{time_display} - **{row['Agent']}**")
                st.text(f"{row['Activity']} : {row['Summary']}")
                st.divider()

    # Tab 3: 詳細表格
    with tab3:
        st.dataframe(
            df.sort_values(by='Timestamp', ascending=False), 
            use_container_width=True,
            hide_index=True
        )

if __name__ == "__main__":
    main()
