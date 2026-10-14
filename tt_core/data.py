"""Business logic for TIM TEAM metrics and activities."""

from __future__ import annotations

import base64
import datetime
import io

import pandas as pd
import streamlit as st
from PIL import Image

from tt_core.constants import INACTIVE_MEMBERS, MDRT_TARGET
from tt_core.db import read_data, run_query_gs, update_user_field


def get_clean_users() -> pd.DataFrame:
    df = read_data("users")
    if df.empty:
        return pd.DataFrame(
            columns=["username", "password", "role", "team", "recruit", "avatar", "last_read"]
        )
    df = df.drop_duplicates(subset=["username"], keep="first")
    return df[~df["username"].isin(INACTIVE_MEMBERS)]


def login(u: str, p: str):
    df = get_clean_users()
    if df.empty:
        return []
    df["password"] = df["password"].astype(str)
    user = df[(df["username"] == u) & (df["password"] == str(p))]
    return user.values.tolist() if not user.empty else []


def proc_img(f):
    try:
        image = Image.open(f)
        if image.mode in ("RGBA", "P"):
            image = image.convert("RGB")
        image = image.resize((100, 100))
        buf = io.BytesIO()
        image.save(buf, format="JPEG", quality=80)
        return f"data:image/jpeg;base64,{base64.b64encode(buf.getvalue()).decode()}"
    except Exception:
        return None


def update_avt(u, i):
    update_user_field(u, "avatar", i)


def update_pw(u, p):
    update_user_field(u, "password", p)


def add_act(u, d, t, n):
    pts = (
        8
        if "出code" in t
        else 5
        if "簽單" in t
        else 3
        if "報考試" in t
        else 2
        if "傾" in t
        else 1
    )
    run_query_gs(
        "INSERT",
        "activities",
        {
            "username": u,
            "date": str(d),
            "type": t,
            "points": pts,
            "note": n,
            "timestamp": str(datetime.datetime.now()),
        },
    )


def add_ammo(u, d, cat, title, knowledge, story_context, nightmare, dream, scenario):
    run_query_gs(
        "INSERT",
        "story_ammo",
        {
            "username": u,
            "date": str(d),
            "category": cat,
            "title": title,
            "knowledge": knowledge,
            "story_context": story_context,
            "nightmare": nightmare,
            "dream": dream,
            "scenario": scenario,
            "timestamp": str(datetime.datetime.now()),
        },
    )


def get_team_sc(fallback: float | None = None) -> float:
    """Team SC shown on Dashboard — manual value, else optional fallback."""
    from tt_core.constants import TEAM_SC_SETTING_KEY
    from tt_core.iris_drive import get_setting

    raw = str(get_setting(TEAM_SC_SETTING_KEY, "") or "").strip()
    if raw:
        try:
            return float(str(raw).replace(",", "").replace("$", "").replace("HK$", ""))
        except ValueError:
            pass
    return float(fallback or 0)


def set_team_sc(amount: float) -> bool:
    from tt_core.constants import TEAM_SC_SETTING_KEY
    from tt_core.iris_drive import set_setting

    return bool(set_setting(TEAM_SC_SETTING_KEY, str(float(amount))))


def upd_fyc(u, m, a, source: str = "manual"):
    df = read_data("monthly_fyc")
    now = str(datetime.datetime.now())
    if not df.empty:
        df["month"] = df["month"].astype(str).str.strip()
    exist = df[(df["username"] == u) & (df["month"] == str(m))] if not df.empty else pd.DataFrame()
    payload = {"amount": a, "source": source, "updated_at": now}
    if not exist.empty:
        run_query_gs("UPDATE", "monthly_fyc", payload, row_id=exist.iloc[0]["id"])
    else:
        run_query_gs(
            "INSERT",
            "monthly_fyc",
            {"username": u, "month": str(m), "amount": a, **payload},
        )


def upd_rec(u, a):
    update_user_field(u, "recruit", a)


def del_act(act_id):
    run_query_gs("DELETE", "activities", row_id=act_id)


def get_all_act() -> pd.DataFrame:
    df = read_data("activities")
    if df.empty:
        return pd.DataFrame(
            columns=["id", "username", "date", "type", "points", "note", "timestamp"]
        )
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.drop_duplicates(subset=["username", "date", "type", "note"], keep="first")
    return df[~df["username"].isin(INACTIVE_MEMBERS)].sort_values(by="date", ascending=False)


