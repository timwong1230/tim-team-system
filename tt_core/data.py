"""Business logic for TIM TEAM metrics and activities."""

from __future__ import annotations

import base64
import datetime
import io

import pandas as pd
import streamlit as st
from PIL import Image

from tt_core.constants import (
    CHECKIN_CHALLENGE_SKIP,
    GUEST_PASSWORD,
    GUEST_ROLE,
    GUEST_USERNAMES,
    INACTIVE_MEMBERS,
    MDRT_TARGET,
    RECRUIT_YEAR_TARGET,
    SEED_USERS,
    SHEET_SCHEMAS,
    WEEKLY_MIN_ACTS,
)
from tt_core.db import read_data, run_query_gs, update_user_field


def is_guest_account(username: str = "", role: str = "") -> bool:
    """Trial guest — login OK, hidden from team ops lists."""
    u = str(username or "").strip().lower()
    r = str(role or "").strip().lower()
    return u in {x.lower() for x in GUEST_USERNAMES} or r == GUEST_ROLE.lower()


def _guest_avatar_url() -> str:
    return "https://ui-avatars.com/api/?name=guest&background=d4af37&color=fff&size=128"


def builtin_guest_row() -> list:
    """Canonical guest row for login when Sheets/cache has not seeded yet."""
    return [
        "guest",
        GUEST_PASSWORD,
        GUEST_ROLE,
        "Tim Team",
        0,
        _guest_avatar_url(),
        "",
    ]


def _normalize_password_cell(value) -> str:
    """Sheets sometimes stores 1234 as float → '1234.0'."""
    text = str(value if value is not None else "").strip()
    if text.endswith(".0") and text[:-2].isdigit():
        return text[:-2]
    return text


def get_clean_users() -> pd.DataFrame:
    """Active accounts that may log in (includes Guest trial users)."""
    df = read_data("users")
    if df.empty:
        return pd.DataFrame(
            columns=["username", "password", "role", "team", "recruit", "avatar", "last_read"]
        )
    df = df.drop_duplicates(subset=["username"], keep="first")
    return df[~df["username"].isin(INACTIVE_MEMBERS)]


def get_team_users() -> pd.DataFrame:
    """Roster for 打卡／業績／招募 — excludes Guest trial accounts."""
    df = get_clean_users()
    if df.empty:
        return df
    guest_names = {x.lower() for x in GUEST_USERNAMES}
    mask = df["username"].astype(str).str.strip().str.lower().isin(guest_names)
    if "role" in df.columns:
        mask = mask | (df["role"].astype(str).str.strip().str.lower() == GUEST_ROLE.lower())
    return df[~mask].copy()


def _seed_user_row(username: str, password: str, role: str) -> list:
    url = (
        f"https://ui-avatars.com/api/?name={username}"
        f"&background=d4af37&color=fff&size=128"
    )
    return [username, password, role, "Tim Team", 0, url, ""]


def ensure_seed_users(*, only: str | None = None) -> bool:
    """Append missing SEED_USERS (e.g. KK) to Sheets + local users cache."""
    try:
        from tt_core import cache_store
        from tt_core.db import get_sheet
    except Exception:
        cache_store = None  # type: ignore
        get_sheet = None  # type: ignore

    cols = SHEET_SCHEMAS.get(
        "users",
        ["username", "password", "role", "team", "recruit", "avatar", "last_read"],
    )
    want = list(SEED_USERS)
    if only:
        key = str(only).strip().lower()
        want = [u for u in want if u[0].lower() == key]
        if not want:
            return False

    df = read_data("users")
    have = (
        set(df["username"].astype(str).str.strip().str.lower())
        if df is not None and not df.empty
        else set()
    )
    missing = [u for u in want if u[0].lower() not in have]
    if not missing and want:
        # Still present in cache — done
        if only:
            return True
        # Fall through only if we still need to sync Sheets for some
        pass

    if get_sheet is not None:
        try:
            ws = get_sheet("users")
            if ws:
                try:
                    existing = [str(x).strip().lower() for x in (ws.col_values(1) or [])]
                except Exception:
                    existing = []
                if not existing:
                    ws.append_row(cols, value_input_option="USER_ENTERED")
                    existing = ["username"]
                for username, password, role in want:
                    if username.lower() in existing:
                        continue
                    ws.append_row(
                        _seed_user_row(username, password, role),
                        value_input_option="USER_ENTERED",
                    )
                    existing.append(username.lower())
        except Exception:
            pass

    try:
        fresh = read_data("users", force=True)
    except Exception:
        fresh = df
    if fresh is None or getattr(fresh, "empty", True):
        fresh = pd.DataFrame(
            [_seed_user_row(u, p, r) for u, p, r in want],
            columns=cols,
        )
    else:
        names = set(fresh["username"].astype(str).str.strip().str.lower())
        extras = []
        for username, password, role in want:
            if username.lower() in names:
                continue
            extras.append(dict(zip(cols, _seed_user_row(username, password, role))))
        if extras:
            extra_df = pd.DataFrame(extras)
            for col in fresh.columns:
                if col not in extra_df.columns:
                    extra_df[col] = ""
            extra_df = extra_df.reindex(columns=list(fresh.columns), fill_value="")
            fresh = pd.concat([fresh, extra_df], ignore_index=True)
    try:
        if cache_store is not None:
            cache_store.invalidate_memory("users")
            cache_store.save_sheet("users", fresh, source="seed_users")
    except Exception:
        pass
    return True


