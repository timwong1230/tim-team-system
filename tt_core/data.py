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


def _act_points(t: str) -> int:
    if "出code" in t or "出 Code" in t:
        return 8
    if "簽單" in t:
        return 5
    if "報考試" in t:
        return 3
    if "傾" in t:
        return 2
    return 1


def add_act(u, d, t, n):
    run_query_gs(
        "INSERT",
        "activities",
        {
            "username": u,
            "date": str(d),
            "type": t,
            "points": _act_points(t),
            "note": n,
            "timestamp": str(datetime.datetime.now()),
        },
    )


def compose_pipeline_note(
    *,
    track: str,
    person: str,
    stage: str,
    next_action: str,
    next_date,
    factfind: str,
) -> str:
    """Structured note for activity feed + searchable follow-up context."""
    nd = str(next_date)
    header = (
        f"【{track}｜{stage}】{person}\n"
        f"Next action: {next_action}\n"
        f"跟進日期: {nd}\n"
    )
    body = (factfind or "").strip()
    return f"{header}\n{body}" if body else header


def add_pipeline_checkin(
    username: str,
    *,
    act_date,
    act_type: str,
    track: str,
    person: str,
    stage: str,
    next_action: str,
    next_date,
    factfind: str,
) -> None:
    """Log activity points + open a follow-up for the home action list."""
    person = str(person or "").strip()
    stage = str(stage or "").strip()
    next_action = str(next_action or "").strip()
    if not person or not stage or not next_action or not next_date:
        raise ValueError("必須填寫對象、階段、Next action、跟進日期")

    note = compose_pipeline_note(
        track=track,
        person=person,
        stage=stage,
        next_action=next_action,
        next_date=next_date,
        factfind=factfind,
    )
    add_act(username, act_date, act_type, note)
    close_open_followups(username, person, track)
    now = str(datetime.datetime.now())
    run_query_gs(
        "INSERT",
        "followups",
        {
            "username": username,
            "track": track,
            "person": person,
            "stage": stage,
            "next_action": next_action,
            "next_date": str(next_date),
            "status": "open",
            "act_type": act_type,
            "note": note,
            "created_at": now,
            "updated_at": now,
        },
    )


def get_followups(username: str | None = None) -> pd.DataFrame:
    df = read_data("followups")
    cols = [
        "id",
        "username",
        "track",
        "person",
        "stage",
        "next_action",
        "next_date",
        "status",
        "act_type",
        "note",
        "created_at",
        "updated_at",
    ]
    if df is None or df.empty:
        return pd.DataFrame(columns=cols)
    for c in cols:
        if c not in df.columns:
            df[c] = ""
    work = df.copy()
    work["status"] = work["status"].astype(str).str.strip().str.lower()
    work["next_date"] = pd.to_datetime(work["next_date"], errors="coerce")
    if username:
        work = work[work["username"].astype(str) == str(username)]
    return work


def get_due_followups(username: str, *, on_or_before=None) -> pd.DataFrame:
    """Open follow-ups due on/before date (default: today) — 今日要跟."""
    today = on_or_before or datetime.date.today()
    cutoff = pd.Timestamp(today)
    df = get_followups(username)
    if df.empty:
        return df
    open_df = df[df["status"] == "open"].copy()
    if open_df.empty:
        return open_df
    due = open_df[open_df["next_date"].notna() & (open_df["next_date"] <= cutoff)]
    return due.sort_values(by=["next_date", "person"], ascending=True)


def get_upcoming_followups(
    username: str, *, days: int = 7, after=None
) -> pd.DataFrame:
    """Open follow-ups after `after` (default today) within N days."""
    start = pd.Timestamp(after or datetime.date.today())
    end = start + pd.Timedelta(days=days)
    df = get_followups(username)
    if df.empty:
        return df
    open_df = df[df["status"] == "open"].copy()
    upcoming = open_df[
        open_df["next_date"].notna()
        & (open_df["next_date"] > start)
        & (open_df["next_date"] <= end)
    ]
    return upcoming.sort_values(by=["next_date", "person"], ascending=True)


def close_open_followups(username: str, person: str, track: str | None = None) -> int:
    """Mark previous open follow-ups for same person as done (replaced by newer check-in)."""
    df = get_followups(username)
    if df.empty:
        return 0
    mask = (df["status"] == "open") & (df["person"].astype(str).str.strip() == str(person).strip())
    if track:
        mask = mask & (df["track"].astype(str) == str(track))
    closed = 0
    now = str(datetime.datetime.now())
    for _, row in df[mask].iterrows():
        rid = row.get("id")
        if rid is None or str(rid).strip() == "":
            continue
        run_query_gs(
            "UPDATE",
            "followups",
            {"status": "done", "updated_at": now},
            row_id=rid,
        )
        closed += 1
    return closed


