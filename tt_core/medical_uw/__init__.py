"""常見疾病核保指引 — interactive underwriting reference for field agents."""

from tt_core.medical_uw.catalog import (
    PRODUCT_LABELS,
    disclaimer_text,
    get_disease,
    list_diseases,
    search_diseases,
)
from tt_core.medical_uw.engine import (
    match_scenarios,
    outcome_tone,
    summarize_answers,
)

__all__ = [
    "PRODUCT_LABELS",
    "disclaimer_text",
    "get_disease",
    "list_diseases",
    "search_diseases",
    "match_scenarios",
    "outcome_tone",
    "summarize_answers",
]