def ensure_guest_user() -> bool:
    """Back-compat wrapper — seed the trial guest account."""
    return ensure_seed_users(only="guest")


def login(u: str, p: str):
    uname = str(u or "").strip()
    pw = str(p or "")

    def _match(frame: pd.DataFrame):
        if frame is None or frame.empty:
            return []
        frame = frame.copy()
        frame["password"] = frame["password"].map(_normalize_password_cell)
        hit = frame[
            (frame["username"].astype(str).str.strip().str.lower() == uname.lower())
            & (frame["password"] == pw)
        ]
        return hit.values.tolist() if not hit.empty else []

    rows = _match(get_clean_users())
    if rows:
        return rows

    # Seed known colleagues / guest into Sheets+cache, then retry
    seed_names = {u[0].lower() for u in SEED_USERS}
    if uname.lower() in seed_names:
        try:
            ensure_seed_users(only=uname)
        except Exception:
            pass
        rows = _match(get_clean_users())
        if rows:
            return rows
        # Last resort: accept seeded credentials even if cache still empty
        for username, password, role in SEED_USERS:
            if username.lower() == uname.lower() and password == pw:
                return [_seed_user_row(username, password, role)]

    # Built-in trial guest (explicit path kept for clarity)
    if is_guest_account(uname) and pw == GUEST_PASSWORD:
        return [builtin_guest_row()]
    return []


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


def get_due_followups(username: str | None = None, *, on_or_before=None) -> pd.DataFrame:
    """Open follow-ups due on/before date (default: today) — 今日要跟.

    Pass ``username=None`` for the whole team (Admin / Leader home).
    """
    today = on_or_before or datetime.date.today()
    cutoff = pd.Timestamp(today)
    df = get_followups(username)
    if df.empty:
        return df
    open_df = df[df["status"] == "open"].copy()
    if open_df.empty:
        return open_df
    due = open_df[open_df["next_date"].notna() & (open_df["next_date"] <= cutoff)]
    sort_cols = ["next_date", "username", "person"]
    sort_cols = [c for c in sort_cols if c in due.columns]
    return due.sort_values(by=sort_cols, ascending=True)


def get_upcoming_followups(
    username: str | None = None, *, days: int = 7, after=None
) -> pd.DataFrame:
    """Open follow-ups after `after` (default today) within N days.

    Pass ``username=None`` for the whole team (Admin / Leader home).
    """
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
    sort_cols = ["next_date", "username", "person"]
    sort_cols = [c for c in sort_cols if c in upcoming.columns]
    return upcoming.sort_values(by=sort_cols, ascending=True)


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


# Stages that usually need manager coaching when overdue
_STUCK_STAGE_REASONS = {
    "Handling Rejection": "卡喺抗拒處理",
    "Closing": "卡喺收單／Closing",
    "落 concept": "Concept 未跟進落實",
    "落 Sales Kit": "Sales Kit 已落未跟",
    "Fact finding": "Fact find 後未推進",
    "3Q": "3Q 後未約下一場",
    "見經理": "約見經理未完成",
    "報考試": "報考未跟進",
    "講 Recruitment Kit": "Recruitment Kit 後未跟",
    "Recruitment 3Q": "招募 3Q 後未約",
    "Fact Finding": "招募 Fact find 後未推進",
    "出 Code": "出 Code 前後需跟進",
}