def mark_followup_done(followup_id) -> bool:
    return bool(
        run_query_gs(
            "UPDATE",
            "followups",
            {"status": "done", "updated_at": str(datetime.datetime.now())},
            row_id=followup_id,
        )
    )


def _quarterly_sheet_items(quarter: str, kind: str) -> list[dict]:
    q = str(quarter or "").strip().upper()
    k = str(kind or "").strip().lower()
    try:
        df = read_data("quarterly_offers")
    except Exception:
        return []
    if df is None or df.empty or "quarter" not in df.columns:
        return []
    work = df.copy()
    work["quarter"] = work["quarter"].astype(str).str.strip().str.upper()
    work["kind"] = work["kind"].astype(str).str.strip().str.lower()
    hit = work[(work["quarter"] == q) & (work["kind"] == k)]
    if hit.empty:
        return []
    rows = []
    for _, r in hit.iterrows():
        title = str(r.get("title", "") or "").strip()
        if not title:
            continue
        rows.append(
            {
                "id": r.get("id", ""),
                "title": title,
                "detail": str(r.get("detail", "") or "").strip(),
                "note": str(r.get("note", "") or "").strip(),
                "sort": int(pd.to_numeric(r.get("sort", 0), errors="coerce") or 0),
            }
        )
    return sorted(rows, key=lambda x: x["sort"])


def get_quarterly_offer_items(quarter: str, kind: str) -> list[dict]:
    """Sheet rows override defaults when that quarter+kind has any saved rows."""
    from tt_core.quarterly_offers import default_items

    q = str(quarter or "").strip().upper()
    k = str(kind or "").strip().lower()
    if k not in {"customer", "agent"}:
        return []
    sheet_items = _quarterly_sheet_items(q, k)
    if sheet_items:
        return sheet_items
    return default_items(q, k)


def get_quarterly_catalog(quarter: str, kind: str) -> dict:
    """Table-ready catalog: banner + sections[{title, columns, rows}]."""
    q = str(quarter or "").strip().upper()
    k = str(kind or "").strip().lower()
    empty = {"banner": "", "footnote": "", "sections": []}
    if k not in {"customer", "agent"}:
        return empty

    sheet_items = _quarterly_sheet_items(q, k)
    if sheet_items:
        try:
            from tt_core.quarterly_offers import catalog_from_flat_items

            cat = catalog_from_flat_items(sheet_items, kind=k)
            if cat.get("sections"):
                return cat
        except Exception:
            pass

    try:
        from tt_core.quarterly_offers import default_catalog

        cat = default_catalog(q, k)
        if isinstance(cat, dict) and cat.get("sections"):
            return cat
    except Exception:
        pass

    try:
        from tt_core import quarterly_offers as qo

        root = getattr(qo, "DEFAULT_CATALOG", None) or getattr(qo, "DEFAULT_OFFERS", None) or {}
        block = (root.get(q) or {}).get(k)
        if isinstance(block, dict) and block.get("sections"):
            return {
                "banner": str(block.get("banner", "") or ""),
                "footnote": str(block.get("footnote", "") or ""),
                "sections": list(block.get("sections") or []),
            }
        if isinstance(block, list) and block:
            rows = [
                [
                    str(x.get("title", "") or ""),
                    str(x.get("detail", "") or ""),
                    str(x.get("note", "") or ""),
                ]
                for x in block
                if isinstance(x, dict) and str(x.get("title", "") or "").strip()
            ]
            if rows:
                return {
                    "banner": "",
                    "footnote": "",
                    "sections": [
                        {
                            "title": "客戶優惠" if k == "customer" else "營業員獎賞",
                            "columns": ["項目", "詳情", "備註"],
                            "rows": rows,
                        }
                    ],
                }
    except Exception:
        pass
    return empty


def add_quarterly_offer(quarter: str, kind: str, title: str, detail: str, note: str = "", sort: int = 0) -> bool:
    return bool(
        run_query_gs(
            "INSERT",
            "quarterly_offers",
            {
                "quarter": str(quarter).strip().upper(),
                "kind": str(kind).strip().lower(),
                "title": str(title or "").strip(),
                "detail": str(detail or "").strip(),
                "note": str(note or "").strip(),
                "sort": int(sort or 0),
                "updated_at": str(datetime.datetime.now()),
            },
        )
    )