def get_data(month=None) -> pd.DataFrame:
    from tt_core.constants import IRIS_YTD_MONTH_KEY

    base_columns = ["username", "team", "recruit", "avatar", "fyc", "Total_Score"]
    users = get_clean_users()
    users = users[users["role"] == "Member"][["username", "team", "recruit", "avatar"]]
    if users.empty:
        return pd.DataFrame(columns=base_columns)

    fyc_df, act_df = read_data("monthly_fyc"), read_data("activities")

    if not fyc_df.empty and "amount" in fyc_df.columns:
        fyc_df["month"] = fyc_df["month"].astype(str).str.strip()
        fyc_df["amount"] = pd.to_numeric(fyc_df["amount"], errors="coerce").fillna(0)
        if month == "Yearly":
            # Prefer Iris YTD Completion rows for Team FYC / MDRT progress
            ytd = fyc_df[fyc_df["month"] == IRIS_YTD_MONTH_KEY]
            if not ytd.empty:
                fyc = (
                    ytd.groupby("username")["amount"]
                    .max()
                    .reset_index()
                    .rename(columns={"amount": "fyc"})
                )
            else:
                # Fallback: sum monthly completions (exclude YTD key)
                months_only = fyc_df[fyc_df["month"] != IRIS_YTD_MONTH_KEY]
                fyc = (
                    months_only.groupby("username")["amount"]
                    .sum()
                    .reset_index()
                    .rename(columns={"amount": "fyc"})
                )
        else:
            fyc = fyc_df[fyc_df["month"] == str(month)][["username", "amount"]].rename(
                columns={"amount": "fyc"}
            )
    else:
        fyc = pd.DataFrame(columns=["username", "fyc"])

    if not act_df.empty and "points" in act_df.columns:
        act_df["points"] = pd.to_numeric(act_df["points"], errors="coerce").fillna(0)
        act = (
            act_df.groupby("username")["points"]
            .sum()
            .reset_index()
            .rename(columns={"points": "Total_Score"})
        )
    else:
        act = pd.DataFrame(columns=["username", "Total_Score"])

    df = pd.merge(users, fyc, on="username", how="left").fillna(0)
    df = pd.merge(df, act, on="username", how="left").fillna(0)
    df["fyc"] = pd.to_numeric(df["fyc"], errors="coerce").fillna(0).astype(float)
    df["Total_Score"] = pd.to_numeric(df["Total_Score"], errors="coerce").fillna(0).astype(int)
    df["recruit"] = pd.to_numeric(df["recruit"], errors="coerce").fillna(0).astype(int)
    return df


def get_q1_data() -> pd.DataFrame:
    users = get_clean_users()
    users = users[users["role"] == "Member"][["username", "avatar"]]
    if users.empty:
        return pd.DataFrame(columns=["username", "q1_total"])

    from tt_core.constants import IRIS_YTD_MONTH_KEY

    fyc_df = read_data("monthly_fyc")
    if not fyc_df.empty:
        fyc_df["month"] = fyc_df["month"].astype(str).str.strip()
        fyc_df["amount"] = pd.to_numeric(fyc_df["amount"], errors="coerce").fillna(0)
        q1 = fyc_df[
            fyc_df["month"].isin(["2026-01", "2026-02", "2026-03"])
            & (fyc_df["month"] != IRIS_YTD_MONTH_KEY)
        ]
        q1_sum = (
            q1.groupby("username")["amount"]
            .sum()
            .reset_index()
            .rename(columns={"amount": "q1_total"})
        )
        return pd.merge(users, q1_sum, on="username", how="left").fillna(0)
    return pd.DataFrame(columns=["username", "q1_total"])


def _week_stats(start: datetime.date, end: datetime.date | None = None):
    users = get_clean_users()
    users = users[users["role"] == "Member"][["username", "avatar"]]
    if users.empty:
        return pd.DataFrame(columns=["username", "wk_score", "wk_count"])

    act_df = read_data("activities")
    stats = pd.DataFrame(columns=["username", "wk_score", "wk_count"])
    if not act_df.empty:
        act_df["date"] = pd.to_datetime(act_df["date"], errors="coerce").dt.date
        act_df["points"] = pd.to_numeric(act_df["points"], errors="coerce").fillna(0).astype(int)
        mask = act_df["date"] >= start
        if end is not None:
            mask = mask & (act_df["date"] <= end)
        period = act_df[mask]
        if not period.empty:
            stats = (
                period.groupby("username")
                .agg(wk_score=("points", "sum"), wk_count=("points", "count"))
                .reset_index()
            )
    return pd.merge(users, stats, on="username", how="left").fillna(0)