def infer_stuck_reason(row: dict | pd.Series, *, today=None) -> str:
    """Human-readable 卡關原因 from stage + overdue days."""
    today = today or datetime.date.today()
    stage = str(row.get("stage") or "").strip()
    track = str(row.get("track") or "").strip()
    action = str(row.get("next_action") or "").strip()
    nd = row.get("next_date")
    overdue_days = 0
    try:
        if pd.notna(nd):
            d = pd.to_datetime(nd).date()
            overdue_days = max((today - d).days, 0)
    except Exception:
        overdue_days = 0

    bits: list[str] = []
    if overdue_days > 0:
        bits.append(f"過期 {overdue_days} 日未跟")
    elif overdue_days == 0 and pd.notna(nd):
        bits.append("今日到期要跟")

    stage_hint = _STUCK_STAGE_REASONS.get(stage)
    if stage_hint:
        bits.append(stage_hint)
    elif stage:
        bits.append(f"停留：{stage}")

    if track:
        bits.append(track)
    if action and len(bits) < 3:
        bits.append(f"Next：{action}")
    return " · ".join(bits) if bits else "待跟進"


def get_stuck_cases(
    username: str | None = None, *, on_or_before=None
) -> pd.DataFrame:
    """Open follow-ups due/overdue — the 卡案清單 for coach view."""
    today = on_or_before or datetime.date.today()
    due = get_due_followups(username, on_or_before=today) if username else None
    if username is None:
        # All members: filter open + due across sheet
        df = get_followups(None)
        if df.empty:
            return df
        cutoff = pd.Timestamp(today)
        open_df = df[df["status"] == "open"].copy()
        due = open_df[open_df["next_date"].notna() & (open_df["next_date"] <= cutoff)]
        due = due.sort_values(by=["next_date", "username", "person"], ascending=True)

    if due is None or due.empty:
        return due if due is not None else pd.DataFrame()

    work = due.copy()
    reasons = []
    overdue = []
    for _, row in work.iterrows():
        reasons.append(infer_stuck_reason(row, today=today))
        try:
            d = pd.to_datetime(row["next_date"]).date()
            overdue.append(max((today - d).days, 0))
        except Exception:
            overdue.append(0)
    work["stuck_reason"] = reasons
    work["overdue_days"] = overdue
    return work.sort_values(by=["overdue_days", "next_date"], ascending=[False, True])


def get_mtd_fyc(username: str, month: str | None = None) -> float:
    """Month-to-date completion FYC for one member."""
    m = month or datetime.date.today().strftime("%Y-%m")
    df = get_data(m)
    if df.empty:
        return 0.0
    hit = df[df["username"].astype(str) == str(username)]
    if hit.empty:
        return 0.0
    return float(hit.iloc[0].get("fyc") or 0)


def get_coach_member_pack(username: str, *, today=None) -> dict:
    """One-page coach pack: activity, FYC, stuck cases for a member."""
    today = today or datetime.date.today()
    month = today.strftime("%Y-%m")
    snap = get_member_snapshot(username)
    stuck = get_stuck_cases(username, on_or_before=today)
    mtd = get_mtd_fyc(username, month)
    open_all = get_followups(username)
    open_n = 0
    if not open_all.empty:
        open_n = int((open_all["status"] == "open").sum())
    return {
        "username": username,
        "wk_score": int(snap.get("wk_score") or 0),
        "wk_count": int(snap.get("wk_count") or 0),
        "wk_start": snap.get("wk_start"),
        "wk_end": snap.get("wk_end"),
        "mtd_fyc": mtd,
        "ytd_fyc": float(snap.get("fyc") or 0),
        "year_score": int(snap.get("score") or 0),
        "recruit": int(snap.get("recruit") or 0),
        "open_followups": open_n,
        "stuck_count": int(len(stuck)),
        "stuck_cases": stuck,
        "needs_acts": (
            int(snap.get("wk_count") or 0) < WEEKLY_MIN_ACTS
            and str(username or "").strip().lower()
            not in {x.lower() for x in CHECKIN_CHALLENGE_SKIP}
        ),
        "month": month,
    }