def delete_quarterly_offer(row_id) -> bool:
    if row_id is None or str(row_id).strip() == "":
        return False
    return bool(run_query_gs("DELETE", "quarterly_offers", row_id=row_id))


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
    # Literals first so a stale constants.py on Streamlit Cloud cannot break import/runtime
    iris_ytd_key = "YTD"
    mdrt_progress_key = "MDRT_2027"
    try:
        from tt_core.constants import IRIS_YTD_MONTH_KEY, MDRT_PROGRESS_MONTH_KEY

        iris_ytd_key = IRIS_YTD_MONTH_KEY
        mdrt_progress_key = MDRT_PROGRESS_MONTH_KEY
    except Exception:
        pass

    base_columns = ["username", "team", "recruit", "avatar", "fyc", "Total_Score"]
    users = get_clean_users()
    users = users[users["role"] == "Member"][["username", "team", "recruit", "avatar"]]
    if users.empty:
        return pd.DataFrame(columns=base_columns)

    fyc_df, act_df = read_data("monthly_fyc"), read_data("activities")
    special_months = {iris_ytd_key, mdrt_progress_key}

    if not fyc_df.empty and "amount" in fyc_df.columns:
        fyc_df["month"] = fyc_df["month"].astype(str).str.strip()
        fyc_df["amount"] = pd.to_numeric(fyc_df["amount"], errors="coerce").fillna(0)
        if month == "Yearly":
            # Prefer Iris YTD Completion rows for member FYC reference
            ytd = fyc_df[fyc_df["month"] == iris_ytd_key]
            if not ytd.empty:
                fyc = (
                    ytd.groupby("username")["amount"]
                    .max()
                    .reset_index()
                    .rename(columns={"amount": "fyc"})
                )
            else:
                # Fallback: sum monthly completions (exclude special keys)
                months_only = fyc_df[~fyc_df["month"].isin(special_months)]
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


def get_mdrt_progress_map() -> dict[str, float]:
    """Per-member 2027 MDRT temporary progress (plan bonus + other credit)."""
    fyc_df = read_data("monthly_fyc")
    if fyc_df is None or fyc_df.empty or "amount" not in fyc_df.columns:
        return {}
    fyc_df = fyc_df.copy()
    fyc_df["month"] = fyc_df["month"].astype(str).str.strip()
    fyc_df["amount"] = pd.to_numeric(fyc_df["amount"], errors="coerce").fillna(0)
    rows = fyc_df[fyc_df["month"] == "MDRT_2027"]
    if rows.empty:
        return {}
    grouped = rows.groupby("username")["amount"].max()
    return {str(k).strip(): float(v) for k, v in grouped.items()}


def lookup_mdrt_progress(username: str, progress_map: dict[str, float] | None = None) -> float:
    """Leaderboard / home shared lookup for MDRT_2027 amount."""
    if progress_map is None:
        progress_map = get_mdrt_progress_map()
    key = str(username or "").strip()
    if not key:
        return 0.0
    if key in progress_map:
        return float(progress_map[key])
    lower = {str(k).strip().lower(): float(v) for k, v in progress_map.items()}
    return float(lower.get(key.lower(), 0.0))


def mdrt_card_metrics(username: str, progress_map: dict[str, float] | None = None) -> dict:
    """Home card metrics — same progress number as Leaderboard."""
    progress = lookup_mdrt_progress(username, progress_map)
    target = float(MDRT_TARGET) if MDRT_TARGET else 0.0
    pct = min(progress / target * 100, 100.0) if target else 0.0
    remaining = max(target - progress, 0.0)
    return {
        "mdrt_progress": progress,
        "mdrt_pct": pct,
        "mdrt_remaining": remaining,
        "mdrt_met": bool(target > 0 and progress >= target),
    }


def set_mdrt_progress(username: str, amount: float) -> None:
    upd_fyc(username, "MDRT_2027", float(amount), source="mdrt_progress")


