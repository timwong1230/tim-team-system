import streamlit as st
import pandas as pd
import json
import os
from datetime import datetime

# --- 設定檔案名稱 ---
# 你的活動紀錄檔案 (Excel 或 CSV)
DATA_FILE = 'activity_log.csv' 
# 用來記錄每位同事「上次已讀時間」的系統檔案
STATUS_FILE = 'user_status.json'

# --- 1. 核心功能：讀取與寫入資料 ---

def load_data():
    """讀取活動紀錄，並強制轉換時間格式"""
    if not os.path.exists(DATA_FILE):
        # 如果檔案不存在，創建一個範本
        df = pd.DataFrame(columns=['Timestamp', 'Agent', 'Activity', 'Summary'])
        df.to_csv(DATA_FILE, index=False)
        return df
    
    try:
        df = pd.read_csv(DATA_FILE)
        # 🔥 關鍵修正：將 Timestamp 欄位強制轉為 datetime 物件，否則無法比較大小
        df['Timestamp'] = pd.to_datetime(df['Timestamp'])
        return df
    except Exception as e:
        st.error(f"讀取資料庫錯誤: {e}")
        return pd.DataFrame()

def save_activity(agent, activity, summary):
    """儲存新活動 (測試用)"""
    df = load_data()
    new_data = pd.DataFrame({
        'Timestamp': [datetime.now()],
        'Agent': [agent],
        'Activity': [activity],
        'Summary': [summary]
    })
    # 這裡使用 concat 代替 append (pandas 新版寫法)
    df = pd.concat([df, new_data], ignore_index=True)
    df.to_csv(DATA_FILE, index=False)

# --- 2. 核心功能：通知系統邏輯 ---

def get_last_read_time(username):
    """獲取該用戶上次按 OK 的時間"""
    if not os.path.exists(STATUS_FILE):
        return datetime.min # 如果沒紀錄過，回傳最小時間
    
    try:
        with open(STATUS_FILE, 'r') as f:
            data = json.load(f)
        time_str = data.get(username)
        if time_str:
            return datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
    except:
        pass # 如果讀取錯誤，回傳最小時間
    return datetime.min

def update_last_read_time(username):
    """更新該用戶的已讀時間為『現在』"""
    data = {}
    if os.path.exists(STATUS_FILE):
        try:
            with open(STATUS_FILE, 'r') as f:
                data = json.load(f)
        except:
            data = {}
    
    # 寫入現在時間
    data[username] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    with open(STATUS_FILE, 'w') as f:
        json.dump(data, f)

# --- 3. 彈窗介面設計 (使用 st.dialog) ---

@st.dialog("🔥 團隊最新戰報 🔥")
def show_notification_modal(new_activities, current_user):
    st.markdown(f"**Hi {current_user}，你不在的時候，團隊發生了以下動態：**")
    
    for index, row in new_activities.iterrows():
        # 格式化時間
        time_str = row['Timestamp'].strftime("%m/%d %H:%M")
        
        # 設計卡片樣式
        st.info(f"""
        **👤 {row['Agent']}** - {row['Activity']}
        \n📄 {row['Summary']}
        \n🕒 *{time_str}*
        """)
    
    st.markdown("---")
    
    if st.button("收到 / OK (我知道了)", type="primary", use_container_width=True):
        # 按下後，更新時間，關閉彈窗
        update_last_read_time(current_user)
        st.rerun()

def check_notifications(current_user):
    """主檢查邏輯：登入後呼叫此函數"""
    df = load_data()
    
    if df.empty:
        return

    # 1. 獲取上次讀取時間
    last_read = get_last_read_time(current_user)
    
    # 2. 篩選：(時間 > 上次讀取) AND (Agent != 自己)
    new_activities = df[
        (df['Timestamp'] > last_read) & 
        (df['Agent'] != current_user)
    ]
    
    # Debug 訊息 (如果想看系統運作狀況，可以取消下面註解)
    # st.write(f"上次讀取: {last_read}")
    # st.write(f"新動態數量: {len(new_activities)}")

    # 3. 如果有資料，觸發彈窗
    if not new_activities.empty:
        show_notification_modal(new_activities, current_user)

# --- 4. 主程式 APP ---

def main():
    st.set_page_config(page_title="Team Activity System", page_icon="📊")

    # --- 模擬登入系統 (用 Selectbox 快速切換身份測試) ---
    st.sidebar.header("🔐 登入模擬 (測試用)")
    users = ["Tim", "Leslie", "May", "Peter"]
    current_user = st.sidebar.selectbox("切換使用者身分", users)
    
    st.sidebar.divider()
    
    # --- 模擬打卡系統 (用來製造數據) ---
    st.sidebar.header("📝 模擬新增活動")
    act_agent = st.sidebar.selectbox("是誰做的?", users, index=1) # 預設選第二個人
    act_type = st.sidebar.selectbox("做了咩?", ["簽單", "見客", "招聘面試", "交單"])
    act_summary = st.sidebar.text_input("詳情", "例如：簽左張儲蓄單 30k")
    
    if st.sidebar.button("提交活動 (模擬打卡)"):
        save_activity(act_agent, act_type, act_summary)
        st.sidebar.success(f"已新增 {act_agent} 的紀錄！")
        # 這裡不 rerun，方便你觀察 data 變化
    
    # --- 🔥 這裡就是觸發彈窗的地方！ 🔥 ---
    # 放在主畫面的最上方
    check_notifications(current_user)

    # --- 主畫面顯示 ---
    st.title(f"👋 Hi, {current_user}")
    st.subheader("團隊活動量看板")

    df = load_data()
    if not df.empty:
        # 顯示最新的紀錄在最上面
        st.dataframe(
            df.sort_values(by='Timestamp', ascending=False), 
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("目前沒有活動紀錄，請在側邊欄新增。")

if __name__ == "__main__":
    main()