def get_team_coach_overview(*, today=None) -> pd.DataFrame:
    """Leader summary row per member for weekly challenge coach view."""
    today = today or datetime.date.today()
    users = get_team_users()
    if users.empty:
        return pd.DataFrame()
    members = users[users["role"] == "Member"]["username"].astype(str).tolist()
    weekly, _, _ = get_weekly_data()
    wk_map = {}
    if not weekly.empty:
        for _, r in weekly.iterrows():
            wk_map[str(r["username"])] = {
                "wk_score": int(r.get("wk_score") or 0),
                "wk_count": int(r.get("wk_count") or 0),
            }
    month = today.strftime("%Y-%m")
    mtd_df = get_data(month)
    mtd_map = {}
    if not mtd_df.empty:
        for _, r in mtd_df.iterrows():
            mtd_map[str(r["username"])] = float(r.get("fyc") or 0)

    skip = {x.lower() for x in CHECKIN_CHALLENGE_SKIP}
    rows = []
    for u in members:
        stuck = get_stuck_cases(u, on_or_before=today)
        wk = wk_map.get(u, {"wk_score": 0, "wk_count": 0})
        skipped = str(u).strip().lower() in skip
        rows.append(
            {
                "username": u,
                "wk_score": wk["wk_score"],
                "wk_count": wk["wk_count"],
                "mtd_fyc": mtd_map.get(u, 0.0),
                "stuck_count": int(len(stuck)),
                # Temporary skips (KK) never count as short on weekly acts
                "needs_acts": (not skipped) and wk["wk_count"] < WEEKLY_MIN_ACTS,
                "max_overdue": int(stuck["overdue_days"].max()) if not stuck.empty else 0,
            }
        )
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    return out.sort_values(
        by=["stuck_count", "max_overdue", "wk_score"],
        ascending=[False, False, True],
    )


def weekly_activity_shortfall(overview: pd.DataFrame | None = None) -> pd.DataFrame:
    """Members below WEEKLY_MIN_ACTS — Admin home ops desk list.

    Pass an existing overview frame to avoid a second Sheets round-trip.
    """
    if overview is None:
        overview = get_team_coach_overview()
    if overview is None or getattr(overview, "empty", True):
        return pd.DataFrame()
    if "needs_acts" not in overview.columns:
        return pd.DataFrame()
    short = overview[overview["needs_acts"]].copy()
    if short.empty:
        return short
    sort_cols = [c for c in ("wk_count", "username") if c in short.columns]
    return short.sort_values(by=sort_cols, ascending=True) if sort_cols else short


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
    guest_names = {x.lower() for x in GUEST_USERNAMES}
    hide = set(INACTIVE_MEMBERS) | guest_names
    # Also drop any username whose role is Guest if we can resolve it
    team = get_team_users()
    if not team.empty:
        allowed = set(team["username"].astype(str))
        return df[df["username"].astype(str).isin(allowed)].sort_values(
            by="date", ascending=False
        )
    return df[
        ~df["username"].astype(str).str.strip().str.lower().isin({x.lower() for x in hide})
    ].sort_values(by="date", ascending=False)


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
    users = get_team_users()
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
    users = get_team_users()
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
    users = get_team_users()
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


def member_home_metrics(username: str, *, today=None) -> dict:
    """Member homepage scorecard: MTD → YTD/MDRT → recruit remaining."""
    today = today or datetime.date.today()
    month = today.strftime("%Y-%m")
    snap = get_member_snapshot(username)
    mtd = get_mtd_fyc(username, month)
    recruit = int(snap.get("recruit") or 0)
    target = int(RECRUIT_YEAR_TARGET) if RECRUIT_YEAR_TARGET else 0
    return {
        "month": month,
        "mtd_fyc": float(mtd),
        "ytd_fyc": float(snap.get("fyc") or 0),
        "mdrt_progress": float(snap.get("mdrt_progress") or 0),
        "mdrt_pct": float(snap.get("mdrt_pct") or 0),
        "mdrt_remaining": float(snap.get("mdrt_remaining") or 0),
        "mdrt_met": bool(snap.get("mdrt_met")),
        "mdrt_target": float(MDRT_TARGET) if MDRT_TARGET else 0.0,
        "recruit": recruit,
        "recruit_target": target,
        "recruit_remaining": max(0, target - recruit),
        "wk_count": int(snap.get("wk_count") or 0),
        "wk_score": int(snap.get("wk_score") or 0),
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

        # Guests don't participate in team activity notifications
        if is_guest_account(current_user):
            st.session_state["_notif_checked_this_login"] = True
            return
        users_df = get_clean_users()
        act_df = read_data("activities")
        if users_df.empty or act_df.empty:
            st.session_state["_notif_checked_this_login"] = True
            return
        user_record = users_df[
            users_df["username"].astype(str).str.strip().str.lower()
            == str(current_user).strip().lower()
        ]
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
        guest_names = {x.lower() for x in GUEST_USERNAMES}
        new_activities = act_df[
            (act_df["timestamp_dt"] > last_read)
            & (act_df["username"] != current_user)
            & (~act_df["username"].isin(INACTIVE_MEMBERS))
            & (~act_df["username"].astype(str).str.strip().str.lower().isin(guest_names))
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