def get_q1_data() -> pd.DataFrame:
    users = get_clean_users()
    users = users[users["role"] == "Member"][["username", "avatar"]]
    if users.empty:
        return pd.DataFrame(columns=["username", "q1_total"])

    fyc_df = read_data("monthly_fyc")
    if not fyc_df.empty:
        fyc_df["month"] = fyc_df["month"].astype(str).str.strip()
        fyc_df["amount"] = pd.to_numeric(fyc_df["amount"], errors="coerce").fillna(0)
        q1 = fyc_df[
            fyc_df["month"].isin(["2026-01", "2026-02", "2026-03"])
            & (~fyc_df["month"].isin({"YTD", "MDRT_2027"}))
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
    # Same MDRT_2027 credit as Leaderboard (never substitute YTD FYC)
    mdrt = mdrt_card_metrics(username)
    return {
        "fyc": fyc,
        "mdrt_progress": mdrt["mdrt_progress"],
        "mdrt_pct": mdrt["mdrt_pct"],
        "mdrt_remaining": mdrt["mdrt_remaining"],
        "mdrt_met": mdrt["mdrt_met"],
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


def _activities_to_plain_rows(df) -> list[dict]:
    """Plain dict rows only — never put a DataFrame in session_state (Cloud crash risk)."""
    rows: list[dict] = []
    if df is None or getattr(df, "empty", True):
        return rows
    for _, row in df.iterrows():
        ts = row.get("timestamp", "")
        try:
            act_time = (
                pd.to_datetime(ts).strftime("%m/%d %H:%M") if ts not in ("", None) else str(row.get("date", "") or "")
            )
        except Exception:
            act_time = str(row.get("date", "") or "")
        rows.append(
            {
                "username": str(row.get("username", "") or ""),
                "type": str(row.get("type", "") or ""),
                "note": str(row.get("note", "") or ""),
                "when": act_time,
            }
        )
    return rows


def show_notification_banner(rows, current_user):
    """Inline banner only — avoid @st.dialog (Cloud Oh-no crash risk)."""
    with st.container(border=True):
        st.markdown(f"### 團隊最新戰報")
        st.markdown(f"**Hi {current_user}，你不在的時候，團隊發生了以下動態：**")
        for row in (rows or [])[:20]:
            st.info(
                f"**{row.get('username', '')}** — {row.get('type', '')}\n\n"
                f"{row.get('note', '')}\n\n*{row.get('when', '')}*"
            )
        if st.button("收到，知道了", type="primary", use_container_width=True, key="_notif_ack"):
            update_last_read_time(current_user)
            st.session_state["_notif_pending_payload"] = None
            st.session_state["_notif_checked_this_login"] = True
            st.rerun()


def scrub_notification_session_state():
    """Drop legacy DataFrame / corrupt notification payloads from session_state."""
    pending = st.session_state.get("_notif_pending_payload")
    if pending is None:
        return
    if isinstance(pending, list):
        return
    # Old builds stored a DataFrame here — that can hard-crash Streamlit Cloud
    st.session_state["_notif_pending_payload"] = None


def check_notifications(current_user: str):
    """Show unread check-in feed at most once per login session."""
    if not current_user:
        return
    try:
        scrub_notification_session_state()
        # Keep banner open across reruns until user dismisses it
        pending = st.session_state.get("_notif_pending_payload")
        if isinstance(pending, list) and pending:
            show_notification_banner(pending, current_user)
            return

        # Already handled this login — never pop again while browsing
        if st.session_state.get("_notif_checked_this_login"):
            return

        users_df = get_clean_users()
        act_df = read_data("activities")
        if users_df.empty or act_df.empty:
            st.session_state["_notif_checked_this_login"] = True
            return
        user_record = users_df[users_df["username"] == current_user]
        if user_record.empty:
            st.session_state["_notif_checked_this_login"] = True
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
            st.session_state["_notif_checked_this_login"] = True
            return
        act_df = act_df.copy()
        act_df["timestamp_dt"] = pd.to_datetime(act_df["timestamp"], errors="coerce")
        new_activities = act_df[
            (act_df["timestamp_dt"] > last_read)
            & (act_df["username"] != current_user)
            & (~act_df["username"].isin(INACTIVE_MEMBERS))
        ]
        st.session_state["_notif_checked_this_login"] = True
        rows = _activities_to_plain_rows(new_activities)
        if rows:
            st.session_state["_notif_pending_payload"] = rows
            show_notification_banner(rows, current_user)
        else:
            update_last_read_time(current_user)
    except Exception:
        # Never let the login banner take down the whole app
        st.session_state["_notif_checked_this_login"] = True
        st.session_state["_notif_pending_payload"] = None


def get_activity_style(act_type: str):
    if "簽單" in act_type:
        return "card-signed", "badge-signed"
    if "見面" in act_type or "傾" in act_type:
        return "card-meeting", "badge-meeting"
    if "招募" in act_type or "新人" in act_type:
        return "card-recruit", "badge-recruit"
    return "card-admin", "badge-default"


def get_note_template(act_type: str = "") -> str:
    """Both 做數 and 招募 use the same 15-question Fact find template."""
    import importlib

    import tt_core.constants as _c

    _c = importlib.reload(_c)
    return getattr(_c, "TEMPLATE_FACTFIND", None) or _c.TEMPLATE_SALES


def track_for_activity(act_type: str) -> str:
    from tt_core.constants import TRACK_RECRUIT, TRACK_SALES

    if any(k in act_type for k in ("招募", "新人", "出code", "報考試")):
        return TRACK_RECRUIT
    return TRACK_SALES


def last_iris_sync():
    log = read_data("iris_sync_log")
    if log.empty:
        return None
    log = log.sort_values(by="id", ascending=False)
    return log.iloc[0].to_dict()
