"""Weekly WhatsApp battle report — rewards/penalties exclude Tim.

Rules:
- Tim's score still appears in the detail list.
- Tim is never on the penalty list and never receives MVP prize money.
- If nobody is penalized, Tim sponsors $100 to the top scorer among others.
- If Tim has the overall highest score, prize goes to the 2nd-highest
  (i.e. highest among non-Tim members).
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from tt_core.constants import WEEKLY_MIN_ACTS, WEEKLY_PENALTY

# Leader / sponsor — excluded from rewards & penalties
WEEKLY_REPORT_EXCLUDED = frozenset({"Tim", "tim", "TIM"})


def _is_excluded(username: Any) -> bool:
    return str(username or "").strip() in WEEKLY_REPORT_EXCLUDED


def eligible_frame(wk_df: pd.DataFrame) -> pd.DataFrame:
    """Members who can win prize / be fined (exclude Tim)."""
    if wk_df is None or getattr(wk_df, "empty", True):
        return pd.DataFrame()
    work = wk_df.copy()
    mask = ~work["username"].astype(str).map(_is_excluded)
    return work[mask].copy()


def pick_mvp_winners(wk_df: pd.DataFrame) -> pd.DataFrame:
    """Highest score among non-Tim members (score > 0)."""
    elig = eligible_frame(wk_df)
    if elig.empty:
        return pd.DataFrame()
    max_score = float(elig["wk_score"].max() or 0)
    if max_score <= 0:
        return pd.DataFrame()
    return elig[elig["wk_score"] == max_score].copy()


def pick_losers(wk_df: pd.DataFrame) -> pd.DataFrame:
    """Below weekly activity minimum — Tim never listed."""
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
    report += "\n🚀 *新一週由零開始，大家加油！*"
    return report
