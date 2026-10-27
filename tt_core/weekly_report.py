"""Weekly WhatsApp battle report — rewards/penalties exclude Tim.

Rules:
- Tim's score still appears in the detail list.
- Tim is never on the penalty list and never receives MVP prize money.
- If nobody is penalized, Tim sponsors $100 to the top scorer among others.
- If Tim has the overall highest score, prize goes to the 2nd-highest
  (i.e. highest among non-Tim members).
- Members in CHECKIN_CHALLENGE_SKIP (e.g. KK) are fully left out of the
  challenge for now: no fine, no MVP, not listed in 詳細戰況.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

import pandas as pd

from tt_core.constants import CHECKIN_CHALLENGE_SKIP, WEEKLY_MIN_ACTS, WEEKLY_PENALTY

# Leader / sponsor — excluded from rewards & penalties (score still shown)
_WEEKLY_PRIZE_EXCLUDED = frozenset({"tim"})


def _norm(username: Any) -> str:
    """Canonical username: NFKC (fullwidth ＫＫ→KK), strip, lower."""
    text = str(username or "")
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"[\u200b\u200c\u200d\ufeff]", "", text)
    return text.strip().lower()


def _skip_names() -> frozenset[str]:
    return frozenset(_norm(x) for x in CHECKIN_CHALLENGE_SKIP)


def is_checkin_challenge_skipped(username: Any) -> bool:
    """True if this member is temporarily out of the 打卡 challenge."""
    return _norm(username) in _skip_names()


def _is_prize_excluded(username: Any) -> bool:
    """No fine / no MVP prize (Tim + temporary skips)."""
    n = _norm(username)
    return n in _WEEKLY_PRIZE_EXCLUDED or n in _skip_names()


def filter_checkin_challenge(df: pd.DataFrame | None) -> pd.DataFrame:
    """Drop temporary skips from challenge boards / prize-pool math."""
    if df is None or getattr(df, "empty", True):
        return pd.DataFrame() if df is None else df.copy()
    if "username" not in df.columns:
        return df.copy()
    skip = _skip_names()
    if not skip:
        return df.copy()
    return df[~df["username"].astype(str).map(_norm).isin(skip)].copy()


def report_mentions_skipped(report: str) -> bool:
    """True if a cached WhatsApp report still names a skipped member."""
    text = str(report or "")
    if not text:
        return False
    for name in _skip_names():
        # Match fine line or detail line for that person
        if re.search(rf"❌\s*{re.escape(name)}\b", text, flags=re.I):
            return True
        if re.search(rf"(?m)^{re.escape(name)}\s*:", text, flags=re.I):
            return True
        # Also catch original casing from sheet before norm
        for raw in CHECKIN_CHALLENGE_SKIP:
            if f"❌ {raw}" in text or f"{raw}:" in text:
                return True
    return False


def eligible_frame(wk_df: pd.DataFrame) -> pd.DataFrame:
    """Members who can win prize / be fined (exclude Tim + temporary skips)."""
    if wk_df is None or getattr(wk_df, "empty", True):
        return pd.DataFrame()
    work = wk_df.copy()
    mask = ~work["username"].astype(str).map(_is_prize_excluded)
    return work[mask].copy()


def pick_mvp_winners(wk_df: pd.DataFrame) -> pd.DataFrame:
    """Highest score among non-Tim / non-skipped members (score > 0)."""
    elig = eligible_frame(wk_df)
    if elig.empty:
        return pd.DataFrame()
    max_score = float(elig["wk_score"].max() or 0)
    if max_score <= 0:
        return pd.DataFrame()
    return elig[elig["wk_score"] == max_score].copy()


def pick_losers(wk_df: pd.DataFrame) -> pd.DataFrame:
    """Below weekly activity minimum — Tim / skips never listed."""
    elig = eligible_frame(wk_df)
    if elig.empty:
        return pd.DataFrame()
    return elig[elig["wk_count"] < WEEKLY_MIN_ACTS].copy()


def build_weekly_settlement_report(
    wk_df: pd.DataFrame,
    start,
    end,
    *,
    sponsor_name: str = "Tim",
) -> str:
    """Format WhatsApp-ready weekly settlement text."""
    # Drop temporary skips (KK) from the entire message up front
    wk_df = filter_checkin_challenge(wk_df)
    winners = pick_mvp_winners(wk_df)
    losers = pick_losers(wk_df)
    penalty_total = int(len(losers) * WEEKLY_PENALTY)

    if not winners.empty:
        if penalty_total > 0:
            prize = penalty_total / len(winners)
        else:
            # Nobody fined → Tim sponsors $100 to top non-Tim scorer(s)
            prize = WEEKLY_PENALTY / len(winners)
    else:
        prize = 0

    report = f"📅 *【TIM TEAM 上週戰報 ({start} ~ {end})】*\n\n"

    if not winners.empty:
        report += f"🏆 *上週 MVP (獨得獎金 ${int(prize)}):*\n"
        for _, w in winners.iterrows():
            report += f"👑 *{w['username']}* ({int(w['wk_score'])}分)\n"
        if penalty_total > 0:
            report += f"_多謝 {len(losers)} 位同事贊助獎金池！_\n\n"
        else:
            report += (
                f"_無人罰款！{sponsor_name} 獎 ${WEEKLY_PENALTY} "
                f"俾最高分同事！_\n\n"
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
    if wk_df is not None and not wk_df.empty:
        for _, row in wk_df.sort_values(by="wk_score", ascending=False).iterrows():
            report += (
                f"{row['username']}: {int(row['wk_score'])}分 "
                f"({int(row['wk_count'])}次)\n"
            )
    skip_label = "、".join(str(x) for x in CHECKIN_CHALLENGE_SKIP)
    if skip_label:
        report += f"\n_（暫時唔計：{skip_label}）_\n"
    report += "\n🚀 *新一週由零開始，大家加油！*"
    return report
