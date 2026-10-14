"""TIM TEAM System — activity + performance hub."""

from __future__ import annotations

import datetime
import re
import urllib.parse

import pandas as pd
import streamlit as st

from tt_core.constants import (
    ACTIVITY_TYPES,
    AMMO_CATEGORIES,
    MDRT_TARGET,
    Q1_TARGET,
    WEEKLY_MIN_ACTS,
    WEEKLY_PENALTY,
)
from tt_core.data import (
    add_act,
    add_ammo,
    check_notifications,
    get_activity_style,
    get_all_act,
    get_clean_users,
    get_data,
    get_last_week_data,
    get_member_snapshot,
    get_note_template,
    get_q1_data,
    get_weekly_data,
    last_iris_sync,
    login,
    proc_img,
    upd_fyc,
    upd_rec,
    update_avt,
    update_pw,
)
from tt_core.db import (
    connection_banner_state,
    init_db_gs,
    read_data,
    warm_cache,
)
from tt_core.iris import (
    apply_sync,
    auto_build_preview,
    build_sync_preview,
    detect_columns,
    get_agent_map,
    load_iris_bytes,
    load_iris_file,
    preview_summary,
    sample_template_csv,
    save_agent_mapping,
    unmapped_agents,
)
from tt_core.iris_drive import (
    download_file,
    get_folder_id,
    has_new_inbox_file,
    list_inbox_files,
    mark_file_synced,
    save_folder_id,
    service_account_email,
)
from tt_core.styles import CUSTOM_CSS

