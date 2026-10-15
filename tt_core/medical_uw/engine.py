"""Match questionnaire answers to underwriting scenarios."""

from __future__ import annotations

from typing import Any


def outcome_tone(text: str) -> str:
    """Map outcome text to a simple tone for UI coloring."""
    t = str(text or "")
    if "拒絕" in t or "DECLINE" in t.upper():
        return "bad"
    if "延遲" in t or "POSTPONE" in t.upper():
        return "warn"
    if "不保" in t or "EXCLUSION" in t.upper():
        return "warn"
    if "加保" in t or "SUB" in t.upper() or "+50" in t or "+" in t:
        return "caution"
    if "個別" in t or "INDIVIDUAL" in t.upper() or "視乎" in t:
        return "caution"
    if "標準" in t or "STANDARD" in t.upper():
        return "good"
    return "neutral"


def _scenario_score(scenario: dict, answers: dict[str, Any]) -> int | None:
    """Return match score (higher = better) or None if incompatible."""
    match = scenario.get("match") or {}
    if not match:
        return 0
    score = 0
    for key, expected in match.items():
        got = answers.get(key)
        if got is None or got == "":
            return None
        if isinstance(expected, list):
            if got not in expected:
                return None
            score += 2
        elif got == expected:
            score += 3
        else:
            return None
    return score


def match_scenarios(
    disease: dict, answers: dict[str, Any], *, fallback_all: bool = True
) -> list[dict]:
    """
    Rank scenarios for a disease given answers.
    Fully matched scenarios first; if none match and fallback_all, return all
    for manual pick.
    """
    scenarios = list(disease.get("scenarios") or [])
    if not scenarios:
        return []

    scored: list[tuple[int, dict]] = []
    for sc in scenarios:
        score = _scenario_score(sc, answers)
        if score is not None and score > 0:
            scored.append((score, sc))

    if scored:
        scored.sort(key=lambda x: (-x[0], x[1].get("label_zh", "")))
        return [sc for _, sc in scored]

    return scenarios if fallback_all else []


def summarize_answers(disease: dict, answers: dict[str, Any]) -> list[tuple[str, str]]:
    """Human-readable (question label, answer label) pairs."""
    rows: list[tuple[str, str]] = []
    for q in disease.get("questions") or []:
        qid = q.get("id")
        if not qid or qid not in answers:
            continue
        val = answers.get(qid)
        label = q.get("prompt") or qid
        ans_label = str(val)
        for opt in q.get("options") or []:
            if opt.get("value") == val:
                ans_label = opt.get("label") or ans_label
                break
        rows.append((label, ans_label))
    return rows