def get_last_week_data():
    today = datetime.date.today()
    current_week_monday = today - datetime.timedelta(days=today.weekday())
    start = current_week_monday - datetime.timedelta(days=7)
    end = start + datetime.timedelta(days=6)
    return _week_stats(start, end), start, end


def get_weekly_data():
    today = datetime.date.today()
    start = today - datetime.timedelta(days=today.weekday())
    return _week_stats(start, None), start, today


def get_member_snapshot(username: str) -> dict:
    """Personal desk metrics for a member."""
    yearly = get_data("Yearly")
    weekly, wk_start, wk_end = get_weekly_data()
    me_year = yearly[yearly["username"] == username]
    me_week = weekly[weekly["username"] == username]
    fyc = float(me_year.iloc[0]["fyc"]) if not me_year.empty else 0.0
    score = int(me_year.iloc[0]["Total_Score"]) if not me_year.empty else 0
    recruit = int(me_year.iloc[0]["recruit"]) if not me_year.empty else 0
    wk_score = int(me_week.iloc[0]["wk_score"]) if not me_week.empty else 0
    wk_count = int(me_week.iloc[0]["wk_count"]) if not me_week.empty else 0
    return {
        "fyc": fyc,
        "mdrt_pct": min(fyc / MDRT_TARGET * 100, 100) if MDRT_TARGET else 0,
        "score": score,
        "recruit": recruit,
        "wk_score": wk_score,
        "wk_count": wk_count,
        "wk_start": wk_start,
        "wk_end": wk_end,
        "team_fyc": float(yearly["fyc"].sum()) if not yearly.empty else 0.0,
        "team_acts": int(yearly["Total_Score"].sum()) if not yearly.empty else 0,
    }


def update_last_read_time(username: str):
    try:
        update_user_field(username, "last_read", str(datetime.datetime.now()))
    except Exception:
        pass


@st.dialog("團隊最新戰報")
def show_notification_modal(new_activities, current_user):
    st.markdown(f"**Hi {current_user}，你不在的時候，團隊發生了以下動態：**")
    for _, row in new_activities.iterrows():
        act_time = (
            pd.to_datetime(row["timestamp"]).strftime("%m/%d %H:%M")
            if row["timestamp"]
            else row["date"]
        )
        st.info(f"**{row['username']}** — {row['type']}\n\n{row['note']}\n\n*{act_time}*")
    st.markdown("---")
    if st.button("收到，知道了", type="primary", use_container_width=True):
        update_last_read_time(current_user)
        st.rerun()


def check_notifications(current_user: str):
    users_df = get_clean_users()
    act_df = read_data("activities")
    if users_df.empty or act_df.empty:
        return
    user_record = users_df[users_df["username"] == current_user]
    if user_record.empty:
        return
    last_read_str = str(user_record.iloc[0].get("last_read", ""))
    try:
        last_read = (
            pd.to_datetime(last_read_str)
            if last_read_str and last_read_str != ""
            else pd.to_datetime("2020-01-01")
        )
    except Exception:
        last_read = pd.to_datetime("2020-01-01")
    if "timestamp" not in act_df.columns:
        return
    act_df["timestamp_dt"] = pd.to_datetime(act_df["timestamp"], errors="coerce")
    new_activities = act_df[
        (act_df["timestamp_dt"] > last_read)
        & (act_df["username"] != current_user)
        & (~act_df["username"].isin(INACTIVE_MEMBERS))
    ]
    if not new_activities.empty:
        show_notification_modal(new_activities, current_user)


def get_activity_style(act_type: str):
    if "簽單" in act_type:
        return "card-signed", "badge-signed"
    if "見面" in act_type or "傾" in act_type:
        return "card-meeting", "badge-meeting"
    if "招募" in act_type or "新人" in act_type:
        return "card-recruit", "badge-recruit"
    return "card-admin", "badge-default"


def get_note_template(act_type: str) -> str:
    from tt_core.constants import TEMPLATE_NEWBIE, TEMPLATE_RECRUIT, TEMPLATE_SALES

    if "招募" in act_type:
        return TEMPLATE_RECRUIT
    if "新人" in act_type:
        return TEMPLATE_NEWBIE
    return TEMPLATE_SALES


def last_iris_sync():
    log = read_data("iris_sync_log")
    if log.empty:
        return None
    log = log.sort_values(by="id", ascending=False)
    return log.iloc[0].to_dict()