st.set_page_config(
    page_title="TIM TEAM System",
    page_icon="🦁",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
init_db_gs()  # cached once per server process — no longer hits Sheets every rerun


# ─── Auth ────────────────────────────────────────────────────────────────────
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False

if not st.session_state["logged_in"]:
    c1, c2, c3 = st.columns([1, 1.4, 1])
    with c2:
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown(
            """
            <div class="login-panel">
              <div class="tt-kicker" style="color:#C5A028 !important;">TIM TEAM SYSTEM</div>
              <h1 style="margin:0 0 6px 0;">活動量 · 業績 · 一站管理</h1>
              <p style="color:#6B7280; margin:0 0 18px 0;">打卡更快 · 戰報更清晰 · Iris 業績自動同步</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown("<br>", unsafe_allow_html=True)
        u = st.text_input("Username", placeholder="e.g. Tim")
        p = st.text_input("Password", type="password", placeholder="••••••")
        if st.button("登入系統", use_container_width=True):
            d = login(u, p)
            if d:
                st.session_state.update(
                    {
                        "logged_in": True,
                        "user": d[0][0],
                        "role": d[0][2],
                        "avatar": d[0][5],
                    }
                )
                st.toast(f"Welcome back, {d[0][0]}!", icon="🦁")
                st.rerun()
            else:
                st.toast("登入失敗，請檢查帳密", icon="❌")
        st.caption("2026 MDRT 目標：$512,800  ·  M + 2 = 百萬年薪之路")
    st.stop()


# ─── Logged-in shell ─────────────────────────────────────────────────────────
# Warm disk cache once per browser session so pages read locally (fast + offline-safe)
if not st.session_state.get("_warmed_at"):
    with st.spinner("正在載入團隊數據（首次會稍慢，之後會用快取）…"):
        warm_cache(force=False)

check_notifications(st.session_state["user"])
is_leader = st.session_state["role"] == "Leader"
conn = connection_banner_state()

with st.sidebar:
    st.markdown("<br>", unsafe_allow_html=True)
    c_avt, c_txt = st.columns([1, 2])
    with c_avt:
        if st.session_state.get("avatar"):
            st.image(st.session_state["avatar"], width=72)
    with c_txt:
        st.markdown(
            f"<h3 style='margin:0'>{st.session_state['user']}</h3>",
            unsafe_allow_html=True,
        )
        st.caption(f"{st.session_state['role']} · TIM TEAM")

    if conn["level"] == "ok":
        st.success(conn["label"], icon="⚡")
    elif conn["level"] == "degraded":
        st.warning(conn["label"], icon="📡")
    else:
        st.info(conn["label"])

    if st.button("重新整理數據", use_container_width=True, help="強制向 Google Sheets 拉最新數據"):
        with st.spinner("同步雲端…"):
            warm_cache(force=True)
        st.toast("數據已更新", icon="✅")
        st.rerun()

    sync = last_iris_sync()
    if sync:
        st.caption(f"Iris 上次同步：{str(sync.get('synced_at', ''))[:16]}")
    else:
        st.caption("Iris 尚未同步業績")

    st.divider()
    menu_items = [
        "🏠 我的主頁",
        "📝 打卡 Check-in",
        "📊 團隊 Dashboard",
        "📅 每月業績",
        "🏆 年度挑戰",
        "⚖️ 每週挑戰",
        "🤝 招募龍虎榜",
        "📚 彈藥庫",
    ]
    if is_leader:
        menu_items.insert(4, "🔄 Iris 業績同步")
    menu_items.append("👤 設定")

    menu = st.radio("MAIN MENU", menu_items, label_visibility="collapsed")
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("登出", use_container_width=True, type="secondary"):
        st.session_state["logged_in"] = False
        st.rerun()

if conn["level"] == "degraded":
    st.warning(
        "雲端 Sheets 暫時慢／斷線，而家顯示離線快取數據。"
        "你可以繼續打卡（會先存本機）；連線恢復後按側欄「重新整理數據」。",
        icon="📡",
    )

if is_leader and get_folder_id():
    new_iris = has_new_inbox_file()
    if new_iris:
        st.info(
            f"Drive Iris Inbox 有新檔：**{new_iris.get('name')}** — "
            "去側欄「Iris 業績同步」撳「同步最新檔」即可更新業績。",
            icon="📥",
        )


# ─── Pages ───────────────────────────────────────────────────────────────────
def page_home():
    user = st.session_state["user"]
    snap = get_member_snapshot(user) if st.session_state["role"] == "Member" else None
    team = get_data("Yearly")

    st.markdown(
        f"""
        <div class="tt-hero">
          <div class="tt-kicker">TIM TEAM SYSTEM</div>
          <h1 style="margin:0;">你好，{user}</h1>
          <p class="tt-sub">今日目標：完成活動打卡 · 睇清楚自己同團隊進度</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if snap:
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.markdown(
                f"""<div class="tt-card"><div class="tt-label">本週活動</div>
                <div class="tt-value">{snap['wk_count']} / {WEEKLY_MIN_ACTS}</div>
                <div class="tt-hint">分數 {snap['wk_score']} · {snap['wk_start']} 起</div></div>""",
                unsafe_allow_html=True,
            )
        with c2:
            st.markdown(
                f"""<div class="tt-card"><div class="tt-label">我的 FYC</div>
                <div class="tt-value">${snap['fyc']:,.0f}</div>
                <div class="tt-hint">MDRT {snap['mdrt_pct']:.1f}%</div>
                <div class="tt-progress-wrap"><div class="tt-progress-bar" style="width:{snap['mdrt_pct']}%"></div></div>
                </div>""",
                unsafe_allow_html=True,
            )
        with c3:
            st.markdown(
                f"""<div class="tt-card"><div class="tt-label">活動分數</div>
                <div class="tt-value">{snap['score']}</div>
                <div class="tt-hint">全年累積</div></div>""",
                unsafe_allow_html=True,
            )
        with c4:
            st.markdown(
                f"""<div class="tt-card"><div class="tt-label">招募</div>
                <div class="tt-value">{snap['recruit']}</div>
                <div class="tt-hint">Team FYC ${snap['team_fyc']:,.0f}</div></div>""",
                unsafe_allow_html=True,
            )
    else:
        c1, c2, c3 = st.columns(3)
        c1.metric("Team FYC", f"${team['fyc'].sum():,.0f}" if not team.empty else "$0")
        c2.metric("Recruits", int(team["recruit"].sum()) if not team.empty else 0)
        c3.metric("Activities", int(team["Total_Score"].sum()) if not team.empty else 0)

    st.markdown("### 快速打卡")

    @st.fragment
    def _quick_checkin():
        with st.form("quick_checkin", clear_on_submit=True):
            c1, c2 = st.columns([1, 2])
            with c1:
                d = st.date_input("日期", value=datetime.date.today())
                t = st.selectbox("活動種類", ACTIVITY_TYPES)
            with c2:
                n = st.text_area(
                    "重點備註（可簡短）",
                    height=120,
                    placeholder="客戶名 / 下一步 / 結果…",
                )
            if st.form_submit_button("提交打卡", type="primary", use_container_width=True):
                if n.strip():
                    add_act(user, d, t, n.strip())
                    st.toast("打卡成功！", icon="✅")
                    st.rerun(scope="app")
                else:
                    st.error("請寫至少一句備註")

    _quick_checkin()

    st.markdown("### 團隊最新動態")
    acts = get_all_act().head(5)
    users_df = get_clean_users()
    if acts.empty:
        st.info("暫時未有動態 — 去「打卡」寫第一筆啦。")
    else:
        acts = pd.merge(acts, users_df[["username", "avatar"]], on="username", how="left")
        for _, row in acts.iterrows():
            act_date = pd.to_datetime(row["date"]).strftime("%Y-%m-%d")
            avatar_url = (
                row["avatar"]
                if isinstance(row.get("avatar"), str) and str(row["avatar"]).startswith("http")
                else f"https://ui-avatars.com/api/?background=d4af37&color=fff&name={row['username']}"
            )
            card_class, badge_class = get_activity_style(row["type"])
            note_html = str(row["note"]).replace("\n", "<br>")
            st.markdown(
                f"""
                <div class="activity-card {card_class}">
                  <div class="act-header">
                    <div style="display:flex;align-items:center;">
                      <img src="{avatar_url}" class="act-avatar">
                      <div><div class="act-name">{row['username']}</div>
                      <div class="act-time">{act_date}</div></div>
                    </div>
                    <div class="act-badge {badge_class}">{row['type']}</div>
                  </div>
                  <div class="act-content">{note_html}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def page_checkin():
    st.markdown("## 打卡中心")
    st.caption("用範本記面談重點，提交後即時出現喺團隊動態。")
    tab_new, tab_hist = st.tabs(["立即打卡", "團隊動態"])

    with tab_new:
        t = st.selectbox("活動種類", ACTIVITY_TYPES, key="ci_type")
        default_note = get_note_template(t)
        with st.form("checkin_form", clear_on_submit=True):
            d = st.date_input("日期", value=datetime.date.today())
            n = st.text_area("內容詳情", value=default_note, height=200)
            if st.form_submit_button("提交打卡", type="primary", use_container_width=True):
                add_act(st.session_state["user"], d, t, n)
                st.toast("提交成功！", icon="✅")

    with tab_hist:
        users_df = get_clean_users()
        filter_user = st.multiselect(
            "篩選同事", options=users_df["username"].unique().tolist() if not users_df.empty else []
        )
        all_acts = get_all_act()
        if all_acts.empty:
            st.info("暫無動態")
            return
        all_acts = pd.merge(all_acts, users_df[["username", "avatar"]], on="username", how="left")
        display_df = all_acts[all_acts["username"].isin(filter_user)] if filter_user else all_acts
        for _, row in display_df.iterrows():
            act_date = pd.to_datetime(row["date"]).strftime("%Y-%m-%d")
            act_time = (
                pd.to_datetime(row["timestamp"]).strftime("%H:%M") if row.get("timestamp") else ""
            )
            avatar_url = (
                row["avatar"]
                if isinstance(row.get("avatar"), str) and str(row["avatar"]).startswith("http")
                else f"https://ui-avatars.com/api/?background=random&color=fff&name={row['username']}"
            )
            card_class, badge_class = get_activity_style(row["type"])
            st.markdown(
                f"""
                <div class="activity-card {card_class}">
                  <div class="act-header">
                    <div style="display:flex;align-items:center;">
                      <img src="{avatar_url}" class="act-avatar">
                      <div><div class="act-name">{row['username']}</div>
                      <div class="act-time">{act_date} {act_time}</div></div>
                    </div>
                    <div class="act-badge {badge_class}">{row['type']}</div>
                  </div>
                  <div class="act-content">{str(row['note']).replace(chr(10), '<br>')}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def page_dashboard():
    st.markdown(f"## Dashboard · {st.session_state['user']}")
    if is_leader:
        with st.expander("每週戰報生成器（Leader）", expanded=False):
            if st.button("生成上週結算戰報"):
                wk_df, start, end = get_last_week_data()
                max_score = wk_df["wk_score"].max() if not wk_df.empty else 0
                winners = (
                    wk_df[wk_df["wk_score"] == max_score]
                    if not wk_df.empty and max_score > 0
                    else pd.DataFrame()
                )
                losers = wk_df[wk_df["wk_count"] < WEEKLY_MIN_ACTS] if not wk_df.empty else pd.DataFrame()
                penalty_total = len(losers) * WEEKLY_PENALTY
                prize = (
                    penalty_total / len(winners)
                    if penalty_total > 0 and not winners.empty
                    else (WEEKLY_PENALTY / len(winners) if not winners.empty else 0)
                )
                report = f"📅 *【TIM TEAM 上週戰報 ({start} ~ {end})】*\n\n"
                if max_score > 0 and not winners.empty:
                    report += f"🏆 *上週 MVP (獨得獎金 ${int(prize)}):*\n"
                    for _, w in winners.iterrows():
                        report += f"👑 *{w['username']}* ({int(w['wk_score'])}分)\n"
                    report += (
                        f"_多謝 {len(losers)} 位同事贊助獎金池！_\n\n"
                        if penalty_total > 0
                        else "_全員達標！Tim 自掏 $100 請飲茶！_\n\n"
                    )
                else:
                    report += "⚠️ *上週全軍覆沒？* 無人開工？\n\n"
                if not losers.empty:
                    report += f"💸 *【罰款名單 - 每人 ${WEEKLY_PENALTY}】*\n"
                    for _, l in losers.iterrows():
                        report += f"❌ {l['username']} (得 {int(l['wk_count'])} 次)\n"
                else:
                    report += "✅ *上週無人罰款！Excellent！*\n"
                report += "\n📊 *詳細戰況：*\n"
                if not wk_df.empty:
                    for _, row in wk_df.sort_values(by="wk_score", ascending=False).iterrows():
                        report += f"{row['username']}: {int(row['wk_score'])}分 ({int(row['wk_count'])}次)\n"
                report += "\n🚀 *新一週由零開始，大家加油！*"
                st.code(report)
                st.link_button("Send to WhatsApp", f"https://wa.me/?text={urllib.parse.quote(report)}")

    df = get_data("Yearly")
    c1, c2, c3 = st.columns(3)
    c1.metric("Team FYC", f"${df['fyc'].sum():,.0f}" if not df.empty else "$0")
    c2.metric("Recruits", int(df["recruit"].sum()) if not df.empty else 0)
    c3.metric("Activities", int(df["Total_Score"].sum()) if not df.empty else 0)

    st.markdown("### Leaderboard")
    if df.empty:
        st.info("暫無成員數據")
    else:
        df = df.copy()
        df["mdrt_fraction"] = df["fyc"].apply(lambda x: f"${x:,.0f} / ${MDRT_TARGET:,.0f}")
        df["mdrt_percent"] = (df["fyc"] / MDRT_TARGET) * 100
        st.dataframe(
            df.sort_values(by="fyc", ascending=False)[
                ["avatar", "username", "mdrt_fraction", "mdrt_percent", "recruit", "Total_Score"]
            ],
            column_config={
                "avatar": st.column_config.ImageColumn("Avatar", width="small"),
                "username": "Name",
                "mdrt_fraction": "MDRT 進度",
                "mdrt_percent": st.column_config.ProgressColumn(
                    "MDRT %", format="%.1f%%", min_value=0, max_value=100
                ),
                "recruit": st.column_config.NumberColumn("Recruit", format="%d"),
                "Total_Score": st.column_config.NumberColumn("Activity", format="%d"),
            },
            use_container_width=True,
            hide_index=True,
        )

    if is_leader:
        with st.expander("手動調整業績 / 招募（備用）"):
            st.caption("日常請用「Iris 業績同步」。呢度只係後備人手修正。")
            c_a, c_b, c_c = st.columns(3)
            user_list = df["username"].unique().tolist() if not df.empty else []
            tgt = c_a.selectbox("User", user_list)
            mth = c_b.selectbox("Month", [f"2026-{i:02d}" for i in range(1, 13)])
            amt = c_c.number_input("Amount", step=1000)
            if st.button("Save FYC"):
                upd_fyc(tgt, mth, amt, source="manual")
                st.toast("Saved!", icon="✅")
                st.rerun()
            st.divider()
            c_d, c_e = st.columns(2)
            tgt_r = c_d.selectbox("User", user_list, key="r1")
            rec = c_e.number_input("Recruits", step=1)
            if st.button("Save Recruit"):
                upd_rec(tgt_r, rec)
                st.toast("Saved!", icon="✅")
                st.rerun()


def page_iris_sync():
    st.markdown("## Iris 業績同步")
    st.markdown(
        """
        <div class="iris-banner">
          <strong>點用先啱</strong><br>
          Iris 團隊報表通常會連其他同事一齊出嚟 — <b>唔使全部入系統</b>。<br>
          只需對應 <b>TIM TEAM 成員</b>；其他編號會自動忽略，唔會寫入業績。<br>
          日常：Iris 匯出 → 丟 Drive → 撳「同步最新檔」。
        </div>
        """,
        unsafe_allow_html=True,
    )

    tab_drive, tab_map, tab_sync, tab_log = st.tabs(
        ["① Drive 自動同步（推薦）", "② 顧問對應", "③ 手動上傳", "④ 同步紀錄"]
    )

    with tab_drive:
        sa = service_account_email()
        st.markdown("#### 一次性設定（約 2 分鐘）")
        st.markdown(
            f"""
1. Google Drive 開一個資料夾，例如 **`TIM TEAM Iris Inbox`**
2. 右鍵資料夾 → 共用 → 加入呢個電郵（編輯者權限）：  
   `{sa or "（讀唔到 service account，請檢查 Streamlit secrets）"}`
3. 打開資料夾，從網址複製 Folder ID  
   （`https://drive.google.com/drive/folders/`**`呢串ID`**）
4. 貼下面儲存
            """
        )
        folder_now = get_folder_id()
        folder_in = st.text_input(
            "Drive Folder ID 或完整資料夾連結",
            value=folder_now,
            placeholder="例如 1AbCDef... 或完整 folders/ URL",
        )
        if st.button("儲存 Drive 資料夾", type="primary"):
            if save_folder_id(folder_in):
                st.toast("已儲存 Drive 資料夾", icon="✅")
                st.rerun()
            else:
                st.error("儲存失敗，請檢查 Google Sheets 連線")

        st.divider()
        st.markdown("#### 日常操作")
        st.caption("喺 Iris 匯出業績檔 → 上傳／儲存去呢個 Drive 資料夾 → 返嚟撳同步。")

        month_drive = st.selectbox(
            "若檔案無月份欄，使用此月份",
            [f"2026-{i:02d}" for i in range(1, 13)],
            index=max(0, datetime.date.today().month - 1),
            key="iris_drive_month",
        )

        if not get_folder_id():
            st.info("請先完成上面嘅 Drive 資料夾設定。")
        else:
            files = list_inbox_files(limit=8)
            err = st.session_state.get("_iris_drive_error")
            if err:
                st.error(
                    f"讀取 Drive 失敗：{err}\n\n"
                    "常見原因：未將資料夾共用俾 service account，或 Folder ID 錯。"
                )
            if not files:
                st.warning("資料夾未見 Excel/CSV。請將 Iris 匯出檔放進去再試。")
            else:
                st.markdown("**資料夾最新檔案**")
                st.dataframe(
                    [
                        {
                            "檔名": f.get("name"),
                            "更新時間": str(f.get("modifiedTime", ""))[:19].replace("T", " "),
                            "大小": f.get("size", ""),
                        }
                        for f in files
                    ],
                    use_container_width=True,
                    hide_index=True,
                )
                latest = files[0]
                c1, c2 = st.columns(2)
                with c1:
                    do_preview = st.button("預覽最新檔", use_container_width=True)
                with c2:
                    do_sync = st.button(
                        "同步最新檔到系統",
                        type="primary",
                        use_container_width=True,
                    )

                if do_preview or do_sync:
                    try:
                        raw = download_file(latest["id"])
                        raw_df = load_iris_bytes(raw, latest.get("name", "iris.xlsx"))
                        preview, detected = auto_build_preview(raw_df, month_drive)
                        st.session_state["_iris_last_preview"] = preview
                        st.caption(
                            f"自動欄位：姓名={detected.get('agent') or '—'} · "
                            f"編號={detected.get('code') or '—'} · "
                            f"FYC={detected.get('fyc')} · "
                            f"月份={detected.get('month') or month_drive}"
                        )
                        summary = preview_summary(preview)
                        st.write(
                            f"團隊可同步：**{summary['matched_rows']}** 列 "
                            f"（{summary['matched_users']} 人）· "
                            f"其他同事將忽略：**{summary['unmapped_agents']}** 個編號"
                        )
                        show_all = st.checkbox("顯示全部（含非團隊）", value=False, key="drv_show_all")
                        matched_view = preview[preview["matched"]]
                        view = preview if show_all else matched_view
                        if matched_view.empty:
                            st.info("而家未對應到任何團隊成員。請去「② 顧問對應」只加你團隊。")
                        st.dataframe(
                            view if not view.empty else preview.head(20),
                            use_container_width=True,
                            hide_index=True,
                            column_config={
                                "amount": st.column_config.NumberColumn("FYC", format="$%.0f"),
                                "matched": "團隊成員",
                            },
                        )
                        if summary["matched_rows"] == 0:
                            st.warning(
                                "未對應到 TIM TEAM 成員。請去「② 顧問對應」，"
                                "用 Iris 編號（例如 30947）對應你團隊 Username。"
                                "其他同事唔使加。"
                            )
                        elif summary["unmapped_agents"] > 0:
                            st.caption(
                                f"有 {summary['unmapped_agents']} 個非團隊編號會自動略過 — 正常。"
                            )
                        if do_sync:
                            if summary["matched_rows"] == 0:
                                st.error("未有團隊成員可同步。請先完成顧問對應。")
                            else:
                                result = apply_sync(
                                    preview,
                                    st.session_state["user"],
                                    latest.get("name", "drive.xlsx"),
                                )
                                mark_file_synced(latest["id"])
                                st.success(
                                    f"已同步「{latest.get('name')}」： "
                                    f"更新 {result['updated']} 筆 · "
                                    f"{result['matched_users']} 位團隊成員 "
                                    f"（另忽略 {result['unmatched']} 列非團隊）"
                                )
                                st.balloons()
                    except Exception as e:
                        st.error(f"處理失敗：{e}")

    users = get_clean_users()
    member_names = (
        users[users["role"] == "Member"]["username"].tolist() if not users.empty else []
    )

    with tab_map:
        st.markdown("#### 只對應你團隊（其他 Iris 同事可忽略）")
        st.caption(
            "你張報表入面嘅數字（如 30947）多數係 Iris 顧問編號。"
            "只需為 TIM TEAM 成員建立對應；其餘編號唔使理。"
        )

        last_preview = st.session_state.get("_iris_last_preview")
        pending = unmapped_agents(last_preview) if last_preview is not None else pd.DataFrame()
        if not pending.empty:
            st.markdown("##### 從最新預覽快速對應")
            st.dataframe(
                pending.head(30),
                use_container_width=True,
                hide_index=True,
                column_config={"amount": st.column_config.NumberColumn("FYC", format="$%.0f")},
            )
            with st.form("quick_map_form", clear_on_submit=True):
                options = []
                for _, r in pending.iterrows():
                    code = str(r.get("iris_code") or "").strip()
                    name = str(r.get("iris_name") or "").strip()
                    label = code or name
                    if label:
                        options.append(label)
                pick = st.selectbox("揀一個 Iris 編號／姓名", options)
                user_q = st.selectbox("對應到系統 Username", member_names, key="quick_map_user")
                if st.form_submit_button("儲存呢個對應", type="primary"):
                    if pick and user_q:
                        if re.fullmatch(r"\d{4,}", str(pick)):
                            save_agent_mapping("", str(pick), user_q, "quick-map")
                        else:
                            save_agent_mapping(str(pick), "", user_q, "quick-map")
                        st.toast(f"已對應 {pick} → {user_q}", icon="✅")
                        st.rerun()

        st.markdown("##### 手動新增對應")
        with st.form("map_form", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            iris_name = c1.text_input("Iris 姓名（可留空）", placeholder="報表有姓名先填")
            iris_code = c2.text_input("Iris 編號", placeholder="例如 30947")
            username = c3.selectbox("系統 Username", member_names)
            notes = st.text_input("備註（可選）")
            if st.form_submit_button("儲存對應", type="primary"):
                if iris_name or iris_code:
                    save_agent_mapping(iris_name, iris_code, username, notes)
                    st.toast("對應已儲存", icon="✅")
                    st.rerun()
                else:
                    st.error("請至少填 Iris 姓名或編號")

        amap = get_agent_map()
        if amap.empty:
            st.info("未有對應。建議先「預覽最新檔」，再用上面快速對應你團隊。")
        else:
            st.markdown("##### 已儲存對應")
            st.dataframe(amap, use_container_width=True, hide_index=True)

    with tab_sync:
        st.download_button(
            "下載範本 CSV",
            data=sample_template_csv(),
            file_name="iris_fyc_template.csv",
            mime="text/csv",
        )
        uploaded = st.file_uploader(
            "上傳 Iris 匯出檔",
            type=["xlsx", "xls", "csv"],
            help="支援常見欄位：Agent Name / Agent Code / FYC / Month",
        )
        default_month = datetime.date.today().strftime("%Y-%m")
        month_choice = st.selectbox(
            "若檔案無月份欄，使用此月份",
            [f"2026-{i:02d}" for i in range(1, 13)],
            index=max(0, datetime.date.today().month - 1),
        )

        if uploaded:
            try:
                raw_df = load_iris_file(uploaded)
            except Exception as e:
                st.error(f"無法讀取檔案：{e}")
                return

            st.markdown("#### 原始預覽")
            st.dataframe(raw_df.head(20), use_container_width=True)

            detected = detect_columns(raw_df)
            cols = [str(c) for c in raw_df.columns]
            c1, c2, c3, c4 = st.columns(4)
            col_agent = c1.selectbox(
                "姓名欄",
                ["（無）"] + cols,
                index=(cols.index(detected["agent"]) + 1) if detected["agent"] in cols else 0,
            )
            col_code = c2.selectbox(
                "編號欄",
                ["（無）"] + cols,
                index=(cols.index(detected["code"]) + 1) if detected["code"] in cols else 0,
            )
            fyc_default = cols.index(detected["fyc"]) if detected["fyc"] in cols else 0
            col_fyc = c3.selectbox("FYC / 業績欄", cols, index=fyc_default)
            col_month = c4.selectbox(
                "月份欄",
                ["（用上方選擇）"] + cols,
                index=(cols.index(detected["month"]) + 1) if detected["month"] in cols else 0,
            )

            preview = build_sync_preview(
                raw_df,
                None if col_agent == "（無）" else col_agent,
                None if col_code == "（無）" else col_code,
                col_fyc,
                None if col_month == "（用上方選擇）" else col_month,
                month_choice or default_month,
            )
            st.session_state["_iris_last_preview"] = preview
            st.markdown("#### 對應結果")
            summary = preview_summary(preview)
            st.write(
                f"團隊可同步：**{summary['matched_rows']}** 列 · "
                f"其他同事將忽略：**{summary['unmapped_agents']}** 個編號"
            )
            st.dataframe(
                preview,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "amount": st.column_config.NumberColumn("FYC", format="$%.0f"),
                    "matched": "團隊成員",
                },
            )
            if summary["unmapped_agents"] > 0:
                st.caption("未對應 = 非團隊／未設定，同步時會自動略過。只需對應 TIM TEAM 成員。")
                with st.expander("查看將被忽略嘅編號"):
                    st.dataframe(
                        unmapped_agents(preview),
                        use_container_width=True,
                        hide_index=True,
                    )

            if st.button(
                "確認同步到系統",
                type="primary",
                disabled=summary["matched_rows"] == 0,
            ):
                result = apply_sync(preview, st.session_state["user"], uploaded.name)
                st.success(
                    f"同步完成：更新 {result['updated']} 筆 · "
                    f"涵蓋 {result['matched_users']} 位團隊成員 · "
                    f"忽略 {result['unmatched']} 列非團隊 · "
                    f"月份 {', '.join(result['months']) or '—'}"
                )
                st.balloons()
                st.rerun()

    with tab_log:
        log = read_data("iris_sync_log")
        if log.empty:
            st.info("未有同步紀錄")
        else:
            st.dataframe(
                log.sort_values(by="id", ascending=False),
                use_container_width=True,
                hide_index=True,
            )


def page_monthly():
    st.markdown("## 每月 FYC")
    m = st.selectbox("月份", [f"2026-{i:02d}" for i in range(1, 13)], index=datetime.date.today().month - 1)
    df = get_data(month=m)
    if df.empty:
        st.info("本月暫無數據 — Leader 可用 Iris 同步匯入。")
        return
    max_fyc = df["fyc"].max() if df["fyc"].max() > 0 else 50000
    st.dataframe(
        df[["avatar", "username", "fyc"]].sort_values(by="fyc", ascending=False),
        column_config={
            "avatar": st.column_config.ImageColumn("Avatar", width="small"),
            "username": "Agent",
            "fyc": st.column_config.ProgressColumn(
                "FYC", format="$%d", min_value=0, max_value=max_fyc
            ),
        },
        use_container_width=True,
        hide_index=True,
    )


def page_year_goal():
    st.markdown("## 2026 年度挑戰")
    q1_df = get_q1_data()
    st.markdown(
        f"""
        <div class="challenge-header-box">
          <strong>Q1 {Q1_TARGET:,} Challenge（1/1 – 31/3）</strong><br>
          第一季累積 FYC 達 HK$ {Q1_TARGET:,} — MDRT 入場券。
        </div>
        """,
        unsafe_allow_html=True,
    )
    if not q1_df.empty:
        for _, r in q1_df.sort_values(by="q1_total", ascending=False).iterrows():
            progress = min(r["q1_total"] / Q1_TARGET, 1.0) if Q1_TARGET else 0
            st.markdown(
                f"""
                <div class="tt-card" style="margin-bottom:10px;display:flex;gap:14px;align-items:center;">
                  <img src="{r['avatar']}" style="width:52px;height:52px;border-radius:50%;object-fit:cover;">
                  <div style="flex:1;">
                    <div style="font-weight:700;">{r['username']}</div>
                    <div>${r['q1_total']:,.0f}</div>
                    <div class="tt-progress-wrap"><div class="tt-progress-bar" style="width:{progress*100}%;"></div></div>
                    <div class="tt-hint">Target: ${Q1_TARGET:,} ({progress*100:.1f}%)</div>
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
    else:
        st.info("暫無 Q1 業績數據")

    st.markdown("### 年度獎賞")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(
            '<div class="reward-card-premium"><span class="reward-icon">🚀</span>'
            '<p class="reward-title-p">1st MDRT</p><p class="reward-prize-p">$20,000 Cash</p>'
            '<p class="reward-desc-p">首位完成 $512,800 FYC 者獨得</p></div>',
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            '<div class="reward-card-premium"><span class="reward-icon">👑</span>'
            '<p class="reward-title-p">Top FYC 冠軍</p><p class="reward-prize-p">$10,000 Cash</p>'
            '<p class="reward-desc-p">全年業績最高者 (需 Min. 180,000 FYC)</p></div>',
            unsafe_allow_html=True,
        )
    c3, c4 = st.columns(2)
    with c3:
        st.markdown(
            '<div class="reward-card-premium"><span class="reward-icon">✈️</span>'
            '<p class="reward-title-p">招募冠軍</p><p class="reward-prize-p">雙人來回機票</p>'
            '<p class="reward-desc-p">全年招募人數最多者 (需 Min. 2人)</p></div>',
            unsafe_allow_html=True,
        )
    with c4:
        st.markdown(
            '<div class="reward-card-premium"><span class="reward-icon">🍽️</span>'
            '<p class="reward-title-p">Monthly Star</p><p class="reward-prize-p">Tim 請食飯</p>'
            '<p class="reward-desc-p">單月 FYC 最高者 (需 Min. $20k)</p></div>',
            unsafe_allow_html=True,
        )


def page_challenge():
    df, start, end = get_weekly_data()
    st.markdown(f"## 每週挑戰 · {start} ~ {end}")
    st.markdown(
        f"""
        <div class="challenge-header-box">
          <strong>遊戲規則</strong>
          <ul>
            <li>結算：逢星期日晚 23:59</li>
            <li>每週活動少於 <strong>{WEEKLY_MIN_ACTS} 次</strong> → 罰款 ${WEEKLY_PENALTY}</li>
            <li>罰款注入獎金池，由最高分者獨得</li>
          </ul>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if df.empty:
        st.info("本週暫無數據")
        return
    max_score = df["wk_score"].max()
    winners = df[df["wk_score"] == max_score] if max_score > 0 else pd.DataFrame()
    pool = len(df[df["wk_count"] < WEEKLY_MIN_ACTS]) * WEEKLY_PENALTY
    st.markdown(
        f"### Prize Pool: <span style='color:#C5A028'>${pool if pool > 0 else WEEKLY_PENALTY}</span>",
        unsafe_allow_html=True,
    )
    if not winners.empty:
        cols = st.columns(len(winners))
        for idx, row in winners.reset_index().iterrows():
            cols[idx].image(row["avatar"], width=60)
            cols[idx].caption(f"👑 {row['username']}")
    st.dataframe(
        df[["avatar", "username", "wk_score", "wk_count"]].sort_values(
            by="wk_score", ascending=False
        ),
        column_config={
            "avatar": st.column_config.ImageColumn("", width="small"),
            "wk_score": st.column_config.ProgressColumn(
                "Score", format="%d", max_value=max(10, int(max_score) if max_score else 10)
            ),
        },
        use_container_width=True,
        hide_index=True,
    )


def page_recruit():
    st.markdown("## 招募龍虎榜")
    df = get_data("Yearly")
    if df.empty:
        st.info("暫無招募數據")
        return
    st.dataframe(
        df[["avatar", "username", "recruit"]].sort_values(by="recruit", ascending=False),
        column_config={
            "avatar": st.column_config.ImageColumn("Avatar", width="small"),
            "username": "Agent",
            "recruit": st.column_config.ProgressColumn(
                "Recruits", format="%d", min_value=0, max_value=10
            ),
        },
        use_container_width=True,
        hide_index=True,
    )


def page_ammo():
    st.markdown("## Story Depot 彈藥庫")
    st.caption("將客觀數據轉成真實故事：噩夢 vs 美夢")

    active_pool_df = get_clean_users()
    roster_pool = (
        active_pool_df[~active_pool_df["username"].isin(["Admin", "Tim"])]["username"]
        .dropna()
        .unique()
        .tolist()
    )
    roster_pool.sort()
    if not roster_pool:
        roster_pool = [u for u in active_pool_df["username"].unique() if u != "Admin"] or ["本週負責同事"]
    curr_week_num = datetime.date.today().isocalendar()[1]
    this_week_duty = roster_pool[curr_week_num % len(roster_pool)]

    st.markdown(
        f"""
        <div class="challenge-header-box" style="border-left-color:#9b59b6;background:linear-gradient(to right,#f4ecf7,#ffffff);">
          <div style="font-weight:800;color:#9b59b6;">本週 Drill Training（Week {curr_week_num}）</div>
          輪值主講：<strong style="color:#9b59b6;">【 {this_week_duty} 】</strong><br>
          固定主講：<strong style="color:#D4AF37;">【 Tim 】</strong>
        </div>
        """,
        unsafe_allow_html=True,
    )

    tab_submit, tab_library = st.tabs(["提交知識素材", "團隊武器庫"])
    with tab_submit:
        with st.form("ammo_form", clear_on_submit=True):
            c_cat, c_date = st.columns(2)
            cat = c_cat.selectbox("知識點範疇", AMMO_CATEGORIES)
            d = c_date.date_input("提交日期", value=datetime.date.today())
            title = st.text_input("知識點主題 (Hook)", placeholder="e.g. 隱形醫療通脹")
            knowledge = st.text_area("專業知識點", height=80)
            story_context = st.text_area("真實故事背景", height=80)
            c_night, c_dream = st.columns(2)
            nightmare = c_night.text_area("噩夢畫面", height=140)
            dream = c_dream.text_area("美夢畫面", height=140)
            scenario = st.text_input("實戰場景")
            if st.form_submit_button("儲存知識素材", type="primary"):
                if title and knowledge and story_context:
                    add_ammo(
                        st.session_state["user"],
                        d,
                        cat,
                        title,
                        knowledge,
                        story_context,
                        nightmare,
                        dream,
                        scenario,
                    )
                    st.toast("知識點提交成功！", icon="💥")
                else:
                    st.error("「標題」「知識點」「真實故事」必填")

    with tab_library:
        df_ammo = read_data("story_ammo")
        if df_ammo.empty or "knowledge" not in df_ammo.columns:
            st.info("武器庫仲係空 — 提交第一批素材啦。")
            return
        df_ammo = df_ammo.drop_duplicates(subset=["id"], keep="first").sort_values(
            by="id", ascending=False
        )
        col_s, col_f = st.columns([2, 1])
        search_kw = col_s.text_input("關鍵字搜尋", placeholder="標題或故事…")
        filter_cat = col_f.selectbox("分類", ["全部"] + df_ammo["category"].unique().tolist())
        filtered = df_ammo
        if filter_cat != "全部":
            filtered = filtered[filtered["category"] == filter_cat]
        if search_kw:
            filtered = filtered[
                filtered["title"].str.contains(search_kw, na=False)
                | filtered["knowledge"].str.contains(search_kw, na=False)
                | filtered["story_context"].str.contains(search_kw, na=False)
            ]
        st.caption(f"武器庫存量：{len(filtered)}")
        for _, row in filtered.iterrows():
            with st.expander(f"[{row['category']}] {row['title']}  ·  {row['username']}"):
                st.markdown(f"**專業知識點：**\n{row['knowledge']}")
                st.markdown(f"**真實故事：**\n{row['story_context']}")
                c_n, c_d = st.columns(2)
                with c_n:
                    if row.get("nightmare"):
                        st.markdown(
                            f"<div class='ammo-nightmare'><strong>噩夢：</strong><br>{row['nightmare']}</div>",
                            unsafe_allow_html=True,
                        )
                    else:
                        st.warning("噩夢畫面待 Training 討論")
                with c_d:
                    if row.get("dream"):
                        st.markdown(
                            f"<div class='ammo-dream'><strong>美夢：</strong><br>{row['dream']}</div>",
                            unsafe_allow_html=True,
                        )
                    else:
                        st.warning("美夢畫面待 Training 討論")
                st.caption(f"場景：{row.get('scenario','')} · {row.get('date','')}")


def page_profile():
    st.markdown("## 個人設定")
    col1, col2 = st.columns([1, 2])
    with col1:
        if st.session_state.get("avatar"):
            st.image(st.session_state["avatar"], width=150)
    with col2:
        st.markdown(f"### {st.session_state['user']}")
        st.markdown(f"**Role:** {st.session_state['role']}")
        with st.expander("更改密碼"):
            new_pw = st.text_input("新密碼", type="password")
            if st.button("更新密碼"):
                update_pw(st.session_state["user"], new_pw)
                st.toast("Password Updated!", icon="✅")
        with st.expander("更改頭像"):
            uploaded_file = st.file_uploader("Upload Image", type=["jpg", "png", "jpeg"])
            if uploaded_file is not None and st.button("Upload"):
                img_str = proc_img(uploaded_file)
                if img_str:
                    update_avt(st.session_state["user"], img_str)
                    st.session_state["avatar"] = img_str
                    st.toast("Avatar Updated!", icon="✅")
                    st.rerun()


# ─── Router ──────────────────────────────────────────────────────────────────
if "我的主頁" in menu:
    page_home()
elif "打卡" in menu:
    page_checkin()
elif "Dashboard" in menu:
    page_dashboard()
elif "Iris" in menu:
    if is_leader:
        page_iris_sync()
    else:
        st.warning("只有 Leader 可以同步 Iris 業績")
elif "每月" in menu:
    page_monthly()
elif "年度" in menu:
    page_year_goal()
elif "每週" in menu:
    page_challenge()
elif "招募" in menu:
    page_recruit()
elif "彈藥庫" in menu:
    page_ammo()
elif "設定" in menu:
    page_profile()
